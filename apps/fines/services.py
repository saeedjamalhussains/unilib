from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.api import log
from apps.fines.models import Fine, Payment


def member_outstanding_balance(member) -> Decimal:
    """Return the total unpaid amount across outstanding fines for a member."""
    return sum(
        (
            fine.balance
            for fine in Fine.objects.filter(
                member=member, status=Fine.Status.OUTSTANDING
            ).prefetch_related("payments")
        ),
        Decimal("0.00"),
    )


@transaction.atomic
def record_payment(
    fine: Fine, amount: Decimal | str, received_by: User, method: str = "cash"
) -> Payment:
    """Record a partial or full payment without allowing overpayment."""
    if not received_by.has_perm("fines.manage_fines"):
        raise PermissionDenied("You are not allowed to record fine payments.")
    fine = Fine.objects.select_for_update().get(pk=fine.pk)
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Payment must be greater than zero."})
    balance = fine.balance
    if fine.status != Fine.Status.OUTSTANDING or amount > balance:
        raise ValidationError(
            {"amount": "Payment exceeds the outstanding balance or the fine is closed."}
        )
    payment = Payment(fine=fine, amount=amount, method=method, received_by=received_by)
    payment.full_clean()
    payment.save()
    if payment.amount == balance:
        fine.status = Fine.Status.PAID
        fine.save(update_fields=("status", "updated_at"))
    log(received_by, "fine.payment_recorded", target=payment, fine_id=fine.pk, amount=str(amount))
    return payment


@transaction.atomic
def waive_fine(fine: Fine, admin: User, reason: str) -> Fine:
    fine = Fine.objects.select_for_update().get(pk=fine.pk)
    if not admin.has_perm("fines.waive_fine"):
        raise PermissionDenied("Only administrators may waive fines.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"waiver_reason": "A reason is required to waive a fine."})
    if fine.status != Fine.Status.OUTSTANDING:
        raise ValidationError("Only outstanding fines can be waived.")
    fine.status = Fine.Status.WAIVED
    fine.waived_by = admin
    fine.waiver_reason = reason
    fine.save(update_fields=("status", "waived_by", "waiver_reason", "updated_at"))
    log(admin, "fine.waived", target=fine, reason=reason)
    return fine
