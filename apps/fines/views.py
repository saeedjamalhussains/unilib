from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from apps.core.permissions import library_permission_required
from apps.fines.forms import PaymentForm, WaiverForm
from apps.fines.models import Fine
from apps.fines.services import record_payment, waive_fine


class FineListView(ListView):
    permission_required = "fines.manage_fines"
    model = Fine
    template_name = "fines/fine_list.html"
    context_object_name = "fines"
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
        return Fine.objects.select_related("loan", "member__user").prefetch_related("payments")


class MyFineListView(ListView):
    permission_required = "fines.view_own_fines"
    model = Fine
    template_name = "fines/fine_list.html"
    context_object_name = "fines"
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
        return (
            Fine.objects.owned_by(self.request.user)
            .select_related("loan", "member")
            .prefetch_related("payments")
        )


@library_permission_required("fines.manage_fines")
def payment_view(request, pk):
    fine = get_object_or_404(Fine, pk=pk)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                record_payment(
                    fine, form.cleaned_data["amount"], request.user, form.cleaned_data["method"]
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Payment recorded.")
                return redirect("fine_list")
    else:
        form = PaymentForm()
    return render(request, "fines/payment_form.html", {"form": form, "fine": fine})


@library_permission_required("fines.waive_fine")
def waiver_view(request, pk):
    fine = get_object_or_404(Fine, pk=pk)
    if request.method == "POST":
        form = WaiverForm(request.POST)
        if form.is_valid():
            try:
                waive_fine(fine, request.user, form.cleaned_data["reason"])
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Fine waived.")
                return redirect("fine_list")
    else:
        form = WaiverForm()
    return render(request, "fines/waiver_form.html", {"form": form, "fine": fine})
