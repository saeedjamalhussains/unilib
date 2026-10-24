from decimal import Decimal

from django.db import migrations


def seed_policies(apps, schema_editor):
    LibraryPolicy = apps.get_model("membership", "LibraryPolicy")
    defaults = (
        {
            "member_type": "student",
            "max_active_loans": 5,
            "loan_days": 14,
            "max_renewals": 2,
            "renewal_days": 7,
            "fine_per_day": Decimal("0.25"),
            "grace_days": 1,
            "max_fine_per_loan": Decimal("50.00"),
            "fine_block_threshold": Decimal("25.00"),
            "reservation_hold_hours": 72,
            "max_active_reservations": 5,
        },
        {
            "member_type": "faculty",
            "max_active_loans": 10,
            "loan_days": 30,
            "max_renewals": 3,
            "renewal_days": 14,
            "fine_per_day": Decimal("0.25"),
            "grace_days": 1,
            "max_fine_per_loan": Decimal("100.00"),
            "fine_block_threshold": Decimal("50.00"),
            "reservation_hold_hours": 72,
            "max_active_reservations": 10,
        },
    )
    for policy in defaults:
        LibraryPolicy.objects.get_or_create(member_type=policy["member_type"], defaults=policy)


class Migration(migrations.Migration):
    dependencies = [("membership", "0001_initial")]
    operations = [migrations.RunPython(seed_policies, migrations.RunPython.noop)]
