from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.role_matrix import CAPABILITIES, ROLES, matrix_markdown
from apps.audit.models import AuditLog
from apps.audit.site import LibraryAdminSite
from apps.core.mixins import LibraryPermissionRequiredMixin


@override_settings(
    ROOT_URLCONF="tests.permission_urls",
    LOGIN_URL="/accounts/login/",
)
class RoleMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", verbosity=0)

    def test_matrix_document_matches_canonical_permissions(self):
        path = Path(__file__).resolve().parents[1] / "docs" / "RBAC_MATRIX.md"
        self.assertEqual(path.read_text(encoding="utf-8"), matrix_markdown())

    def test_seeded_group_permissions_match_every_matrix_entry(self):
        for capability in CAPABILITIES:
            app_label, codename = capability.permission.split(".", maxsplit=1)
            for role in ROLES:
                with self.subTest(permission=capability.permission, role=role):
                    has_permission = Group.objects.get(name=role).permissions.filter(
                        content_type__app_label=app_label,
                        codename=codename,
                    ).exists()
                    self.assertEqual(has_permission, role in capability.roles)

    def test_seed_command_reconciles_permission_drift_idempotently(self):
        admin_group = Group.objects.get(name="Administrator")
        admin_group.permissions.clear()

        call_command("seed_roles", verbosity=0)
        first_permission_ids = set(
            Group.objects.get(name="Administrator").permissions.values_list("pk", flat=True)
        )
        call_command("seed_roles", verbosity=0)
        second_permission_ids = set(
            Group.objects.get(name="Administrator").permissions.values_list("pk", flat=True)
        )

        self.assertEqual(first_permission_ids, second_permission_ids)
        self.assertEqual(
            len(first_permission_ids),
            sum("Administrator" in capability.roles for capability in CAPABILITIES),
        )

    def test_role_permission_controls_protected_view_for_all_roles(self):
        for role in ROLES:
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(
                    username=f"user-{role.lower()}",
                    email=f"{role.lower()}@example.edu",
                    password="long-test-password",
                )
                user.groups.add(Group.objects.get(name=role))
                self.client.force_login(user)

                response = self.client.get(reverse("protected"))
                expected = 200 if role in ("Administrator", "Librarian", "Faculty", "Student") else 403

                self.assertEqual(response.status_code, expected)

    def test_anonymous_protected_request_redirects_to_login(self):
        response = self.client.get(reverse("protected"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"/accounts/login/?next={reverse('protected')}",
        )

    def test_authenticated_permission_denial_is_audited(self):
        user = get_user_model().objects.create_user(
            username="no-role",
            email="no-role@example.edu",
            password="long-test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("protected"))

        self.assertEqual(response.status_code, 403)
        event = AuditLog.objects.get(action="access.denied")
        self.assertEqual(event.actor, user)
        self.assertEqual(event.outcome, AuditLog.OUTCOME_DENIED)
        self.assertEqual(event.target_repr, reverse("protected"))

    def test_permission_decorator_allows_authorized_users_and_audits_denials(self):
        administrator = get_user_model().objects.create_user(
            username="decorator-admin",
            email="decorator-admin@example.edu",
            password="long-test-password",
        )
        administrator.groups.add(Group.objects.get(name="Administrator"))
        self.client.force_login(administrator)
        self.assertEqual(self.client.get(reverse("decorated_protected")).status_code, 200)

        student = get_user_model().objects.create_user(
            username="decorator-student",
            email="decorator-student@example.edu",
            password="long-test-password",
        )
        student.groups.add(Group.objects.get(name="Student"))
        self.client.force_login(student)
        response = self.client.get(reverse("decorated_protected"))

        self.assertEqual(response.status_code, 403)
        event = AuditLog.objects.get(
            action="access.denied",
            actor=student,
            target_repr=reverse("decorated_protected"),
        )
        self.assertEqual(event.outcome, AuditLog.OUTCOME_DENIED)


class AuditLogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reader",
            email="reader@example.edu",
            password="long-test-password",
        )

    def test_login_success_is_audited_with_actor_and_request_metadata(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "long-test-password"},
            HTTP_USER_AGENT="Foundation test client",
            REMOTE_ADDR="192.0.2.15",
        )

        self.assertEqual(response.status_code, 302)
        event = AuditLog.objects.get(action="auth.login")
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.ip_address, "192.0.2.15")
        self.assertEqual(event.user_agent, "Foundation test client")

    def test_login_failure_records_username_but_never_password(self):
        self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "not-the-password"},
        )

        event = AuditLog.objects.get(action="auth.login_failed")
        self.assertEqual(event.outcome, AuditLog.OUTCOME_FAILED)
        self.assertEqual(event.metadata, {"username": self.user.username})
        self.assertNotIn("password", str(event.metadata))

    def test_logout_is_audited(self):
        self.client.force_login(self.user)

        self.client.post(reverse("logout"))

        event = AuditLog.objects.get(action="auth.logout")
        self.assertEqual(event.actor, self.user)

    def test_password_change_is_audited(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "long-test-password",
                "new_password1": "different-longer-password-2026",
                "new_password2": "different-longer-password-2026",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            AuditLog.objects.filter(
                action="auth.password_changed",
                actor=self.user,
            ).count(),
            1,
        )

    def test_audit_entries_reject_updates_and_deletes(self):
        event = AuditLog.objects.create(action="test.event", outcome="success")

        event.action = "changed"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=event.pk).update(action="changed")
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=event.pk).delete()
        self.assertEqual(AuditLog.objects.get(pk=event.pk).action, "test.event")

    def test_audit_insert_rolls_back_with_outer_transaction(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            AuditLog.objects.create(action="rolled.back", outcome="success")
            raise RuntimeError("rollback")

        self.assertFalse(AuditLog.objects.filter(action="rolled.back").exists())

    def test_admin_site_is_limited_to_superusers_and_administrators(self):
        from django.test import RequestFactory

        site = LibraryAdminSite()
        request = RequestFactory().get("/admin/")
        request.user = self.user
        self.assertFalse(site.has_permission(request))

        self.user.groups.add(Group.objects.create(name="Administrator"))
        self.assertTrue(site.has_permission(request))

        self.user.groups.clear()
        self.user.is_superuser = True
        self.assertTrue(site.has_permission(request))


class DenyByDefaultUrlTests(TestCase):
    PUBLIC_AUTH_VIEWS = frozenset({
        "login",
        "logout",
        "password_reset",
        "password_reset_done",
        "password_reset_confirm",
        "password_reset_complete",
    })

    def test_every_project_url_is_public_allowlisted_or_explicitly_protected(self):
        unresolved = []

        def inspect_patterns(patterns, parent_namespace=""):
            for pattern in patterns:
                namespace = parent_namespace
                if isinstance(pattern, URLResolver):
                    if pattern.namespace == "admin":
                        continue
                    namespace = pattern.namespace or namespace
                    inspect_patterns(pattern.url_patterns, namespace)
                    continue
                if not isinstance(pattern, URLPattern):
                    continue

                callback = pattern.callback
                name = pattern.name
                if name in self.PUBLIC_AUTH_VIEWS:
                    continue
                view_class = getattr(callback, "view_class", None)
                if view_class is not None and issubclass(
                    view_class, (LoginRequiredMixin, LibraryPermissionRequiredMixin)
                ):
                    continue
                if hasattr(callback, "login_url"):
                    continue
                unresolved.append(f"{namespace}:{name}")

        inspect_patterns(get_resolver().url_patterns)
        self.assertEqual(unresolved, [])
