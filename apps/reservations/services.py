from datetime import datetime, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.api import log
from apps.catalog.models import Book
from apps.circulation.models import Loan
from apps.inventory.models import BookCopy
from apps.membership.models import LibraryPolicy, MemberProfile
from apps.reservations.models import Reservation


def notify(reservation: Reservation) -> None:
    """Send a hold-ready notice through Django's configured email backend."""
    if reservation.member.user.email:
        send_mail(
            subject=f"Library hold ready: {reservation.book.title}",
            message=f"Your reserved copy is ready. Please collect it before {reservation.hold_expires_at}.",
            from_email=None,
            recipient_list=[reservation.member.user.email],
            fail_silently=False,
        )


@transaction.atomic
def place_reservation(book: Book, member: MemberProfile) -> Reservation:
    """Place a member in the FIFO queue when no copy is available."""
    from apps.catalog.models import Book

    book = Book.objects.select_for_update().get(pk=book.pk)
    member = MemberProfile.objects.select_for_update().get(pk=member.pk)
    if (
        member.status != MemberProfile.Status.ACTIVE
        or member.membership_expiry < timezone.localdate()
    ):
        raise ValidationError("An active membership is required to place a reservation.")
    if BookCopy.objects.filter(book=book, status=BookCopy.Status.AVAILABLE).exists():
        raise ValidationError(
            "A copy is currently available; reservations are only for unavailable titles."
        )
    policy = LibraryPolicy.objects.get(member_type=member.member_type)
    active = Reservation.objects.filter(
        member=member, status__in=(Reservation.Status.PENDING, Reservation.Status.READY)
    )
    if active.count() >= policy.max_active_reservations:
        raise ValidationError("The member has reached the active-reservation limit.")
    if Loan.objects.filter(member=member, copy__book=book, returned_at__isnull=True).exists():
        raise ValidationError("A member cannot reserve a title already on loan to them.")
    if active.filter(book=book).exists():
        raise ValidationError("The member already has an active reservation for this title.")
    reservation = Reservation.objects.create(book=book, member=member)
    log(member.user, "reservation.created", target=reservation)
    return reservation


@transaction.atomic
def cancel_reservation(reservation: Reservation, actor: User) -> Reservation:
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if not actor.has_perm("reservations.manage_reservations") and not (
        actor.has_perm("reservations.place_reservation")
        and reservation.member.user_id == actor.pk
    ):
        raise PermissionDenied("You are not allowed to cancel this reservation.")
    if reservation.status not in (Reservation.Status.PENDING, Reservation.Status.READY):
        raise ValidationError("Only pending or ready reservations can be cancelled.")
    copy = reservation.ready_copy
    reservation.status = Reservation.Status.CANCELLED
    reservation.ready_copy = None
    reservation.hold_expires_at = None
    reservation.save(update_fields=("status", "ready_copy", "hold_expires_at", "updated_at"))
    if copy is not None:
        _advance_hold(copy, actor)
    log(actor, "reservation.cancelled", target=reservation)
    return reservation


def _advance_hold(copy: BookCopy, actor: User | None) -> None:
    next_reservation = (
        Reservation.objects.select_for_update()
        .filter(book=copy.book, status=Reservation.Status.PENDING)
        .order_by("created_at", "pk")
        .first()
    )
    if next_reservation is None:
        from apps.inventory.services import change_copy_status

        change_copy_status(actor, copy, BookCopy.Status.AVAILABLE)
        return
    next_reservation.status = Reservation.Status.READY
    next_reservation.ready_copy = copy
    hours = LibraryPolicy.objects.get(
        member_type=next_reservation.member.member_type
    ).reservation_hold_hours
    next_reservation.hold_expires_at = timezone.now() + timedelta(hours=hours)
    next_reservation.save(update_fields=("status", "ready_copy", "hold_expires_at", "updated_at"))
    from apps.inventory.services import change_copy_status

    change_copy_status(actor, copy, BookCopy.Status.ON_HOLD)
    transaction.on_commit(lambda: notify(next_reservation))
    log(actor, "reservation.ready", target=next_reservation)


@transaction.atomic
def expire_holds(now: datetime | None = None) -> list[int]:
    """Expire timed-out holds and immediately advance each returned copy's queue."""
    now = now or timezone.now()
    expired_ids = []
    for reservation in (
        Reservation.objects.select_for_update()
        .filter(status=Reservation.Status.READY, hold_expires_at__lte=now)
        .select_related("ready_copy", "book")
        .order_by("hold_expires_at", "pk")
    ):
        copy = reservation.ready_copy
        reservation.status = Reservation.Status.EXPIRED
        reservation.ready_copy = None
        reservation.hold_expires_at = None
        reservation.save(update_fields=("status", "ready_copy", "hold_expires_at", "updated_at"))
        log(None, "reservation.expired", target=reservation)
        if copy is not None:
            _advance_hold(copy, None)
        expired_ids.append(reservation.pk)
    return expired_ids
