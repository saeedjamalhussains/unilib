from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class OwnedByUserQuerySet(models.QuerySet):
    def owned_by(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)


class MemberProfile(models.Model):
    class MemberType(models.TextChoices):
        STUDENT = "student", "Student"
        FACULTY = "faculty", "Faculty"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="member_profile"
    )
    university_id = models.CharField(max_length=64, unique=True)
    department = models.CharField(max_length=150)
    member_type = models.CharField(max_length=10, choices=MemberType.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    membership_expiry = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        ordering = ("university_id", "pk")
        permissions = (
            ("manage_members", "Can register and edit library members"),
            ("view_all_members", "Can view all member profiles"),
        )

    def __str__(self):
        return f"{self.university_id} — {self.user.get_full_name() or self.user.username}"


class LibraryPolicy(models.Model):
    member_type = models.CharField(
        max_length=10, choices=MemberProfile.MemberType.choices, unique=True
    )
    max_active_loans = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    loan_days = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    max_renewals = models.PositiveSmallIntegerField()
    renewal_days = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    fine_per_day = models.DecimalField(max_digits=7, decimal_places=2)
    grace_days = models.PositiveSmallIntegerField(default=0)
    max_fine_per_loan = models.DecimalField(max_digits=8, decimal_places=2)
    fine_block_threshold = models.DecimalField(max_digits=8, decimal_places=2)
    reservation_hold_hours = models.PositiveSmallIntegerField(
        default=72, validators=[MinValueValidator(1)]
    )
    max_active_reservations = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("member_type",)
        permissions = (("manage_policy", "Can edit library policies"),)
        constraints = (
            models.CheckConstraint(
                condition=Q(fine_per_day__gte=0)
                & Q(max_fine_per_loan__gte=0)
                & Q(fine_block_threshold__gte=0),
                name="membership_policy_nonnegative_fines",
            ),
        )

    def __str__(self):
        return f"{self.get_member_type_display()} policy"
