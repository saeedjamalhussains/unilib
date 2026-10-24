from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import LibraryPermissionRequiredMixin
from apps.inventory.forms import BookCopyForm
from apps.inventory.models import BookCopy
from apps.inventory.services import change_copy_status, save_copy


class CopyManagementRequiredMixin(LibraryPermissionRequiredMixin):
    permission_required = "inventory.manage_copies"


class CopyListView(CopyManagementRequiredMixin, ListView):
    model = BookCopy
    template_name = "inventory/copy_list.html"
    context_object_name = "copies"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = BookCopy.Status.choices
        return context

    def get_queryset(self):
        queryset = BookCopy.objects.select_related("book").order_by(
            "accession_number", "pk"
        )
        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if search:
            queryset = queryset.filter(
                Q(accession_number__icontains=search)
                | Q(book__title__icontains=search)
                | Q(book__isbn__icontains=search)
            )
        if status in BookCopy.Status.values:
            queryset = queryset.filter(status=status)
        return queryset


class CopyCreateView(CopyManagementRequiredMixin, CreateView):
    form_class = BookCopyForm
    template_name = "inventory/copy_form.html"
    success_url = reverse_lazy("copy_list")

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("book"):
            initial["book"] = self.request.GET["book"]
        return initial

    def form_valid(self, form):
        self.object = form.save(commit=False)
        try:
            save_copy(self.request.user, self.object)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Copy {self.object.accession_number} was added.")
        return redirect(self.get_success_url())


class CopyUpdateView(CopyManagementRequiredMixin, UpdateView):
    model = BookCopy
    form_class = BookCopyForm
    template_name = "inventory/copy_form.html"
    success_url = reverse_lazy("copy_list")

    def get_queryset(self):
        return BookCopy.objects.select_related("book")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        try:
            save_copy(self.request.user, self.object)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Copy {self.object.accession_number} was updated.")
        return redirect(self.get_success_url())


class BookCopyStatusForm(forms.Form):
    status = forms.ChoiceField(choices=BookCopy.Status.choices)


class CopyStatusView(CopyManagementRequiredMixin, View):
    def get_copy(self):
        return get_object_or_404(BookCopy.objects.select_related("book"), pk=self.kwargs["pk"])

    def post(self, request, *args, **kwargs):
        form = BookCopyStatusForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Select a valid copy status.")
            return redirect("copy_list")
        copy = change_copy_status(request.user, self.get_copy(), form.cleaned_data["status"])
        messages.success(request, f"Copy {copy.accession_number} is now {copy.get_status_display()}.")
        return redirect("copy_list")
