from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.catalog.forms import AuthorForm, BookForm, CategoryForm, PublisherForm
from apps.catalog.models import Author, Book, Category, Publisher
from apps.catalog.services import (
    delete_book,
    delete_catalog_record,
    save_catalog_record,
)
from apps.core.mixins import LibraryPermissionRequiredMixin

REFERENCE_RESOURCES = {
    "authors": (Author, AuthorForm, "Authors", "Author"),
    "publishers": (Publisher, PublisherForm, "Publishers", "Publisher"),
    "categories": (Category, CategoryForm, "Categories", "Category"),
}


class CatalogReadRequiredMixin(LibraryPermissionRequiredMixin):
    permission_required = "catalog.view_book"


class CatalogManageRequiredMixin(LibraryPermissionRequiredMixin):
    permission_required = "catalog.manage_catalog"


class CatalogBookListView(CatalogReadRequiredMixin, ListView):
    model = Book
    template_name = "catalog/book_list.html"
    context_object_name = "books"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Book.objects.select_related("publisher")
            .prefetch_related("authors", "categories")
            .annotate(
                available_copies=Count(
                    "copies",
                    filter=Q(copies__status="available"),
                    distinct=True,
                )
            )
        )
        title = self.request.GET.get("title", "").strip()
        author = self.request.GET.get("author", "").strip()
        isbn = self.request.GET.get("isbn", "").strip()
        category = self.request.GET.get("category", "").strip()
        query = self.request.GET.get("q", "").strip()
        if title:
            queryset = queryset.filter(title__icontains=title)
        if author:
            queryset = queryset.filter(authors__name__icontains=author)
        if isbn:
            queryset = queryset.filter(isbn__icontains=isbn)
        if category:
            queryset = queryset.filter(categories__name__icontains=category)
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(subtitle__icontains=query)
                | Q(isbn__icontains=query)
                | Q(authors__name__icontains=query)
                | Q(categories__name__icontains=query)
            )
        return queryset.distinct().order_by("title", "pk")


class CatalogBookDetailView(CatalogReadRequiredMixin, DetailView):
    model = Book
    template_name = "catalog/book_detail.html"
    context_object_name = "book"

    def get_queryset(self):
        return (
            Book.objects.select_related("publisher")
            .prefetch_related("authors", "categories")
            .annotate(
                available_copies=Count(
                    "copies",
                    filter=Q(copies__status="available"),
                    distinct=True,
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("inventory.manage_copies"):
            copies = self.object.copies.order_by("accession_number", "pk")
            context["copy_page"] = Paginator(copies, 20).get_page(
                self.request.GET.get("copies_page")
            )
        return context


class CatalogBookCreateView(CatalogManageRequiredMixin, CreateView):
    form_class = BookForm
    template_name = "catalog/book_form.html"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        try:
            save_catalog_record(
                self.request.user,
                self.object,
                authors=form.cleaned_data["authors"],
                categories=form.cleaned_data["categories"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Book '{self.object.title}' was added.")
        return redirect("catalog:book_detail", pk=self.object.pk)


class CatalogBookUpdateView(CatalogManageRequiredMixin, UpdateView):
    model = Book
    form_class = BookForm
    template_name = "catalog/book_form.html"

    def get_queryset(self):
        return Book.objects.select_related("publisher").prefetch_related(
            "authors", "categories"
        )

    def form_valid(self, form):
        self.object = form.save(commit=False)
        try:
            save_catalog_record(
                self.request.user,
                self.object,
                authors=form.cleaned_data["authors"],
                categories=form.cleaned_data["categories"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Book '{self.object.title}' was updated.")
        return redirect("catalog:book_detail", pk=self.object.pk)


class CatalogBookDeleteView(LibraryPermissionRequiredMixin, View):
    permission_required = "catalog.delete_book"

    def get_book(self):
        return get_object_or_404(Book.objects.prefetch_related("copies"), pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        return render(
            request,
            "catalog/book_delete_confirm.html",
            {"book": self.get_book()},
        )

    def post(self, request, *args, **kwargs):
        book = self.get_book()
        try:
            delete_book(request.user, book)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("catalog:book_detail", pk=book.pk)
        messages.success(request, "Book was deleted.")
        return redirect("catalog:book_list")


class ReferenceResourceMixin:
    def resource_config(self):
        resource = self.kwargs["resource"]
        try:
            return REFERENCE_RESOURCES[resource]
        except KeyError as exc:
            raise PermissionDenied("Unknown catalog resource.") from exc

    def get_model(self):
        return self.resource_config()[0]

    def get_form_class(self):
        return self.resource_config()[1]

    def get_resource_singular(self):
        return self.resource_config()[3]

    def get_success_url(self):
        return reverse("catalog:reference_list", kwargs={"resource": self.kwargs["resource"]})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["resource"] = self.kwargs["resource"]
        context["resource_label"] = self.resource_config()[2]
        context["resource_singular"] = self.get_resource_singular()
        return context

    def get_queryset(self):
        return self.get_model().objects.order_by("name", "pk")

class ReferenceListView(CatalogManageRequiredMixin, ReferenceResourceMixin, ListView):
    template_name = "catalog/reference_list.html"
    context_object_name = "records"
    paginate_by = 25


class ReferenceCreateView(CatalogManageRequiredMixin, ReferenceResourceMixin, CreateView):
    template_name = "catalog/reference_form.html"

    def form_valid(self, form):
        record = form.save(commit=False)
        try:
            save_catalog_record(self.request.user, record)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"{record} was added.")
        return redirect(self.get_success_url())


class ReferenceUpdateView(CatalogManageRequiredMixin, ReferenceResourceMixin, UpdateView):
    template_name = "catalog/reference_form.html"

    def form_valid(self, form):
        record = form.save(commit=False)
        try:
            save_catalog_record(self.request.user, record)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"{record} was updated.")
        return redirect(self.get_success_url())


class ReferenceDeleteView(CatalogManageRequiredMixin, ReferenceResourceMixin, View):
    def get_record(self):
        return get_object_or_404(self.get_model(), pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        return render(
            request,
            "catalog/reference_delete_confirm.html",
            {
                "record": self.get_record(),
                "resource": self.kwargs["resource"],
                "resource_label": self.resource_config()[2],
                "resource_singular": self.get_resource_singular(),
            },
        )

    def post(self, request, *args, **kwargs):
        record = self.get_record()
        try:
            delete_catalog_record(request.user, record)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, f"{record} was deleted.")
        return redirect(self.get_success_url())
