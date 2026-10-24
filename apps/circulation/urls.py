from django.urls import path

from apps.circulation.views import AllLoansView, MyLoansView, issue_view, renew_view, return_view

urlpatterns = [
    path("issue/", issue_view, name="issue_copy"),
    path("return/", return_view, name="return_copy"),
    path("loans/", AllLoansView.as_view(), name="all_loans"),
    path("my-loans/", MyLoansView.as_view(), name="my_loans"),
    path("loans/<int:pk>/renew/", renew_view, name="renew_loan"),
]
