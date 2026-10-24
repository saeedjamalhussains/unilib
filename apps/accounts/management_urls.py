from django.urls import path

from apps.accounts.views import (
    AccountActivateView,
    AccountCreateView,
    AccountDeactivateView,
    AccountListView,
    AccountUpdateView,
)

urlpatterns = [
    path("", AccountListView.as_view(), name="manage_user_list"),
    path("create/", AccountCreateView.as_view(), name="manage_user_create"),
    path("<int:pk>/edit/", AccountUpdateView.as_view(), name="manage_user_edit"),
    path(
        "<int:pk>/activate/",
        AccountActivateView.as_view(),
        name="manage_user_activate",
    ),
    path(
        "<int:pk>/deactivate/",
        AccountDeactivateView.as_view(),
        name="manage_user_deactivate",
    ),
]
