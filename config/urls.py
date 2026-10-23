from django.urls import include, path

from apps.audit.site import admin_site
from apps.core.views import home

urlpatterns = [
    path("admin/", admin_site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", home, name="home"),
]
