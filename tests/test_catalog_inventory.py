from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.catalog.forms import BookForm
from apps.catalog.models import Author, Book, Category, Publisher
from apps.catalog.services import (
    delete_book,
    delete_catalog_record,
    save_catalog_record,
)
from apps.catalog.validators import validate_isbn
from apps.inventory.models import BookCopy
from apps.inventory.services import change_copy_status, save_copy


def isbn13(seed):
    body = f"978030640{seed:03d}"
    checksum = (
        10
        - sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(body))
        % 10
    ) % 10
    return body + str(checksum)


class CatalogInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", stdout=StringIO())
        User = get_user_model()
        cls.admin = User.objects.create_user(
            username="catalog-admin",
            email="catalog-admin@example.edu",
            password="Long-Unique-Admin-Password-2026!",
        )
        cls.admin.groups.add(Group.objects.get(name="Administrator"))
        cls.librarian = User.objects.create_user(
            username="catalog-librarian",
            email="catalog-librarian@example.edu",
            password="Long-Unique-Librarian-Password-2026!",
        )
        cls.librarian.groups.add(Group.objects.get(name="Librarian"))
        cls.student = User.objects.create_user(
            username="catalog-student",
            email="catalog-student@example.edu",
            password="Long-Unique-Student-Password-2026!",
        )
        cls.student.groups.add(Group.objects.get(name="Student"))
        cls.faculty = User.objects.create_user(
            username="catalog-faculty",
            email="catalog-faculty@example.edu",
            password="Long-Unique-Faculty-Password-2026!",
        )
        cls.faculty.groups.add(Group.objects.get(name="Faculty"))
        cls.publisher = Publisher.objects.create(name="Example Press")
        cls.author = Author.objects.create(name="Ada Writer")
        cls.category = Category.objects.create(name="Computing")

    def create_book(self, suffix=1, *, title="Algorithms"):
        return Book.objects.create(
            title=title,
            isbn=isbn13(suffix),
            publisher=self.publisher,
            price="30.00",
        )

    def create_copy(self, book, accession="ACC-001", status=BookCopy.Status.AVAILABLE):
        return BookCopy.objects.create(
            book=book,
            accession_number=accession,
            shelf_location="A-1",
            status=status,
            acquired_date=date(2024, 1, 1),
        )


