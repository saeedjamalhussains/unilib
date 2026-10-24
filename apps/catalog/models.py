from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.catalog.validators import validate_isbn


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Author(TimestampedModel):
    name = models.CharField(max_length=200, db_index=True)
    biography = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class Publisher(TimestampedModel):
    name = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class Category(TimestampedModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "pk")

    def __str__(self):
        return self.name


class Book(TimestampedModel):
    title = models.CharField(max_length=300, db_index=True)
    subtitle = models.CharField(max_length=300, blank=True)
    isbn = models.CharField(max_length=17, unique=True, validators=[validate_isbn])
    edition = models.CharField(max_length=100, blank=True)
    publication_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(9999),
        ],
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.PROTECT,
        related_name="books",
    )
    authors = models.ManyToManyField(Author, related_name="books")
    categories = models.ManyToManyField(Category, related_name="books", blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ("title", "pk")
        permissions = (("manage_catalog", "Can add and edit catalog records"),)

    def __str__(self):
        return self.title
