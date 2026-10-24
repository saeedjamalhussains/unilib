from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.services import (
    activate_user,
    assign_role,
    create_account,
    deactivate_user,
    delete_account,
    update_account,
)
from apps.audit.models import AuditLog


class AccountManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", stdout=StringIO())
        cls.User = get_user_model()
        cls.admin = cls.User.objects.create_user(
            username="administrator",
            email="administrator@example.edu",
            password="Long-Unique-Admin-Password-2026!",
        )
        cls.admin.groups.add(Group.objects.get(name="Administrator"))
        cls.librarian = cls.User.objects.create_user(
            username="librarian",
            email="librarian@example.edu",
            password="Long-Unique-Librarian-Password-2026!",
        )
        cls.librarian.groups.add(Group.objects.get(name="Librarian"))
        cls.student = cls.User.objects.create_user(
            username="student",
            email="student@example.edu",
            password="Long-Unique-Student-Password-2026!",
        )
        cls.student.groups.add(Group.objects.get(name="Student"))

    def make_user(self, username, role, *, active=True):
        user = self.User.objects.create_user(
            username=username,
            email=f"{username}@example.edu",
            password="Long-Unique-User-Password-2026!",
            is_active=active,
        )
        user.groups.add(Group.objects.get(name=role))
        return user

    def test_admin_creates_any_role_and_audits_creation_and_role(self):
        user = create_account(
            self.admin,
            username="new-librarian",
            email="new-librarian@example.edu",
            first_name="New",
            last_name="Librarian",
            password="Long-Unique-New-Password-2026!",
            role="Librarian",
        )

        self.assertEqual(set(user.groups.values_list("name", flat=True)), {"Librarian"})
        self.assertTrue(user.check_password("Long-Unique-New-Password-2026!"))
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.admin,
                target_id=str(user.pk),
                action__in=("accounts.user_created", "accounts.role_assigned"),
            ).count(),
            2,
        )

    def test_librarian_can_create_only_faculty_and_student_accounts(self):
        created = create_account(
            self.librarian,
            username="new-faculty",
            email="new-faculty@example.edu",
            password="Long-Unique-Faculty-Password-2026!",
            role="Faculty",
        )

        self.assertEqual(set(created.groups.values_list("name", flat=True)), {"Faculty"})
        for role in ("Administrator", "Librarian"):
            with self.subTest(role=role), self.assertRaises(PermissionDenied):
                create_account(
                    self.librarian,
                    username=f"forbidden-{role.lower()}",
                    email=f"forbidden-{role.lower()}@example.edu",
                    password="Long-Unique-Forbidden-Password-2026!",
                    role=role,
                )
        self.assertFalse(self.User.objects.filter(username="forbidden-administrator").exists())

    def test_librarian_can_create_a_student_from_the_staff_form(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("manage_user_create"),
            {
                "username": "created-student",
                "email": "created-student@example.edu",
                "first_name": "Created",
                "last_name": "Student",
                "role": "Student",
                "password1": "Long-Unique-Created-Password-2026!",
                "password2": "Long-Unique-Created-Password-2026!",
            },
        )

        self.assertRedirects(response, reverse("manage_user_list"))
        created = self.User.objects.get(username="created-student")
        self.assertEqual(set(created.groups.values_list("name", flat=True)), {"Student"})
        self.assertEqual(
            AuditLog.objects.filter(
                actor=self.librarian,
                target_id=str(created.pk),
                action__in=("accounts.user_created", "accounts.role_assigned"),
            ).count(),
            2,
        )

    def test_librarian_cannot_edit_or_reassign_privileged_accounts(self):
        with self.assertRaises(PermissionDenied):
            update_account(
                self.librarian,
                self.admin,
                username=self.admin.username,
                email=self.admin.email,
                first_name="Changed",
            )
        with self.assertRaises(PermissionDenied):
            assign_role(self.librarian, self.student, "Faculty")

    def test_admin_can_change_another_users_role_and_audit_previous_role(self):
        assign_role(self.admin, self.student, "Faculty")

        self.student.refresh_from_db()
        self.assertEqual(set(self.student.groups.values_list("name", flat=True)), {"Faculty"})
        event = AuditLog.objects.get(
            action="accounts.role_changed",
            target_id=str(self.student.pk),
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.metadata["previous_roles"], ["Student"])
        self.assertEqual(event.metadata["role"], "Faculty")

    def test_no_user_can_change_their_own_role(self):
        with self.assertRaises(PermissionDenied):
            assign_role(self.admin, self.admin, "Librarian")

    def test_last_active_administrator_cannot_be_demoted_deactivated_or_deleted(self):
        actor = self.make_user("superuser-operator", "Student")
        actor.is_superuser = True
        actor.save(update_fields=("is_superuser",))
        with self.assertRaisesMessage(ValidationError, "last active administrator"):
            assign_role(actor, self.admin, "Librarian")
        with self.assertRaisesMessage(ValidationError, "last active administrator"):
            deactivate_user(actor, self.admin)
        with self.assertRaisesMessage(ValidationError, "last active administrator"):
            delete_account(actor, self.admin)

    def test_role_form_reports_last_administrator_protection_without_partial_update(self):
        actor = self.make_user("superuser-operator", "Student")
        actor.is_superuser = True
        actor.save(update_fields=("is_superuser",))
        self.client.force_login(actor)

        response = self.client.post(
            reverse("manage_user_edit", args=(self.admin.pk,)),
            {
                "username": self.admin.username,
                "email": self.admin.email,
                "first_name": self.admin.first_name,
                "last_name": "Should Roll Back",
                "role": "Librarian",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "last active administrator")
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.last_name, "Should Roll Back")
        self.assertEqual(set(self.admin.groups.values_list("name", flat=True)), {"Administrator"})

    def test_active_administrator_can_be_demoted_when_another_remains(self):
        another_admin = self.make_user("second-admin", "Administrator")

        assign_role(self.admin, another_admin, "Librarian")

        another_admin.refresh_from_db()
        self.assertEqual(set(another_admin.groups.values_list("name", flat=True)), {"Librarian"})

    def test_users_cannot_deactivate_themselves(self):
        with self.assertRaises(PermissionDenied):
            deactivate_user(self.admin, self.admin)

    def test_librarian_can_reactivate_member_and_audit_it(self):
        target = self.make_user("inactive-student", "Student", active=False)

        activated = activate_user(self.librarian, target)

        self.assertTrue(activated.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.librarian,
                action="accounts.user_activated",
                target_id=str(target.pk),
            ).exists()
        )

    def test_account_activation_is_post_only(self):
        target = self.make_user("inactive-student", "Student", active=False)
        self.client.force_login(self.librarian)

        response = self.client.get(
            reverse("manage_user_activate", args=(target.pk,))
        )

        self.assertEqual(response.status_code, 405)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_self_deactivation_forbidden_response_is_audited(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("manage_user_deactivate", args=(self.admin.pk,))
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action="access.denied",
                target_repr=reverse(
                    "manage_user_deactivate", args=(self.admin.pk,)
                ),
            ).exists()
        )

    def test_librarian_can_edit_member_account_without_changing_role(self):
        updated = update_account(
            self.librarian,
            self.student,
            username=self.student.username,
            email=self.student.email,
            first_name="Updated",
            last_name="Student",
        )

        self.assertEqual(updated.first_name, "Updated")
        self.assertEqual(set(updated.groups.values_list("name", flat=True)), {"Student"})
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.librarian,
                action="accounts.user_updated",
                target_id=str(updated.pk),
            ).exists()
        )

    def test_admin_can_assign_role_in_edit_form(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("manage_user_edit", args=(self.student.pk,)),
            {
                "username": self.student.username,
                "email": self.student.email,
                "first_name": self.student.first_name,
                "last_name": self.student.last_name,
                "role": "Faculty",
            },
        )

        self.assertRedirects(response, reverse("manage_user_list"))
        self.student.refresh_from_db()
        self.assertEqual(set(self.student.groups.values_list("name", flat=True)), {"Faculty"})

    def test_admin_can_edit_own_details_without_resubmitting_role(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("manage_user_edit", args=(self.admin.pk,)),
            {
                "username": self.admin.username,
                "email": self.admin.email,
                "first_name": "Admin",
                "last_name": "Updated",
                "role": "",
            },
        )

        self.assertRedirects(response, reverse("manage_user_list"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.last_name, "Updated")
        self.assertEqual(set(self.admin.groups.values_list("name", flat=True)), {"Administrator"})

    def test_librarian_forged_role_field_is_ignored_on_member_edit(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("manage_user_edit", args=(self.student.pk,)),
            {
                "username": self.student.username,
                "email": self.student.email,
                "first_name": self.student.first_name,
                "last_name": self.student.last_name,
                "role": "Faculty",
            },
        )

        self.assertRedirects(response, reverse("manage_user_list"))
        self.student.refresh_from_db()
        self.assertEqual(set(self.student.groups.values_list("name", flat=True)), {"Student"})

    def test_librarian_cannot_deactivate_or_delete_privileged_accounts(self):
        with self.assertRaises(PermissionDenied):
            deactivate_user(self.librarian, self.admin)
        with self.assertRaises(PermissionDenied):
            delete_account(self.librarian, self.student)

    def test_account_routes_are_scoped_and_protected(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("manage_user_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student")
        self.assertNotContains(response, "administrator")

        self.client.force_login(self.student)
        response = self.client.get(reverse("manage_user_list"))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.student,
                action="access.denied",
                outcome="denied",
            ).exists()
        )

    def test_librarian_forged_role_post_cannot_create_administrator(self):
        self.client.force_login(self.librarian)

        response = self.client.post(
            reverse("manage_user_create"),
            {
                "username": "forged-admin",
                "email": "forged-admin@example.edu",
                "first_name": "",
                "last_name": "",
                "role": "Administrator",
                "password1": "Long-Unique-Forged-Password-2026!",
                "password2": "Long-Unique-Forged-Password-2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(username="forged-admin").exists())

    def test_deactivation_requires_confirming_post(self):
        target = self.make_user("temporary-student", "Student")
        self.client.force_login(self.librarian)

        confirm_response = self.client.get(
            reverse("manage_user_deactivate", args=(target.pk,))
        )
        self.assertEqual(confirm_response.status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

        post_response = self.client.post(
            reverse("manage_user_deactivate", args=(target.pk,))
        )
        self.assertRedirects(post_response, reverse("manage_user_list"))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                action="accounts.user_deactivated",
                target_id=str(target.pk),
                actor=self.librarian,
            ).exists()
        )
