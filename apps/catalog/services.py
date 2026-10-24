import re
from collections.abc import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.api import log
from apps.catalog.models import Author, Book, Category, Publisher

CatalogRecord = Author | Book | Category | Publisher


def _catalog_snapshot(item: CatalogRecord) -> dict:
    if isinstance(item, Book):
        return {
            "title": item.title,
            "isbn": item.isbn,
            "subtitle": item.subtitle,
            "edition": item.edition,
            "publication_year": item.publication_year,
            "publisher_id": item.publisher_id,
            "description": item.description,
            "price": str(item.price) if item.price is not None else None,
            "author_ids": sorted(item.authors.values_list("pk", flat=True)),
            "category_ids": sorted(item.categories.values_list("pk", flat=True)),
        }
    if isinstance(item, Author):
        return {"name": item.name, "biography": item.biography}
    if isinstance(item, Publisher):
        return {"name": item.name}
    if isinstance(item, Category):
        return {"name": item.name, "description": item.description}
    raise TypeError("Unsupported catalog record.")


@transaction.atomic
def save_catalog_record(
    actor: User,
    record: CatalogRecord,
    *,
    authors: Iterable[Author] | None = None,
    categories: Iterable[Category] | None = None,
) -> CatalogRecord:
    """Validate and save one catalog record, auditing the before/after state."""
    is_new = record.pk is None
    if is_new:
        before = None
    else:
        original = type(record).objects.get(pk=record.pk)
        before = _catalog_snapshot(original)
    if isinstance(record, Book):
        record.isbn = re.sub(r"[\s-]", "", record.isbn).upper()
    record.full_clean(exclude=("authors", "categories"))
    record.save()
    if isinstance(record, Book):
        if authors is not None:
            record.authors.set(authors)
        if categories is not None:
            record.categories.set(categories)
    after = _catalog_snapshot(record)
    if before != after:
        action = (
            f"catalog.{record._meta.model_name}_created"
            if is_new
            else f"catalog.{record._meta.model_name}_updated"
        )
        log(actor, action, target=record, before=before, after=after)
    return record


@transaction.atomic
def delete_book(actor: User, book: Book) -> None:
    """Delete a book title only when it has no protected physical copies."""
    book = Book.objects.select_for_update().get(pk=book.pk)
    if book.copies.exists():
        raise ValidationError("Books with inventory copies cannot be deleted.")
    before = _catalog_snapshot(book)
    log(actor, "catalog.book_deleted", target=book, before=before)
    book.delete()


@transaction.atomic
def delete_catalog_record(actor: User, record: Author | Category | Publisher) -> None:
    """Delete an unused author, publisher, or category with an audit event."""
    record = type(record).objects.select_for_update().get(pk=record.pk)
    if isinstance(record, Author) and record.books.exists():
        raise ValidationError("Authors linked to books cannot be deleted.")
    if isinstance(record, Publisher) and record.books.exists():
        raise ValidationError("Publishers linked to books cannot be deleted.")
    if isinstance(record, Category) and record.books.exists():
        raise ValidationError("Categories linked to books cannot be deleted.")
    before = _catalog_snapshot(record)
    log(
        actor,
        f"catalog.{record._meta.model_name}_deleted",
        target=record,
        before=before,
    )
    record.delete()
