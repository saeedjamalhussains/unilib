from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.access import AccountManagementRequiredMixin
from apps.accounts.forms import AccountCreateForm, AccountUpdateForm
from apps.accounts.role_matrix import ROLES
from apps.accounts.services import (
    account_list_for,
    activate_user,
    create_account,
    deactivate_user,
    update_account,
)
from apps.audit.api import log


class AuditedPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    def form_valid(self, form):
        response = super().form_valid(form)
        log(self.request, "auth.password_changed", target=self.request.user)
        return response


class LoginRequiredPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    pass


class AccountListView(AccountManagementRequiredMixin, ListView):
    template_name = "accounts/account_list.html"
    context_object_name = "accounts"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_group_names"] = ROLES
        return context

    def get_queryset(self):
        queryset = account_list_for(
            self.request.user,
            get_user_model().objects.prefetch_related("groups").order_by("username"),
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return queryset


class AccountCreateView(AccountManagementRequiredMixin, CreateView):
    form_class = AccountCreateForm
    template_name = "accounts/account_form.html"
    success_url = reverse_lazy("manage_user_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["actor"] = self.request.user
        return kwargs

    def form_valid(self, form):
        account = create_account(
            self.request.user,
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            password=form.cleaned_data["password1"],
            role=form.cleaned_data["role"],
        )
        self.object = account
        messages.success(self.request, f"Account for {account.username} was created.")
        return redirect(self.get_success_url())


class AccountUpdateView(AccountManagementRequiredMixin, UpdateView):
    form_class = AccountUpdateForm
    template_name = "accounts/account_form.html"
    context_object_name = "account"
    success_url = reverse_lazy("manage_user_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["actor"] = self.request.user
        return kwargs

    def get_queryset(self):
        queryset = get_user_model().objects.prefetch_related("groups")
        return account_list_for(self.request.user, queryset)

    def form_valid(self, form):
        try:
            self.object = update_account(
                self.request.user,
                self.get_object(),
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                role=form.cleaned_data.get("role") or None,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Account for {self.object.username} was updated.")
        return redirect(self.get_success_url())


class AccountDeactivateView(AccountManagementRequiredMixin, View):
    def get_account(self):
        return get_object_or_404(
            account_list_for(self.request.user, get_user_model().objects.all()),
            pk=self.kwargs["pk"],
        )

    def get(self, request, *args, **kwargs):
        account = self.get_account()
        if not account.is_active:
            messages.info(request, "This account is already inactive.")
            return redirect("manage_user_list")
        if account.pk == request.user.pk:
            raise PermissionDenied("You cannot deactivate your own account.")
        return render(
            request,
            "accounts/account_deactivate_confirm.html",
            {"account": account},
        )

    def post(self, request, *args, **kwargs):
        account = deactivate_user(request.user, self.get_account())
        messages.success(request, f"Account for {account.username} was deactivated.")
        return redirect("manage_user_list")


class AccountActivateView(AccountManagementRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        account = get_object_or_404(
            account_list_for(request.user, get_user_model().objects.all()),
            pk=kwargs["pk"],
        )
        activated_account = activate_user(request.user, account)
        messages.success(
            request,
            f"Account for {activated_account.username} is active.",
        )
        return redirect("manage_user_list")
