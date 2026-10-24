from django.urls import path

from apps.inventory.views import CopyCreateView, CopyListView, CopyStatusView, CopyUpdateView

urlpatterns = [
    path("", CopyListView.as_view(), name="copy_list"),
    path("add/", CopyCreateView.as_view(), name="copy_create"),
    path("<int:pk>/edit/", CopyUpdateView.as_view(), name="copy_update"),
    path("<int:pk>/status/", CopyStatusView.as_view(), name="copy_status"),
]
