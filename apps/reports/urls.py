from django.urls import path

from apps.reports.views import report_index

urlpatterns = [path("", report_index, name="report_index")]
