from django.http import HttpResponse
from django.urls import path
from django.views import View

from apps.core.mixins import LibraryPermissionRequiredMixin
from apps.core.views import home


class CatalogPermissionView(LibraryPermissionRequiredMixin, View):
    permission_required = "catalog.view_book"

    def get(self, request):
        return HttpResponse("allowed")


urlpatterns = [
    path("", home, name="home"),
    path("protected/", CatalogPermissionView.as_view(), name="protected"),
]
