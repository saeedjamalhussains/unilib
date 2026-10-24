from django.urls import path

from apps.catalog.views import (
    CatalogBookCreateView,
    CatalogBookDeleteView,
    CatalogBookDetailView,
    CatalogBookListView,
    CatalogBookUpdateView,
    ReferenceCreateView,
    ReferenceDeleteView,
    ReferenceListView,
    ReferenceUpdateView,
)

app_name = "catalog"

urlpatterns = [
    path("", CatalogBookListView.as_view(), name="book_list"),
    path("books/add/", CatalogBookCreateView.as_view(), name="book_create"),
    path("books/<int:pk>/", CatalogBookDetailView.as_view(), name="book_detail"),
    path("books/<int:pk>/edit/", CatalogBookUpdateView.as_view(), name="book_update"),
    path("books/<int:pk>/delete/", CatalogBookDeleteView.as_view(), name="book_delete"),
    path("<slug:resource>/", ReferenceListView.as_view(), name="reference_list"),
    path("<slug:resource>/add/", ReferenceCreateView.as_view(), name="reference_create"),
    path(
        "<slug:resource>/<int:pk>/edit/",
        ReferenceUpdateView.as_view(),
        name="reference_update",
    ),
    path(
        "<slug:resource>/<int:pk>/delete/",
        ReferenceDeleteView.as_view(),
        name="reference_delete",
    ),
]
