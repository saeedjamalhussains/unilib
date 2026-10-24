from django.http import HttpResponse
from django.urls import path
from django.views import View

from apps.core.mixins import LibraryPermissionRequiredMixin
from apps.core.permissions import library_permission_required
from apps.core.views import home


class CatalogPermissionView(LibraryPermissionRequiredMixin, View):
    permission_required = "catalog.view_book"

    def get(self, request):
        return HttpResponse("allowed")


@library_permission_required("accounts.assign_roles")
def role_assignment_permission_view(request):
    return HttpResponse("allowed")


urlpatterns = [
    path("", home, name="home"),
    path("protected/", CatalogPermissionView.as_view(), name="protected"),
    path("decorated/", role_assignment_permission_view, name="decorated_protected"),
]
