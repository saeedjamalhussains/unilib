from django import forms

from apps.catalog.models import Book
from apps.inventory.models import BookCopy


class BookCopyForm(forms.ModelForm):
    class Meta:
        model = BookCopy
        fields = (
            "book",
            "accession_number",
            "shelf_location",
            "status",
            "condition",
            "acquired_date",
        )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["book"].queryset = Book.objects.order_by("title")
        self.fields["acquired_date"].widget.attrs["type"] = "date"
        for name, field in self.fields.items():
            field.widget.attrs["class"] = (
                "form-select" if name in ("book", "status") else "form-control"
            )