class ISBNValidationTests(TestCase):
    def test_valid_isbn_10_and_13_are_accepted(self):
        validate_isbn("0306406152")
        validate_isbn("9780306406157")
        validate_isbn("0-306-40615-2")

    def test_invalid_check_digits_and_formats_are_rejected(self):
        for isbn in (
            "0306406153",
            "9780306406158",
            "1234567890123",
            "not-an-isbn",
            "123",
        ):
            with self.subTest(isbn=isbn), self.assertRaises(ValidationError):
                validate_isbn(isbn)

    def test_book_form_normalizes_isbn_separators(self):
        publisher = Publisher.objects.create(name="ISBN Press")
        author = Author.objects.create(name="ISBN Author")
        form = BookForm(
            {
                "title": "ISBN test",
                "isbn": "978-0-306-40615-7",
                "publisher": publisher.pk,
                "authors": [author.pk],
                "categories": [],
                "publication_year": "",
                "edition": "",
                "subtitle": "",
                "description": "",
                "price": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["isbn"], "9780306406157")


class CatalogServiceTests(CatalogInventoryTests):
    def test_create_and_update_catalog_records_are_audited(self):
        book = Book(
            title="Service Book",
            isbn=isbn13(10),
            publisher=self.publisher,
            price="42.50",
        )
        save_catalog_record(
            self.librarian,
            book,
            authors=[self.author],
            categories=[self.category],
        )
        book.title = "Updated Service Book"
        save_catalog_record(
            self.librarian,
            book,
            authors=[self.author],
            categories=[self.category],
        )

        actions = list(
            AuditLog.objects.filter(target_id=str(book.pk))
            .order_by("pk")
            .values_list("action", flat=True)
        )
        self.assertEqual(actions, ["catalog.book_created", "catalog.book_updated"])
        self.assertEqual(
            AuditLog.objects.get(action="catalog.book_created", target_id=str(book.pk)).actor,
            self.librarian,
        )

    def test_catalog_record_save_validates_isbn(self):
        book = Book(title="Bad ISBN", isbn="9780306406158", publisher=self.publisher)

        with self.assertRaises(ValidationError):
            save_catalog_record(self.librarian, book)

        self.assertFalse(Book.objects.filter(title="Bad ISBN").exists())

    def test_book_with_copy_cannot_be_deleted(self):
        book = self.create_book()
        self.create_copy(book)

        with self.assertRaisesMessage(ValidationError, "inventory copies"):
            delete_book(self.admin, book)

        self.assertTrue(Book.objects.filter(pk=book.pk).exists())

    def test_unused_book_and_reference_records_can_be_deleted_with_audit(self):
        book = self.create_book()
        category = Category.objects.create(name="Unused")
        delete_book(self.admin, book)
        delete_catalog_record(self.admin, category)

        self.assertEqual(
            set(
                AuditLog.objects.filter(action__endswith="_deleted").values_list(
                    "action", flat=True
                )
            ),
            {"catalog.book_deleted", "catalog.category_deleted"},
        )

    def test_linked_reference_records_cannot_be_deleted(self):
        book = self.create_book()
        book.authors.add(self.author)
        with self.assertRaisesMessage(ValidationError, "linked to books"):
            delete_catalog_record(self.admin, self.author)
        with self.assertRaisesMessage(ValidationError, "linked to books"):
            delete_catalog_record(self.admin, self.publisher)


class InventoryServiceTests(CatalogInventoryTests):
    def test_copy_create_and_status_changes_are_audited(self):
        book = self.create_book()
        copy = BookCopy(
            book=book,
            accession_number="INV-SERVICE-001",
            shelf_location="B-2",
            acquired_date=date(2024, 2, 1),
        )
        save_copy(self.librarian, copy)
        change_copy_status(self.librarian, copy, BookCopy.Status.DAMAGED)

        events = list(
            AuditLog.objects.filter(target_id=str(copy.pk))
            .order_by("pk")
            .values_list("action", "actor_id")
        )
        self.assertEqual(
            events,
            [
                ("inventory.copy_created", self.librarian.pk),
                ("inventory.copy_status_changed", self.librarian.pk),
            ],
        )

    def test_invalid_status_is_rejected_without_change_or_audit(self):
        book = self.create_book()
        copy = self.create_copy(book)

        with self.assertRaises(ValidationError):
            change_copy_status(self.librarian, copy, "unknown")

        copy.refresh_from_db()
        self.assertEqual(copy.status, BookCopy.Status.AVAILABLE)
        self.assertFalse(
            AuditLog.objects.filter(action="inventory.copy_status_changed").exists()
        )

    def test_copy_update_and_status_update_are_audited(self):
        book = self.create_book()
        copy = self.create_copy(book, accession="INV-UPDATE-001")

        copy.shelf_location = "C-4"
        save_copy(self.librarian, copy)
        copy.status = BookCopy.Status.WITHDRAWN
        save_copy(self.librarian, copy)

        self.assertEqual(
            list(
                AuditLog.objects.filter(target_id=str(copy.pk))
                .order_by("pk")
                .values_list("action", flat=True)
            ),
            ["inventory.copy_updated", "inventory.copy_status_changed"],
        )

    def test_setting_copy_to_current_status_is_audited_as_no_change(self):
        book = self.create_book()
        copy = self.create_copy(book, accession="INV-UNCHANGED-001")

        returned = change_copy_status(
            self.librarian,
            copy,
            BookCopy.Status.AVAILABLE,
        )

        self.assertEqual(returned.status, BookCopy.Status.AVAILABLE)
        self.assertFalse(
            AuditLog.objects.filter(
                target_id=str(copy.pk),
                action="inventory.copy_status_changed",
            ).exists()
        )

    def test_book_deletion_is_protected_at_database_level(self):
        book = self.create_book()
        self.create_copy(book)

        with self.assertRaises(ProtectedError):
            book.delete()


class CatalogAndInventoryViewTests(CatalogInventoryTests):
    def setUp(self):
        self.book = self.create_book()
        self.book.authors.add(self.author)
        self.book.categories.add(self.category)
        self.copy = self.create_copy(self.book)

    def test_anonymous_catalog_access_redirects_to_login(self):
        response = self.client.get(reverse("catalog:book_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_students_can_search_and_view_books_but_not_inventory(self):
        self.client.force_login(self.student)

        for query in (
            {"title": "Algorithm"},
            {"author": "Ada"},
            {"isbn": self.book.isbn[-5:]},
            {"category": "Computing"},
            {"q": "Ada Writer"},
        ):
            with self.subTest(query=query):
                response = self.client.get(reverse("catalog:book_list"), query)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Algorithms")

        detail_response = self.client.get(
            reverse("catalog:book_detail", args=(self.book.pk,))
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "1 available")
        self.assertNotContains(detail_response, "ACC-001")

        denied = self.client.get(reverse("copy_list"))
        self.assertEqual(denied.status_code, 403)

    def test_librarian_can_create_book_and_reference_records(self):
        self.client.force_login(self.librarian)
        response = self.client.post(
            reverse("catalog:book_create"),
            {
                "title": "Created Through View",
                "isbn": isbn13(21),
                "publisher": self.publisher.pk,
                "authors": [self.author.pk],
                "categories": [self.category.pk],
                "subtitle": "",
                "edition": "",
                "publication_year": "",
                "description": "",
                "price": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Book.objects.get(title="Created Through View")
        self.assertEqual(list(created.authors.all()), [self.author])
        self.assertTrue(
            AuditLog.objects.filter(
                action="catalog.book_created",
                target_id=str(created.pk),
                actor=self.librarian,
            ).exists()
        )

        response = self.client.post(
            reverse("catalog:reference_create", args=("authors",)),
            {"name": "New Author", "biography": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Author.objects.filter(name="New Author").exists())

    def test_librarian_can_edit_book_and_audit_change(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("catalog:book_update", args=(self.book.pk,)),
            {
                "title": "Updated Through View",
                "isbn": self.book.isbn,
                "publisher": self.publisher.pk,
                "authors": [self.author.pk],
                "categories": [self.category.pk],
                "subtitle": "",
                "edition": "",
                "publication_year": "",
                "description": "",
                "price": "30.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "Updated Through View")
        self.assertTrue(
            AuditLog.objects.filter(
                action="catalog.book_updated",
                target_id=str(self.book.pk),
                actor=self.librarian,
            ).exists()
        )

    def test_students_cannot_manage_catalog_and_denial_is_audited(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("catalog:book_create"))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.student,
                action="access.denied",
                target_repr=reverse("catalog:book_create"),
            ).exists()
        )

    def test_only_administrator_can_delete_book_and_delete_is_post_only(self):
        self.client.force_login(self.librarian)
        self.assertEqual(
            self.client.get(reverse("catalog:book_delete", args=(self.book.pk,))).status_code,
            403,
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("catalog:book_delete", args=(self.book.pk,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

        response = self.client.post(
            reverse("catalog:book_delete", args=(self.book.pk,))
        )
        self.assertRedirects(response, reverse("catalog:book_detail", args=(self.book.pk,)))
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())

    def test_librarian_can_create_and_change_copy_status(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("copy_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ACC-001")

        response = self.client.post(
            reverse("copy_status", args=(self.copy.pk,)),
            {"status": BookCopy.Status.DAMAGED},
        )
        self.assertRedirects(response, reverse("copy_list"))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.DAMAGED)
        self.assertTrue(
            AuditLog.objects.filter(
                action="inventory.copy_status_changed",
                target_id=str(self.copy.pk),
                actor=self.librarian,
            ).exists()
        )

    def test_copy_status_change_is_post_only(self):
        self.client.force_login(self.librarian)

        response = self.client.get(reverse("copy_status", args=(self.copy.pk,)))

        self.assertEqual(response.status_code, 405)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)

    def test_copy_status_change_requires_csrf_and_audits_denial(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.librarian)

        response = csrf_client.post(
            reverse("copy_status", args=(self.copy.pk,)),
            {"status": BookCopy.Status.DAMAGED},
        )

        self.assertEqual(response.status_code, 403)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.librarian,
                action="access.denied",
                target_repr=reverse("copy_status", args=(self.copy.pk,)),
            ).exists()
        )

    def test_librarian_can_add_physical_copy_from_copy_form(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("copy_create"),
            {
                "book": self.book.pk,
                "accession_number": "ACC-NEW-002",
                "shelf_location": "C-3",
                "status": BookCopy.Status.AVAILABLE,
                "condition": "New",
                "acquired_date": "2025-01-02",
            },
        )

        self.assertEqual(response.status_code, 302)
        copy = BookCopy.objects.get(accession_number="ACC-NEW-002")
        self.assertEqual(copy.book, self.book)
        self.assertTrue(
            AuditLog.objects.filter(
                action="inventory.copy_created",
                target_id=str(copy.pk),
                actor=self.librarian,
            ).exists()
        )

    def test_catalog_permission_matrix_uses_the_real_book_model_permission(self):
        for role, user in (
            ("Administrator", self.admin),
            ("Librarian", self.librarian),
            ("Faculty", self.faculty),
            ("Student", self.student),
        ):
            with self.subTest(role=role):
                self.assertTrue(user.has_perm("catalog.view_book"))

        for user in (self.admin, self.librarian):
            self.assertTrue(user.has_perm("catalog.manage_catalog"))
            self.assertTrue(user.has_perm("inventory.manage_copies"))
        self.assertTrue(self.admin.has_perm("catalog.delete_book"))
        self.assertFalse(self.librarian.has_perm("catalog.delete_book"))

    def test_invalid_copy_status_form_is_reported_without_mutation(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("copy_status", args=(self.copy.pk,)),
            {"status": "made-up"},
        )

        self.assertRedirects(response, reverse("copy_list"))
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)

    def test_book_and_copy_lists_are_paginated(self):
        for index in range(30, 53):
            self.create_book(index, title=f"Page title {index}")
        self.client.force_login(self.student)

        first_page = self.client.get(reverse("catalog:book_list"))
        second_page = self.client.get(reverse("catalog:book_list"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertTrue(first_page.context["is_paginated"])
        self.assertEqual(len(first_page.context["books"]), 20)
        self.assertEqual(len(second_page.context["books"]), 4)

    def test_catalog_escapes_untrusted_book_titles(self):
        unsafe_title = '<script>alert("xss")</script>'
        Book.objects.filter(pk=self.book.pk).update(title=unsafe_title)
        self.client.force_login(self.student)

        response = self.client.get(reverse("catalog:book_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, unsafe_title)

    def test_detail_copy_list_is_paginated_for_inventory_managers(self):
        for index in range(2, 25):
            self.create_copy(
                self.book,
                accession=f"ACC-PAGE-{index:03d}",
            )
        self.client.force_login(self.librarian)

        first_page = self.client.get(
            reverse("catalog:book_detail", args=(self.book.pk,))
        )
        second_page = self.client.get(
            reverse("catalog:book_detail", args=(self.book.pk,)),
            {"copies_page": 2},
        )

        self.assertEqual(len(first_page.context["copy_page"].object_list), 20)
        self.assertEqual(len(second_page.context["copy_page"].object_list), 4)
