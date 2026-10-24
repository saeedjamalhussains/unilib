from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.api import log
from apps.inventory.models import BookCopy


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
    is_new = copy.pk is None
    if is_new:
        before = None
    else:
        existing = BookCopy.objects.select_for_update().get(pk=copy.pk)
        before = _copy_snapshot(existing)
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
def change_copy_status(actor: User, copy: BookCopy, status: str) -> BookCopy:
    """Change a copy's status through the audited inventory service."""
    copy = BookCopy.objects.select_for_update().get(pk=copy.pk)
    if status not in BookCopy.Status.values:
        raise ValidationError({"status": "Select a valid copy status."})
    if copy.status == status:
        return copy
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
