from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.catalog.models import Book
from apps.core.permissions import library_permission_required
from apps.membership.models import MemberProfile
from apps.reservations.models import Reservation
from apps.reservations.services import cancel_reservation, place_reservation


class ReservationListView(ListView):
    permission_required = "reservations.manage_reservations"
    model = Reservation
    template_name = "reservations/reservation_list.html"
    context_object_name = "reservations"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        from django.contrib.auth.views import redirect_to_login
        from django.core.exceptions import PermissionDenied

        from apps.audit.api import log

        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.has_perm(self.permission_required):
            log(request, "access.denied", target=request.path, outcome="denied")
            request._audit_access_denied = True
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Reservation.objects.select_related("book", "member__user", "ready_copy")


class MyReservationListView(ListView):
    permission_required = "reservations.place_reservation"
    model = Reservation
    template_name = "reservations/my_reservations.html"
    context_object_name = "reservations"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        from django.contrib.auth.views import redirect_to_login
        from django.core.exceptions import PermissionDenied

        from apps.audit.api import log

        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.has_perm(self.permission_required):
            log(request, "access.denied", target=request.path, outcome="denied")
            request._audit_access_denied = True
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Reservation.objects.owned_by(self.request.user).select_related("book", "ready_copy")


@library_permission_required("reservations.place_reservation")
def place_view(request, book_id=None):
    if request.method == "POST":
        book = get_object_or_404(Book, pk=book_id or request.POST.get("book"))
        member = get_object_or_404(MemberProfile, user=request.user)
        try:
            place_reservation(book, member)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, "Reservation placed.")
        return redirect("my_reservations")
    return render(
        request, "reservations/place_form.html", {"books": Book.objects.order_by("title")}
    )


@require_POST
def cancel_view(request, pk):
    from django.contrib.auth.views import redirect_to_login
    from django.core.exceptions import PermissionDenied

    from apps.audit.api import log

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    staff = request.user.has_perm("reservations.manage_reservations")
    if not staff and not request.user.has_perm("reservations.place_reservation"):
        log(request, "access.denied", target=request.path, outcome="denied")
        request._audit_access_denied = True
        raise PermissionDenied
    queryset = Reservation.objects.all() if staff else Reservation.objects.owned_by(request.user)
    reservation = get_object_or_404(queryset, pk=pk)
    try:
        cancel_reservation(reservation, request.user)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, "Reservation cancelled.")
    return redirect("reservation_list" if staff else "my_reservations")


cancel_view.permission_required = (
    "reservations.manage_reservations",
    "reservations.place_reservation",
)
