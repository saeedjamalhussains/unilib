from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.circulation.models import Loan
from apps.membership.models import MemberProfile


class FineQuerySet(models.QuerySet):
    def owned_by(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(member__user=user)


class Fine(models.Model):
    class Reason(models.TextChoices):
        OVERDUE = "overdue", "Overdue"
        LOST = "lost", "Lost"
        DAMAGED = "damaged", "Damaged"

    class Status(models.TextChoices):
        OUTSTANDING = "outstanding", "Outstanding"
        PAID = "paid", "Paid"
        WAIVED = "waived", "Waived"

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="fines")
    member = models.ForeignKey(MemberProfile, on_delete=models.PROTECT, related_name="fines")
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    reason = models.CharField(max_length=10, choices=Reason.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OUTSTANDING)
    assessed_at = models.DateTimeField(default=timezone.now)
    waived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fines_waived",
    )
    waiver_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FineQuerySet.as_manager()

    class Meta:
        ordering = ("-assessed_at", "-pk")
        permissions = (
            ("view_own_fines", "Can view own fines"),
            ("manage_fines", "Can record payments and view all fines"),
            ("waive_fine", "Can waive fines"),
        )
        constraints = (
            models.CheckConstraint(condition=Q(amount__gte=0), name="fine_amount_nonnegative"),
        )

    @property
    def balance(self):
        from django.db.models import Sum

        cached_payments = getattr(self, "_prefetched_objects_cache", {}).get("payments")
        if cached_payments is None:
            paid = self.payments.aggregate(total=Sum("amount"))["total"] or 0
        else:
            paid = sum((payment.amount for payment in cached_payments), 0)
        return max(self.amount - paid, 0)

    def __str__(self):
        return f"{self.get_reason_display()} fine for {self.member.university_id}"


class Payment(models.Model):
    fine = models.ForeignKey(Fine, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    method = models.CharField(max_length=50)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    paid_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-paid_at", "-pk")
        constraints = (
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        )

    def __str__(self):
        return f"{self.amount} payment for fine {self.fine_id}"
