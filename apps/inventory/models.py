from django.db import models

from apps.catalog.models import Book, TimestampedModel


class BookCopy(TimestampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ON_LOAN = "on_loan", "On loan"
        ON_HOLD = "on_hold", "On hold"
        LOST = "lost", "Lost"
        DAMAGED = "damaged", "Damaged"
        WITHDRAWN = "withdrawn", "Withdrawn"

    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name="copies",
    )
    accession_number = models.CharField(max_length=100, unique=True)
    shelf_location = models.CharField(max_length=100)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
    )
    condition = models.CharField(max_length=200, blank=True)
    acquired_date = models.DateField()

    class Meta:
        ordering = ("accession_number", "pk")
        permissions = (("manage_copies", "Can add and edit physical book copies"),)
        indexes = (
            models.Index(fields=("status", "accession_number")),
        )

    def __str__(self):
        return f"{self.accession_number} — {self.book.title}"
