from django.urls import path

from apps.fines.views import FineListView, MyFineListView, payment_view, waiver_view

urlpatterns = [
    path("", FineListView.as_view(), name="fine_list"),
    path("mine/", MyFineListView.as_view(), name="my_fines"),
    path("<int:pk>/payment/", payment_view, name="fine_payment"),
    path("<int:pk>/waive/", waiver_view, name="fine_waive"),
]
