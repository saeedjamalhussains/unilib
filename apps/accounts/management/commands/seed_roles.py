from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.role_matrix import CAPABILITIES, ROLES


class Command(BaseCommand):
    help = "Create the library role groups and reconcile their permissions."

    @transaction.atomic
    def handle(self, *args, **options):
        permissions_by_codename = {}
        for capability in CAPABILITIES:
            app_label, codename = capability.permission.split(".", maxsplit=1)
            model = self.get_permission_model(app_label, codename)
            if model is not None:
                content_type = ContentType.objects.get_for_model(model)
            else:
                content_type, _ = ContentType.objects.get_or_create(
                    app_label=app_label,
                    model="rolecapability",
                )
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=codename,
                defaults={"name": capability.description},
            )
            Permission.objects.filter(
                content_type__app_label=app_label,
                content_type__model="rolecapability",
                codename=codename,
            ).exclude(pk=permission.pk).delete()
            permissions_by_codename[capability.permission] = permission

        for role in ROLES:
            group, _ = Group.objects.get_or_create(name=role)
            expected = [
                permissions_by_codename[capability.permission]
                for capability in CAPABILITIES
                if role in capability.roles
            ]
            group.permissions.set(expected)
            self.stdout.write(f"Reconciled {role}: {len(expected)} permissions.")

    @staticmethod
    def get_permission_model(app_label, codename):
        model_names = {
            ("accounts", "manage_users"): "user",
            ("accounts", "assign_roles"): "user",
            ("catalog", "view_book"): "book",
            ("catalog", "manage_catalog"): "book",
            ("catalog", "delete_book"): "book",
            ("inventory", "manage_copies"): "bookcopy",
            ("audit", "view_auditlog"): "auditlog",
        }
        model_name = model_names.get((app_label, codename))
        if model_name is None:
            return None
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            return None
