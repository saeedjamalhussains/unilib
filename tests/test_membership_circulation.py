from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.catalog.models import Author, Book, Category, Publisher
from apps.circulation.models import Loan
from apps.circulation.services import issue_copy, renew_loan, return_copy
from apps.fines.models import Fine
from apps.fines.services import record_payment, waive_fine
from apps.inventory.models import BookCopy
from apps.inventory.services import change_copy_status
from apps.membership.models import LibraryPolicy, MemberProfile
from apps.membership.services import get_policy, register_member, save_member, save_policy
from apps.reports.services import export_csv, get_report_rows
from apps.reservations.models import Reservation
from apps.reservations.services import cancel_reservation, expire_holds, place_reservation


def valid_isbn(number):
    body = f"978000000{number:03d}"
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(body))
    return body + str((-total) % 10)


class LibraryWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", stdout=StringIO())
        User = get_user_model()
        cls.users = {}
        for username, role in (
            ("workflow-admin", "Administrator"),
            ("workflow-librarian", "Librarian"),
            ("workflow-student", "Student"),
            ("workflow-student-b", "Student"),
            ("workflow-faculty", "Faculty"),
        ):
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.edu",
                password="safe-test-password-2026",
            )
            user.groups.add(Group.objects.get(name=role))
            cls.users[role + username] = user
        cls.admin = cls.users["Administratorworkflow-admin"]
        cls.librarian = cls.users["Librarianworkflow-librarian"]
        cls.student = cls.users["Studentworkflow-student"]
        cls.student_b = cls.users["Studentworkflow-student-b"]
        cls.faculty = cls.users["Facultyworkflow-faculty"]
        cls.student_profile = MemberProfile.objects.create(
            user=cls.student,
            university_id="STU-001",
            department="Computing",
            member_type=MemberProfile.MemberType.STUDENT,
            status=MemberProfile.Status.ACTIVE,
            membership_expiry=timezone.localdate() + timedelta(days=120),
        )
        cls.student_b_profile = MemberProfile.objects.create(
            user=cls.student_b,
            university_id="STU-002",
            department="Computing",
            member_type=MemberProfile.MemberType.STUDENT,
            status=MemberProfile.Status.ACTIVE,
            membership_expiry=timezone.localdate() + timedelta(days=120),
        )
        cls.faculty_profile = MemberProfile.objects.create(
            user=cls.faculty,
            university_id="FAC-001",
            department="Arts",
            member_type=MemberProfile.MemberType.FACULTY,
            status=MemberProfile.Status.ACTIVE,
            membership_expiry=timezone.localdate() + timedelta(days=120),
        )
        cls.publisher = Publisher.objects.create(name="Workflow Press")
        cls.author = Author.objects.create(name="Workflow Writer")
        cls.category = Category.objects.create(name="Computing")
        cls.book = Book.objects.create(
            title="Transactional Services",
            isbn=valid_isbn(1),
            publisher=cls.publisher,
        )
        cls.book.authors.add(cls.author)
        cls.book.categories.add(cls.category)
        cls.copy = BookCopy.objects.create(
            book=cls.book,
            accession_number="WF-001",
            shelf_location="S-1",
            status=BookCopy.Status.AVAILABLE,
            acquired_date=timezone.localdate(),
        )
        cls.student_policy = LibraryPolicy.objects.get(member_type="student")

    def test_issue_enforces_eligibility_and_audits_copy_and_loan(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        self.copy.refresh_from_db()
        self.assertEqual(loan.due_date, timezone.localdate() + timedelta(days=14))
        self.assertEqual(self.copy.status, BookCopy.Status.ON_LOAN)
        self.assertTrue(
            AuditLog.objects.filter(action="loan.issued", actor=self.librarian).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action="inventory.copy_status_changed", actor=self.librarian
            ).exists()
        )
        with self.assertRaisesMessage(ValidationError, "not available"):
            issue_copy(self.copy, self.student_b_profile, self.librarian)

    def test_issue_rejects_expired_suspended_and_fine_blocked_members(self):
        self.student_profile.status = MemberProfile.Status.SUSPENDED
        self.student_profile.save()
        with self.assertRaisesMessage(ValidationError, "not active"):
            issue_copy(self.copy, self.student_profile, self.librarian)
        self.student_profile.status = MemberProfile.Status.ACTIVE
        self.student_profile.membership_expiry = timezone.localdate() - timedelta(days=1)
        self.student_profile.save()
        with self.assertRaisesMessage(ValidationError, "expired"):
            issue_copy(self.copy, self.student_profile, self.librarian)
        self.student_profile.membership_expiry = timezone.localdate() + timedelta(days=1)
        self.student_profile.save()
        self.student_policy.fine_block_threshold = Decimal("0.50")
        self.student_policy.save()
        loan = Loan.objects.create(
            copy=BookCopy.objects.create(
                book=self.book,
                accession_number="WF-FINE",
                shelf_location="S-2",
                acquired_date=timezone.localdate(),
                status=BookCopy.Status.ON_LOAN,
            ),
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        Fine.objects.create(
            loan=loan,
            member=self.student_profile,
            amount=Decimal("1.00"),
            reason=Fine.Reason.OVERDUE,
        )
        with self.assertRaisesMessage(ValidationError, "outstanding fines"):
            issue_copy(self.copy, self.student_profile, self.librarian)

    def test_issue_rejects_member_at_active_loan_limit_and_fulfils_ready_hold(self):
        existing_loan = Loan.objects.create(
            copy=BookCopy.objects.create(
                book=self.book,
                accession_number="WF-LIMIT",
                shelf_location="S-2",
                acquired_date=timezone.localdate(),
                status=BookCopy.Status.ON_LOAN,
            ),
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        self.student_policy.max_active_loans = 1
        self.student_policy.save()
        with self.assertRaisesMessage(ValidationError, "active-loan limit"):
            issue_copy(self.copy, self.student_profile, self.librarian)
        existing_loan.returned_at = timezone.now()
        existing_loan.save(update_fields=("returned_at",))
        self.copy.status = BookCopy.Status.ON_HOLD
        self.copy.save(update_fields=("status",))
        reservation = Reservation.objects.create(
            book=self.book,
            member=self.student_profile,
            status=Reservation.Status.READY,
            ready_copy=self.copy,
            hold_expires_at=timezone.now() + timedelta(hours=12),
        )
        issued = issue_copy(self.copy, self.student_profile, self.librarian)
        reservation.refresh_from_db()
        self.assertEqual(issued.copy, self.copy)
        self.assertEqual(reservation.status, Reservation.Status.FULFILLED)

    def test_copy_status_service_preserves_circulation_invariants(self):
        with self.assertRaisesMessage(ValidationError, "marked on loan through circulation"):
            change_copy_status(self.librarian, self.copy, BookCopy.Status.ON_LOAN)
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        with self.assertRaisesMessage(ValidationError, "active loan"):
            change_copy_status(self.librarian, self.copy, BookCopy.Status.DAMAGED)
        loan.returned_at = timezone.now()
        loan.save(update_fields=("returned_at",))
        change_copy_status(self.librarian, self.copy, BookCopy.Status.DAMAGED)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.DAMAGED)

    def test_last_available_copy_is_preserved_for_another_member_reservation(self):
        Reservation.objects.create(book=self.book, member=self.student_b_profile)
        with self.assertRaisesMessage(ValidationError, "last available"):
            issue_copy(self.copy, self.student_profile, self.librarian)

    def test_return_assesses_capped_fine_and_marks_copy_available(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        loan.due_date = timezone.localdate() - timedelta(days=20)
        loan.save(update_fields=("due_date",))
        self.student_policy.max_fine_per_loan = Decimal("1.00")
        self.student_policy.save()
        returned = return_copy(loan, self.librarian)
        self.copy.refresh_from_db()
        fine = Fine.objects.get(loan=returned)
        self.assertEqual(fine.amount, Decimal("1.00"))
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)
        self.assertIsNotNone(returned.returned_at)

    def test_return_reserves_first_pending_queue_entry_and_grace_boundary(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        loan.due_date = timezone.localdate() - timedelta(days=1)
        loan.save(update_fields=("due_date",))
        reservation = Reservation.objects.create(book=self.book, member=self.student_b_profile)
        queued = Reservation.objects.create(book=self.book, member=self.faculty_profile)
        return_copy(loan, self.librarian)
        self.copy.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.ON_HOLD)
        self.assertEqual(reservation.status, Reservation.Status.READY)
        queued.refresh_from_db()
        self.assertEqual(queued.status, Reservation.Status.PENDING)
        self.assertIsNotNone(reservation.hold_expires_at)
        self.assertFalse(Fine.objects.filter(loan=loan).exists())

    def test_staff_can_return_by_member_id_when_only_one_loan_matches(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        self.client.force_login(self.librarian)
        response = self.client.post(
            reverse("return_copy"),
            {"university_id": self.student_profile.university_id},
        )
        self.assertEqual(response.status_code, 302)
        loan.refresh_from_db()
        self.assertIsNotNone(loan.returned_at)

    def test_renewal_increments_count_and_blocks_pending_reservation(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        due_before = loan.due_date
        renewed = renew_loan(loan, self.student)
        self.assertEqual(renewed.renewals_count, 1)
        self.assertEqual(renewed.due_date, due_before + timedelta(days=7))
        Reservation.objects.create(book=self.book, member=self.student_b_profile)
        with self.assertRaisesMessage(ValidationError, "pending reservations"):
            renew_loan(renewed, self.student)

    def test_renewal_rejects_overdue_returned_inactive_and_exhausted_loans(self):
        loan = issue_copy(self.copy, self.student_profile, self.librarian)
        loan.due_date = timezone.localdate() - timedelta(days=1)
        loan.save(update_fields=("due_date",))
        with self.assertRaisesMessage(ValidationError, "overdue"):
            renew_loan(loan, self.student)
        loan.due_date = timezone.localdate()
        loan.renewals_count = self.student_policy.max_renewals
        loan.save(update_fields=("due_date", "renewals_count"))
        with self.assertRaisesMessage(ValidationError, "maximum number"):
            renew_loan(loan, self.student)
        loan.renewals_count = 0
        loan.save(update_fields=("renewals_count",))
        self.student_profile.status = MemberProfile.Status.SUSPENDED
        self.student_profile.save(update_fields=("status",))
        with self.assertRaisesMessage(ValidationError, "not active"):
            renew_loan(loan, self.student)
        loan.returned_at = timezone.now()
        loan.save(update_fields=("returned_at",))
        with self.assertRaisesMessage(ValidationError, "returned loan"):
            renew_loan(loan, self.student)

    def test_reservation_requires_unavailable_title_and_can_be_cancelled(self):
        with self.assertRaisesMessage(ValidationError, "currently available"):
            place_reservation(self.book, self.student_profile)
        self.copy.status = BookCopy.Status.ON_LOAN
        self.copy.save(update_fields=("status",))
        reservation = place_reservation(self.book, self.student_profile)
        cancel_reservation(reservation, self.student)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)

    def test_expiring_hold_advances_copy_and_is_idempotent(self):
        self.copy.status = BookCopy.Status.ON_HOLD
        self.copy.save(update_fields=("status",))
        reservation = Reservation.objects.create(
            book=self.book,
            member=self.student_profile,
            status=Reservation.Status.READY,
            ready_copy=self.copy,
            hold_expires_at=timezone.now() - timedelta(hours=1),
        )
        ids = expire_holds()
        reservation.refresh_from_db()
        self.copy.refresh_from_db()
        self.assertEqual(ids, [reservation.pk])
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)
        self.assertEqual(expire_holds(), [])

    def test_expiring_hold_advances_to_next_member_in_queue(self):
        Reservation.objects.create(
            book=self.book,
            member=self.student_profile,
            status=Reservation.Status.READY,
            ready_copy=self.copy,
            hold_expires_at=timezone.now() - timedelta(hours=2),
        )
        waiting = Reservation.objects.create(book=self.book, member=self.student_b_profile)
        expire_holds()
        waiting.refresh_from_db()
        self.copy.refresh_from_db()
        self.assertEqual(waiting.status, Reservation.Status.READY)
        self.assertEqual(waiting.ready_copy, self.copy)
        self.assertEqual(self.copy.status, BookCopy.Status.ON_HOLD)

    def test_partial_payment_never_overpays_and_waiver_requires_reason(self):
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        fine = Fine.objects.create(
            loan=loan,
            member=self.student_profile,
            amount=Decimal("10.00"),
            reason=Fine.Reason.DAMAGED,
        )
        record_payment(fine, Decimal("4.00"), self.librarian)
        self.assertEqual(fine.balance, Decimal("6.00"))
        with self.assertRaisesMessage(ValidationError, "exceeds"):
            record_payment(fine, Decimal("7.00"), self.librarian)
        record_payment(fine, Decimal("6.00"), self.librarian)
        fine.refresh_from_db()
        self.assertEqual(fine.status, Fine.Status.PAID)
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            waive_fine(fine, self.admin, "")

    def test_waiver_is_admin_only_and_audited(self):
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        fine = Fine.objects.create(
            loan=loan,
            member=self.student_profile,
            amount=Decimal("2.00"),
            reason=Fine.Reason.LOST,
        )
        with self.assertRaises(PermissionDenied):
            waive_fine(fine, self.librarian, "Goodwill")
        waive_fine(fine, self.admin, "Approved by administrator")
        fine.refresh_from_db()
        self.assertEqual(fine.status, Fine.Status.WAIVED)
        self.assertTrue(AuditLog.objects.filter(action="fine.waived", actor=self.admin).exists())

    def test_membership_policy_changes_are_audited(self):
        self.student_policy.loan_days = 15
        save_policy(self.admin, self.student_policy)
        event = AuditLog.objects.get(action="membership.policy_updated")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.metadata["after"]["loan_days"], "15")

    def test_member_registration_assigns_role_and_update_is_audited(self):
        profile = MemberProfile(
            university_id="STU-NEW",
            department="Physics",
            member_type=MemberProfile.MemberType.STUDENT,
            status=MemberProfile.Status.ACTIVE,
            membership_expiry=timezone.localdate() + timedelta(days=30),
        )
        created = register_member(
            self.admin,
            profile,
            username="registered-student",
            email="registered-student@example.edu",
            password="Registered-Account-Password-2026",
        )
        self.assertTrue(created.user.groups.filter(name="Student").exists())
        created.department = "Mathematics"
        save_member(self.admin, created)
        self.assertTrue(
            AuditLog.objects.filter(
                action="membership.member_updated", target_id=str(created.pk)
            ).exists()
        )

    def test_policy_lookup_reports_missing_configuration(self):
        with self.assertRaisesMessage(ValidationError, "No library policy"):
            get_policy("unknown")

    def test_all_report_types_and_date_filter_validation(self):
        self.copy.status = BookCopy.Status.ON_LOAN
        self.copy.save(update_fields=("status",))
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate() - timedelta(days=2),
        )
        Fine.objects.create(
            loan=loan,
            member=self.student_profile,
            amount=Decimal("5.00"),
            reason=Fine.Reason.OVERDUE,
        )
        self.assertTrue(get_report_rows("inventory"))
        self.assertEqual(len(get_report_rows("active_loans")), 1)
        self.assertEqual(len(get_report_rows("overdue_loans")), 1)
        circulation = get_report_rows(
            "circulation",
            start_date=timezone.localdate() - timedelta(days=5),
            end_date=timezone.localdate(),
            category=self.category.name,
        )
        self.assertEqual(circulation[0]["loan_count"], 1)
        self.assertEqual(len(get_report_rows("most_borrowed")), 1)
        self.assertEqual(len(get_report_rows("outstanding_fines")), 1)
        with self.assertRaisesMessage(ValidationError, "valid report"):
            get_report_rows("unknown")
        with self.assertRaisesMessage(ValidationError, "Start date"):
            get_report_rows(
                "circulation",
                start_date=timezone.localdate(),
                end_date=timezone.localdate() - timedelta(days=1),
            )

    def test_report_page_and_dashboard_pages_render(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("my_profile")).status_code, 200)
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("report_index"), {"report": "inventory"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse("report_index"), {"report": "inventory", "format": "csv"}
        )
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertTrue(AuditLog.objects.filter(action="reports.csv_exported").exists())
        self.client.force_login(self.admin)
        for url_name in (
            "member_list",
            "policy_list",
            "all_loans",
            "reservation_list",
            "fine_list",
            "audit_list",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_private_lists_scope_records_and_foreign_ids_are_404(self):
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_b_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        reservation = Reservation.objects.create(book=self.book, member=self.student_b_profile)
        fine = Fine.objects.create(
            loan=loan,
            member=self.student_b_profile,
            amount=Decimal("1.00"),
            reason=Fine.Reason.OVERDUE,
        )
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("my_loans")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("my_fines")), "STU-002")
        self.assertEqual(self.client.post(reverse("renew_loan", args=(loan.pk,))).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("cancel_reservation", args=(reservation.pk,))).status_code, 404
        )
        for url_name in (
            "member_list",
            "all_loans",
            "reservation_list",
            "fine_list",
            "report_index",
            "copy_list",
            "audit_list",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)
        self.assertEqual(self.client.get(reverse("my_profile")).status_code, 200)
        self.client.force_login(self.student_b)
        self.assertEqual(self.client.get(reverse("my_fines")).status_code, 200)
        self.assertEqual(fine.member.user, self.student_b)

    def test_missing_csrf_token_rejects_state_changing_routes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        loan = Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        reservation = Reservation.objects.create(book=self.book, member=self.student_b_profile)
        fine = Fine.objects.create(
            loan=loan,
            member=self.student_profile,
            amount=Decimal("1.00"),
            reason=Fine.Reason.DAMAGED,
        )
        paths = (
            reverse("logout"),
            reverse("manage_user_create"),
            reverse("manage_user_deactivate", args=(self.student.pk,)),
            reverse("manage_user_activate", args=(self.student.pk,)),
            reverse("member_create"),
            reverse("member_edit", args=(self.student_profile.pk,)),
            reverse("policy_create"),
            reverse("policy_edit", args=(self.student_policy.pk,)),
            reverse("catalog:book_create"),
            reverse("catalog:book_update", args=(self.book.pk,)),
            reverse("catalog:book_delete", args=(self.book.pk,)),
            reverse("copy_create"),
            reverse("copy_update", args=(self.copy.pk,)),
            reverse("copy_status", args=(self.copy.pk,)),
            reverse("issue_copy"),
            reverse("return_copy"),
            reverse("renew_loan", args=(loan.pk,)),
            reverse("place_reservation"),
            reverse("cancel_reservation", args=(reservation.pk,)),
            reverse("fine_payment", args=(fine.pk,)),
            reverse("fine_waive", args=(fine.pk,)),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(client.post(path).status_code, 403)

    def test_database_constraint_prevents_two_active_loans_for_one_copy(self):
        Loan.objects.create(
            copy=self.copy,
            member=self.student_profile,
            issued_by=self.librarian,
            due_date=timezone.localdate(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Loan.objects.create(
                copy=self.copy,
                member=self.student_b_profile,
                issued_by=self.librarian,
                due_date=timezone.localdate(),
            )

    def test_rollback_removes_domain_change_and_audit_event(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            issue_copy(self.copy, self.student_profile, self.librarian)
            raise RuntimeError("rollback test")
        self.assertFalse(Loan.objects.filter(copy=self.copy).exists())
        self.assertFalse(AuditLog.objects.filter(action="loan.issued").exists())


class CsvExportTests(TestCase):
    def test_formula_cells_are_neutralized(self):
        output = export_csv(
            [
                {"name": "=SUM(A1:A2)", "category": "+cmd"},
                {"name": "-10+1", "category": "@formula"},
            ]
        )
        self.assertIn("'=SUM(A1:A2)", output)
        self.assertIn("'+cmd", output)
        self.assertIn("'-10+1", output)
        self.assertIn("'@formula", output)


class LoginThrottleTests(TestCase):
    def test_repeated_invalid_passwords_are_throttled(self):
        for attempt in range(5):
            response = self.client.post(
                reverse("login"),
                {"username": "not-a-user", "password": "invalid"},
                REMOTE_ADDR="192.0.2.50",
            )
            self.assertEqual(response.status_code, 200, attempt)
        response = self.client.post(
            reverse("login"),
            {"username": "not-a-user", "password": "invalid"},
            REMOTE_ADDR="192.0.2.50",
        )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(AuditLog.objects.filter(action="auth.login_locked").exists())
