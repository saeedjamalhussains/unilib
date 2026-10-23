from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.role_matrix import matrix_markdown


class Command(BaseCommand):
    help = "Write the RBAC documentation from the canonical permission matrix."

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / "docs" / "RBAC_MATRIX.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(matrix_markdown(), encoding="utf-8")
        self.stdout.write(f"Wrote {path}")
