from django.db import models
from django.db.models import Q

from apps.catalog.models import Book
from apps.inventory.models import BookCopy
from apps.membership.models import MemberProfile


class ReservationQuerySet(models.QuerySet):
    def owned_by(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(member__user=user)


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready for pickup"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="reservations")
    member = models.ForeignKey(MemberProfile, on_delete=models.PROTECT, related_name="reservations")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    ready_copy = models.ForeignKey(
        BookCopy, null=True, blank=True, on_delete=models.PROTECT, related_name="reservations"
    )
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReservationQuerySet.as_manager()

    class Meta:
        ordering = ("created_at", "pk")
        permissions = (
            ("place_reservation", "Can place and cancel own reservations"),
            ("manage_reservations", "Can view and manage all reservations"),
        )
        constraints = (
            models.UniqueConstraint(
                fields=("book", "member"),
                condition=Q(status__in=("pending", "ready")),
                name="one_active_reservation_per_book_member",
            ),
        )

    def __str__(self):
        return f"{self.book.title} reserved by {self.member.university_id}"
