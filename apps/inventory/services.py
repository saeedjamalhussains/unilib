from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.api import log
from apps.inventory.models import BookCopy


def _validate_status_transition(copy: BookCopy, status: str) -> None:
    from apps.circulation.models import Loan
    from apps.reservations.models import Reservation

    has_active_loan = Loan.objects.filter(copy=copy, returned_at__isnull=True).exists()
    has_ready_hold = Reservation.objects.filter(
        ready_copy=copy, status=Reservation.Status.READY
    ).exists()
    if has_active_loan and status != BookCopy.Status.ON_LOAN:
        raise ValidationError("A copy with an active loan cannot leave its on-loan status.")
    if status == BookCopy.Status.ON_LOAN and not has_active_loan:
        raise ValidationError("A copy can only be marked on loan through circulation.")
    if has_ready_hold and status != BookCopy.Status.ON_HOLD:
        raise ValidationError("A copy with a ready reservation cannot leave its hold status.")
    if status == BookCopy.Status.ON_HOLD and not has_ready_hold:
        raise ValidationError("A copy can only be placed on hold for a ready reservation.")


def _copy_snapshot(copy: BookCopy) -> dict:
    return {
        "book_id": copy.book_id,
        "accession_number": copy.accession_number,
        "shelf_location": copy.shelf_location,
        "status": copy.status,
        "condition": copy.condition,
        "acquired_date": copy.acquired_date.isoformat(),
    }


@transaction.atomic
def save_copy(actor: User, copy: BookCopy) -> BookCopy:
    """Persist a physical copy and audit creation, updates, and status changes."""
    if not actor.has_perm("inventory.manage_copies"):
        raise PermissionDenied("You are not allowed to manage physical copies.")
    is_new = copy.pk is None
    if is_new:
        before = None
    else:
        existing = BookCopy.objects.select_for_update().get(pk=copy.pk)
        before = _copy_snapshot(existing)
    if is_new and copy.status != BookCopy.Status.AVAILABLE:
        raise ValidationError("New copies must start as available.")
    if before is not None and before["status"] != copy.status:
        _validate_status_transition(copy, copy.status)
    copy.full_clean()
    copy.save()
    after = _copy_snapshot(copy)
    if before != after:
        if is_new:
            action = "inventory.copy_created"
        elif before["status"] != after["status"]:
            action = "inventory.copy_status_changed"
        else:
            action = "inventory.copy_updated"
        log(actor, action, target=copy, before=before, after=after)
    return copy


@transaction.atomic
def change_copy_status(actor: User | None, copy: BookCopy, status: str) -> BookCopy:
    """Change a copy's status through the audited inventory service."""
    if actor is not None and not actor.has_perm("inventory.manage_copies"):
        raise PermissionDenied("You are not allowed to change copy status.")
    copy = BookCopy.objects.select_for_update().get(pk=copy.pk)
    if status not in BookCopy.Status.values:
        raise ValidationError({"status": "Select a valid copy status."})
    if copy.status == status:
        return copy
    _validate_status_transition(copy, status)
    before = _copy_snapshot(copy)
    copy.status = status
    copy.full_clean()
    copy.save(update_fields=("status", "updated_at"))
    log(
        actor,
        "inventory.copy_status_changed",
        target=copy,
        before=before,
        after=_copy_snapshot(copy),
    )
    return copy
