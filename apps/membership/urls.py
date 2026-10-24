from django.urls import path

from apps.membership.views import (
    MemberListView,
    MemberUpdateView,
    MyProfileView,
    PolicyListView,
    member_create,
    policy_edit,
)

urlpatterns = [
    path("", MemberListView.as_view(), name="member_list"),
    path("create/", member_create, name="member_create"),
    path("me/", MyProfileView.as_view(), name="my_profile"),
    path("<int:pk>/edit/", MemberUpdateView.as_view(), name="member_edit"),
    path("policies/", PolicyListView.as_view(), name="policy_list"),
    path("policies/create/", policy_edit, name="policy_create"),
    path("policies/<int:pk>/edit/", policy_edit, name="policy_edit"),
]
