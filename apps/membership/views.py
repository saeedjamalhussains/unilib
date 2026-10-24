from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, UpdateView

from apps.core.mixins import LibraryPermissionRequiredMixin, OwnedByMemberMixin
from apps.core.permissions import library_permission_required
from apps.membership.forms import LibraryPolicyForm, MemberProfileForm
from apps.membership.models import LibraryPolicy, MemberProfile
from apps.membership.services import register_member, save_member, save_policy


class MemberListView(LoginRequiredMixin, LibraryPermissionRequiredMixin, ListView):
    permission_required = ("membership.view_all_members",)
    model = MemberProfile
    template_name = "membership/member_list.html"
    context_object_name = "members"
    paginate_by = 25

    def get_queryset(self):
        queryset = MemberProfile.objects.select_related("user")
        term = self.request.GET.get("q", "").strip()
        if term:
            queryset = queryset.filter(
                models.Q(university_id__icontains=term)
                | models.Q(user__username__icontains=term)
                | models.Q(user__first_name__icontains=term)
                | models.Q(user__last_name__icontains=term)
            )
        return queryset


@library_permission_required("membership.manage_members")
def member_create(request):
    if request.method == "POST":
        form = MemberProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            try:
                register_member(
                    request,
                    profile,
                    username=form.cleaned_data["username"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Member profile created.")
                return redirect("member_list")
    else:
        form = MemberProfileForm()
    return render(request, "membership/member_form.html", {"form": form})


class MemberUpdateView(LoginRequiredMixin, LibraryPermissionRequiredMixin, UpdateView):
    permission_required = "membership.manage_members"
    model = MemberProfile
    form_class = MemberProfileForm
    template_name = "membership/member_form.html"
    success_url = "/members/"
    queryset = MemberProfile.objects.select_related("user")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object:
            kwargs["user_instance"] = self.object.user
        return kwargs

    def form_valid(self, form):
        user = self.object.user
        role = (
            "Student"
            if form.cleaned_data["member_type"] == MemberProfile.MemberType.STUDENT
            else "Faculty"
        )
        if not user.groups.filter(name=role).exists():
            form.add_error("member_type", "Member type must match the user's library role.")
            return self.form_invalid(form)
        user.username = form.cleaned_data["username"]
        user.email = form.cleaned_data["email"]
        user.first_name = form.cleaned_data["first_name"]
        user.last_name = form.cleaned_data["last_name"]
        user.full_clean()
        try:
            with transaction.atomic():
                user.save()
                save_member(self.request, form.save())
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Member profile updated.")
        return redirect(self.success_url)


class MyProfileView(LoginRequiredMixin, OwnedByMemberMixin, ListView):
    model = MemberProfile
    template_name = "membership/my_profile.html"
    context_object_name = "profiles"

    def get_queryset(self):
        return MemberProfile.objects.owned_by(self.request.user).select_related("user")

    def get(self, request, *args, **kwargs):
        profile = self.get_queryset().first()
        if profile is None:
            return render(request, self.template_name, {"profile": None})
        return render(request, self.template_name, {"profile": profile})


class PolicyListView(LoginRequiredMixin, LibraryPermissionRequiredMixin, ListView):
    permission_required = "membership.manage_policy"
    model = LibraryPolicy
    template_name = "membership/policy_list.html"


@library_permission_required("membership.manage_policy")
def policy_edit(request, pk=None):
    instance = get_object_or_404(LibraryPolicy, pk=pk) if pk else None
    if request.method == "POST":
        form = LibraryPolicyForm(request.POST, instance=instance)
        if form.is_valid():
            save_policy(request, form.save())
            messages.success(request, "Library policy saved.")
            return redirect("policy_list")
    else:
        form = LibraryPolicyForm(instance=instance)
    return render(request, "membership/policy_form.html", {"form": form})
