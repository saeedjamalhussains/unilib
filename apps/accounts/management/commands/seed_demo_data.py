import os
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Author, Book, Category, Publisher
from apps.circulation.models import Loan
from apps.fines.models import Fine
from apps.inventory.models import BookCopy
from apps.membership.models import MemberProfile
from apps.reservations.models import Reservation


class Command(BaseCommand):
    help = "Create repeatable development accounts and library sample data."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo_data is available only when DEBUG=True.")
        User = get_user_model()
        account_roles = (
            ("demo_admin", "Administrator"),
            ("demo_librarian", "Librarian"),
            ("demo_faculty", "Faculty"),
            ("demo_student", "Student"),
        )
        generated_credentials = {}
        configured_password = os.environ.get("DEMO_PASSWORD")
        with transaction.atomic():
            groups = {role: Group.objects.get(name=role) for _, role in account_roles}
            users = {}
            for username, role in account_roles:
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@example.invalid",
                        "is_active": True,
                    },
                )
                if created:
                    password = configured_password or secrets.token_urlsafe(18)
                    validate_password(password, user=user)
                    user.set_password(password)
                    user.save(update_fields=("password",))
                    if not configured_password:
                        generated_credentials[username] = password
                user.groups.set((groups[role],))
                users[role] = user

            publisher, _ = Publisher.objects.get_or_create(name="University Press")
            author, _ = Author.objects.get_or_create(name="Demo Author")
            category, _ = Category.objects.get_or_create(name="General")
            today = timezone.localdate()
            for number in range(1, 31):
                isbn = self._isbn(number)
                book, _ = Book.objects.get_or_create(
                    isbn=isbn,
                    defaults={
                        "title": f"University Library Sample Book {number:02d}",
                        "edition": "1",
                        "publication_year": 2024,
                        "publisher": publisher,
                        "description": "Sample catalog record for local development.",
                        "price": Decimal("25.00"),
                    },
                )
                book.authors.add(author)
                book.categories.add(category)
                for copy_number in range(1, 4):
                    BookCopy.objects.get_or_create(
                        accession_number=f"DEMO-{number:02d}-{copy_number}",
                        defaults={
                            "book": book,
                            "shelf_location": f"A-{number:02d}",
                            "status": BookCopy.Status.AVAILABLE,
                            "condition": "Good",
                            "acquired_date": today,
                        },
                    )
            student, _ = MemberProfile.objects.get_or_create(
                user=users["Student"],
                defaults={
                    "university_id": "DEMO-STUDENT-001",
                    "department": "Computer Science",
                    "member_type": MemberProfile.MemberType.STUDENT,
                    "status": MemberProfile.Status.ACTIVE,
                    "membership_expiry": today + timedelta(days=365),
                },
            )
            faculty, _ = MemberProfile.objects.get_or_create(
                user=users["Faculty"],
                defaults={
                    "university_id": "DEMO-FACULTY-001",
                    "department": "Library Science",
                    "member_type": MemberProfile.MemberType.FACULTY,
                    "status": MemberProfile.Status.ACTIVE,
                    "membership_expiry": today + timedelta(days=365),
                },
            )
            overdue_copy = BookCopy.objects.get(accession_number="DEMO-01-1")
            if not Loan.objects.filter(copy=overdue_copy, returned_at__isnull=True).exists():
                overdue_copy.status = BookCopy.Status.ON_LOAN
                overdue_copy.save(update_fields=("status", "updated_at"))
                loan = Loan.objects.create(
                    copy=overdue_copy,
                    member=student,
                    issued_by=users["Librarian"],
                    due_date=today - timedelta(days=8),
                )
                Fine.objects.get_or_create(
                    loan=loan,
                    defaults={
                        "member": student,
                        "amount": Decimal("2.00"),
                        "reason": Fine.Reason.OVERDUE,
                    },
                )
            for copy in BookCopy.objects.filter(book__isbn=self._isbn(2)):
                if not Loan.objects.filter(copy=copy, returned_at__isnull=True).exists():
                    copy.status = BookCopy.Status.ON_LOAN
                    copy.save(update_fields=("status", "updated_at"))
                    Loan.objects.create(
                        copy=copy,
                        member=faculty,
                        issued_by=users["Librarian"],
                        due_date=today + timedelta(days=20),
                    )
            if not Reservation.objects.filter(
                book_id=Book.objects.get(isbn=self._isbn(2)).pk,
                member=student,
                status__in=(Reservation.Status.PENDING, Reservation.Status.READY),
            ).exists():
                Reservation.objects.create(
                    book=Book.objects.get(isbn=self._isbn(2)),
                    member=student,
                    status=Reservation.Status.PENDING,
                )
        if generated_credentials:
            self.stdout.write(
                self.style.WARNING("Generated passwords for newly created demo accounts:")
            )
            for username, password in generated_credentials.items():
                self.stdout.write(f"  {username}: {password}")
        elif configured_password:
            self.stdout.write("Created demo accounts using DEMO_PASSWORD.")
        self.stdout.write(self.style.SUCCESS("Demo accounts and sample library data are ready."))

    @staticmethod
    def _isbn(number):
        body = f"978{number:09d}"
        checksum = sum(
            int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(body)
        )
        return body + str((-checksum) % 10)
