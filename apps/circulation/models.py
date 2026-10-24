from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.inventory.models import BookCopy
from apps.membership.models import MemberProfile


class LoanQuerySet(models.QuerySet):
    def owned_by(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(member__user=user)


class Loan(models.Model):
    copy = models.ForeignKey(BookCopy, on_delete=models.PROTECT, related_name="loans")
    member = models.ForeignKey(MemberProfile, on_delete=models.PROTECT, related_name="loans")
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="loans_issued"
    )
    issued_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="loans_returned",
    )
    renewals_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LoanQuerySet.as_manager()

    class Meta:
        ordering = ("-issued_at", "-pk")
        permissions = (
            ("process_circulation", "Can issue, return, and renew loans"),
            ("view_all_loans", "Can view all loans"),
            ("view_own_loans", "Can view own loans"),
            ("renew_own_loan", "Can renew own loans"),
        )
        constraints = (
            models.UniqueConstraint(
                fields=("copy",),
                condition=Q(returned_at__isnull=True),
                name="one_active_loan_per_copy",
            ),
        )
        indexes = (models.Index(fields=("member", "returned_at")),)

    @property
    def is_overdue(self):
        return self.returned_at is None and self.due_date < timezone.localdate()

    def __str__(self):
        return f"{self.copy.accession_number} loan to {self.member.university_id}"
