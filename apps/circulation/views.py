from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.circulation.forms import IssueCopyForm, ReturnCopyForm
from apps.circulation.models import Loan
from apps.circulation.services import issue_copy, renew_loan, return_copy
from apps.core.mixins import LibraryPermissionRequiredMixin, OwnedByMemberMixin
from apps.core.permissions import library_permission_required
from apps.inventory.models import BookCopy
from apps.membership.models import MemberProfile


class AllLoansView(LoginRequiredMixin, LibraryPermissionRequiredMixin, ListView):
    permission_required = "circulation.view_all_loans"
    model = Loan
    template_name = "circulation/loan_list.html"
    context_object_name = "loans"
    paginate_by = 25

    def get_queryset(self):
        return Loan.objects.select_related("copy__book", "member__user", "issued_by", "returned_to")


class MyLoansView(LoginRequiredMixin, OwnedByMemberMixin, ListView):
    permission_required = "circulation.view_own_loans"
    model = Loan
    template_name = "circulation/loan_list.html"
    context_object_name = "loans"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not request.user.has_perm(self.permission_required):
            from django.core.exceptions import PermissionDenied

            from apps.audit.api import log

            log(
                request,
                "access.denied",
                target=request.path,
                outcome="denied",
                permission=self.permission_required,
            )
            request._audit_access_denied = True
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Loan.objects.owned_by(self.request.user).select_related("copy__book", "member")


@library_permission_required("circulation.process_circulation")
def issue_view(request):
    if request.method == "POST":
        form = IssueCopyForm(request.POST)
        if form.is_valid():
            try:
                copy = BookCopy.objects.get(accession_number=form.cleaned_data["accession_number"])
                member = MemberProfile.objects.select_related("user").get(
                    university_id=form.cleaned_data["university_id"]
                )
                issue_copy(copy, member, request.user)
            except (BookCopy.DoesNotExist, MemberProfile.DoesNotExist):
                form.add_error(None, "No matching copy or member was found.")
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Copy issued successfully.")
                return redirect("all_loans")
    else:
        form = IssueCopyForm()
    return render(request, "circulation/issue_form.html", {"form": form})


@library_permission_required("circulation.process_circulation")
def return_view(request):
    if request.method == "POST":
        form = ReturnCopyForm(request.POST)
        if form.is_valid():
            active_loans = Loan.objects.filter(returned_at__isnull=True)
            if form.cleaned_data.get("accession_number"):
                active_loans = active_loans.filter(
                    copy__accession_number=form.cleaned_data["accession_number"]
                )
            else:
                active_loans = active_loans.filter(
                    member__university_id=form.cleaned_data["university_id"]
                )
            matching_loans = active_loans.select_related("copy", "member")
            loan = matching_loans.first()
            if loan is None:
                form.add_error(None, "No active loan was found for that lookup.")
            elif not form.cleaned_data.get("accession_number") and matching_loans.count() > 1:
                form.add_error(
                    "university_id",
                    "This member has multiple active loans. Enter the copy accession number.",
                )
            else:
                try:
                    return_copy(loan, request.user)
                except ValidationError as error:
                    form.add_error(None, error)
                else:
                    messages.success(request, "Copy returned successfully.")
                    return redirect("all_loans")
    else:
        form = ReturnCopyForm()
    return render(request, "circulation/return_form.html", {"form": form})


@require_POST
def renew_view(request, pk):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    staff = request.user.has_perm("circulation.process_circulation")
    member = request.user.has_perm("circulation.renew_own_loan")
    if not staff and not member:
        from django.core.exceptions import PermissionDenied

        from apps.audit.api import log

        log(request, "access.denied", target=request.path, outcome="denied")
        request._audit_access_denied = True
        raise PermissionDenied
    queryset = Loan.objects.all() if staff else Loan.objects.owned_by(request.user)
    loan = get_object_or_404(queryset, pk=pk)
    try:
        renew_loan(loan, request.user)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, "Loan renewed.")
    return redirect("all_loans" if staff else "my_loans")


renew_view.permission_required = (
    "circulation.process_circulation",
    "circulation.renew_own_loan",
)
