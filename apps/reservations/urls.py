from django.urls import path

from apps.reservations.views import (
    MyReservationListView,
    ReservationListView,
    cancel_view,
    place_view,
)

urlpatterns = [
    path("", ReservationListView.as_view(), name="reservation_list"),
    path("mine/", MyReservationListView.as_view(), name="my_reservations"),
    path("place/", place_view, name="place_reservation"),
    path("place/<int:book_id>/", place_view, name="place_reservation_for_book"),
    path("<int:pk>/cancel/", cancel_view, name="cancel_reservation"),
]
