from collections.abc import Iterable, Mapping
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from apps.circulation.models import Loan
from apps.fines.models import Fine
from apps.inventory.models import BookCopy

REPORTS = {
    "inventory": "Inventory status",
    "active_loans": "Active loans",
    "overdue_loans": "Overdue loans",
    "circulation": "Circulation statistics",
    "most_borrowed": "Most borrowed titles",
    "outstanding_fines": "Outstanding fines",
}


def get_report_rows(
    report_name: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str = "",
) -> list[dict[str, str | int]]:
    if report_name not in REPORTS:
        raise ValidationError("Select a valid report.")
    today = timezone.localdate()
    if start_date and end_date and start_date > end_date:
        raise ValidationError("Start date must not be after end date.")
    if report_name == "inventory":
        return [
            {"status": status, "copy_count": count}
            for status, count in BookCopy.objects.values_list("status")
            .annotate(copy_count=Count("pk"))
            .order_by("status")
        ]
    if report_name in ("active_loans", "overdue_loans"):
        loans = Loan.objects.filter(returned_at__isnull=True).select_related(
            "copy__book", "member__user"
        )
        if report_name == "overdue_loans":
            loans = loans.filter(due_date__lt=today)
        return [
            {
                "title": loan.copy.book.title,
                "accession_number": loan.copy.accession_number,
                "university_id": loan.member.university_id,
                "member": loan.member.user.get_full_name() or loan.member.user.username,
                "issued_at": loan.issued_at.date().isoformat(),
                "due_date": loan.due_date.isoformat(),
            }
            for loan in loans.order_by("due_date", "pk")
        ]
    if report_name == "circulation":
        loans = Loan.objects.all()
        if start_date:
            loans = loans.filter(issued_at__date__gte=start_date)
        if end_date:
            loans = loans.filter(issued_at__date__lte=end_date)
        if category:
            loans = loans.filter(copy__book__categories__name=category)
        return list(
            loans.values("copy__book__categories__name")
            .annotate(loan_count=Count("pk"))
            .order_by("copy__book__categories__name")
        )
    if report_name == "most_borrowed":
        loans = Loan.objects.all()
        if start_date:
            loans = loans.filter(issued_at__date__gte=start_date)
        if end_date:
            loans = loans.filter(issued_at__date__lte=end_date)
        return list(
            loans.values("copy__book__title", "copy__book__isbn")
            .annotate(loan_count=Count("pk"))
            .order_by("-loan_count", "copy__book__title")[:100]
        )
    fines = (
        Fine.objects.filter(status=Fine.Status.OUTSTANDING)
        .select_related("member__user", "loan__copy__book")
        .prefetch_related("payments")
    )
    return [
        {
            "university_id": fine.member.university_id,
            "member": fine.member.user.get_full_name() or fine.member.user.username,
            "title": fine.loan.copy.book.title,
            "amount": str(fine.amount),
            "balance": str(fine.balance),
            "assessed_at": fine.assessed_at.date().isoformat(),
        }
        for fine in fines.order_by("assessed_at", "pk")
    ]


def export_csv(rows: Iterable[Mapping[str, object]]) -> str:
    """Serialize report rows while neutralizing spreadsheet formula cells."""
    import csv

    output = StringIO()
    writer = csv.writer(output)
    rows = list(rows)
    if not rows:
        writer.writerow(("No results",))
        return output.getvalue()
    keys = list(rows[0])
    writer.writerow(keys)
    for row in rows:
        values = []
        for key in keys:
            value = str(row.get(key, ""))
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return output.getvalue()
