from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from apps.audit.api import log
from apps.core.permissions import library_permission_required
from apps.reports.services import REPORTS, export_csv, get_report_rows


@library_permission_required("reports.view_reports")
def report_index(request):
    report_name = request.GET.get("report", "inventory")
    start_date = parse_date(request.GET.get("start", ""))
    end_date = parse_date(request.GET.get("end", ""))
    category = request.GET.get("category", "").strip()
    errors = []
    if request.GET.get("start") and start_date is None:
        errors.append("Enter a valid start date.")
    if request.GET.get("end") and end_date is None:
        errors.append("Enter a valid end date.")
    try:
        rows = (
            get_report_rows(
                report_name,
                start_date=start_date,
                end_date=end_date,
                category=category,
            )
            if not errors
            else []
        )
    except ValidationError as error:
        errors.extend(error.messages)
        rows = []
    if request.GET.get("format") == "csv" and not errors:
        response = HttpResponse(export_csv(rows), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report_name}.csv"'
        log(request, "reports.csv_exported", target=report_name, row_count=len(rows))
        return response
    page_obj = Paginator(rows, 50).get_page(request.GET.get("page"))
    page_rows = page_obj.object_list
    return render(
        request,
        "reports/index.html",
        {
            "reports": REPORTS,
            "report_name": report_name,
            "rows": page_rows,
            "columns": list(page_rows[0]) if page_rows else [],
            "page_obj": page_obj,
            "is_paginated": page_obj.paginator.num_pages > 1,
            "errors": errors,
            "start": request.GET.get("start", ""),
            "end": request.GET.get("end", ""),
            "category": category,
        },
    )
