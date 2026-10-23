from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from apps.accounts.role_matrix import CAPABILITIES, ROLES


class Command(BaseCommand):
    help = "Create the library role groups and reconcile their permissions."

    def handle(self, *args, **options):
        permissions_by_codename = {}
        for capability in CAPABILITIES:
            app_label, codename = capability.permission.split(".", maxsplit=1)
            permission = (
                Permission.objects.filter(
                    content_type__app_label=app_label,
                    codename=codename,
                )
                .select_related("content_type")
                .order_by("pk")
                .first()
            )
            content_type = permission.content_type if permission else None
            if content_type is None:
                content_type, _ = ContentType.objects.get_or_create(
                    app_label=app_label,
                    model="rolecapability",
                )
                permission = None
            if permission is None:
                permission, _ = Permission.objects.get_or_create(
                    content_type=content_type,
                    codename=codename,
                    defaults={"name": capability.description},
                )
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
