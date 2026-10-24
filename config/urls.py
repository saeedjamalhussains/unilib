from django.urls import include, path

from apps.audit.site import admin_site
from apps.core.views import home

urlpatterns = [
    path("admin/", admin_site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("inventory/copies/", include("apps.inventory.urls")),
    path(
        "manage/users/",
        include("apps.accounts.management_urls"),
    ),
    path("", home, name="home"),
]
