from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.api import log
from apps.catalog.models import Book
from apps.circulation.models import Loan
from apps.inventory.models import BookCopy
from apps.membership.models import LibraryPolicy, MemberProfile
from apps.membership.services import get_policy
from apps.reservations.models import Reservation


@transaction.atomic
def issue_copy(copy: BookCopy, member: MemberProfile, issued_by: User) -> Loan:
    """Issue an available or member-held copy while serializing competing checkouts."""
    if not issued_by.has_perm("circulation.process_circulation"):
        raise PermissionDenied("You are not allowed to issue copies.")
    Book.objects.select_for_update().get(pk=copy.book_id)
    member = MemberProfile.objects.select_for_update().select_related("user").get(pk=member.pk)
    copy = BookCopy.objects.select_for_update().select_related("book").get(pk=copy.pk)
    today = timezone.localdate()
    policy = get_policy(member.member_type)
    if member.status != MemberProfile.Status.ACTIVE or member.membership_expiry < today:
        raise ValidationError("This membership is not active or has expired.")
    if (
        Loan.objects.filter(member=member, returned_at__isnull=True).count()
        >= policy.max_active_loans
    ):
        raise ValidationError("The member has reached the active-loan limit.")
    from apps.fines.services import member_outstanding_balance

    if member_outstanding_balance(member) > policy.fine_block_threshold:
        raise ValidationError("The member's outstanding fines exceed the issue limit.")
    ready_reservation = (
        Reservation.objects.select_for_update()
        .filter(book=copy.book, member=member, status=Reservation.Status.READY, ready_copy=copy)
        .first()
    )
    if copy.status == BookCopy.Status.ON_HOLD:
        if ready_reservation is None:
            raise ValidationError("This copy is on hold for another member.")
    elif copy.status != BookCopy.Status.AVAILABLE:
        raise ValidationError("This copy is not available for issue.")
    elif ready_reservation is not None:
        raise ValidationError("A held copy must be issued from its hold status.")
    if copy.status == BookCopy.Status.AVAILABLE:
        available_count = BookCopy.objects.filter(
            book=copy.book, status=BookCopy.Status.AVAILABLE
        ).count()
        pending_for_others = (
            Reservation.objects.filter(book=copy.book, status=Reservation.Status.PENDING)
            .exclude(member=member)
            .exists()
        )
        if available_count <= 1 and pending_for_others:
            raise ValidationError("This is the last available copy and another member is waiting.")
    loan = Loan.objects.create(
        copy=copy,
        member=member,
        issued_by=issued_by,
        due_date=today + timedelta(days=policy.loan_days),
    )
    if ready_reservation is not None:
        ready_reservation.status = Reservation.Status.FULFILLED
        ready_reservation.save(update_fields=("status", "updated_at"))
        log(issued_by, "reservation.fulfilled", target=ready_reservation)
    from apps.inventory.services import change_copy_status

    change_copy_status(issued_by, copy, BookCopy.Status.ON_LOAN)
    log(
        issued_by,
        "loan.issued",
        target=loan,
        member_id=member.pk,
        accession_number=copy.accession_number,
        due_date=loan.due_date.isoformat(),
    )
    return loan


@transaction.atomic
def return_copy(loan: Loan, returned_to: User) -> Loan:
    """Return an active loan, assess any overdue fine, and assign a pending hold."""
    if not returned_to.has_perm("circulation.process_circulation"):
        raise PermissionDenied("You are not allowed to return copies.")
    loan = Loan.objects.select_for_update().select_related("member", "copy__book").get(pk=loan.pk)
    if loan.returned_at is not None:
        raise ValidationError("This loan has already been returned.")
    loan.returned_at = timezone.now()
    loan.returned_to = returned_to
    loan.save(update_fields=("returned_at", "returned_to", "updated_at"))
    policy = get_policy(loan.member.member_type)
    overdue_days = max(0, (timezone.localdate() - loan.due_date).days - policy.grace_days)
    fine_amount = min(
        Decimal(overdue_days) * policy.fine_per_day,
        policy.max_fine_per_loan,
    )
    if fine_amount > 0:
        from apps.fines.models import Fine

        fine = Fine.objects.create(
            loan=loan,
            member=loan.member,
            amount=fine_amount,
            reason=Fine.Reason.OVERDUE,
        )
        log(
            returned_to,
            "fine.assessed",
            target=fine,
            loan_id=loan.pk,
            amount=str(fine_amount),
            reason="overdue",
        )
    copy = BookCopy.objects.select_for_update().get(pk=loan.copy_id)
    reservation = (
        Reservation.objects.select_for_update()
        .filter(book=copy.book, status=Reservation.Status.PENDING)
        .order_by("created_at", "pk")
        .first()
    )
    if reservation is None:
        from apps.inventory.services import change_copy_status

        change_copy_status(returned_to, copy, BookCopy.Status.AVAILABLE)
    else:
        reservation.status = Reservation.Status.READY
        reservation.ready_copy = copy
        reservation.hold_expires_at = timezone.now() + timedelta(
            hours=LibraryPolicy.objects.get(
                member_type=reservation.member.member_type
            ).reservation_hold_hours
        )
        reservation.save(update_fields=("status", "ready_copy", "hold_expires_at", "updated_at"))
        from apps.inventory.services import change_copy_status

        change_copy_status(returned_to, copy, BookCopy.Status.ON_HOLD)
        from apps.reservations.services import notify

        transaction.on_commit(lambda: notify(reservation))
        log(returned_to, "reservation.ready", target=reservation)
    log(returned_to, "loan.returned", target=loan, overdue_days=overdue_days)
    return loan


@transaction.atomic
def renew_loan(loan: Loan, actor: User) -> Loan:
    """Renew an active loan if policy and reservation rules allow it."""
    loan = Loan.objects.select_for_update().select_related("member", "copy__book").get(pk=loan.pk)
    if not actor.has_perm("circulation.process_circulation") and not (
        actor.has_perm("circulation.renew_own_loan") and loan.member.user_id == actor.pk
    ):
        raise PermissionDenied("You are not allowed to renew this loan.")
    if loan.returned_at is not None:
        raise ValidationError("A returned loan cannot be renewed.")
    policy = get_policy(loan.member.member_type)
    if loan.renewals_count >= policy.max_renewals:
        raise ValidationError("The maximum number of renewals has been reached.")
    if loan.due_date < timezone.localdate():
        raise ValidationError("An overdue loan cannot be renewed.")
    if Reservation.objects.filter(book=loan.copy.book, status=Reservation.Status.PENDING).exists():
        raise ValidationError("This title has pending reservations and cannot be renewed.")
    if loan.member.status != MemberProfile.Status.ACTIVE:
        raise ValidationError("The member is not active.")
    loan.due_date = max(timezone.localdate(), loan.due_date) + timedelta(days=policy.renewal_days)
    loan.renewals_count += 1
    loan.save(update_fields=("due_date", "renewals_count", "updated_at"))
    log(actor, "loan.renewed", target=loan, due_date=loan.due_date.isoformat())
    return loan
