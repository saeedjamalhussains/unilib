import re

from django import forms

from apps.catalog.models import Author, Book, Category, Publisher


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = (
            "title",
            "subtitle",
            "isbn",
            "edition",
            "publication_year",
            "publisher",
            "authors",
            "categories",
            "description",
            "price",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["authors"].widget.attrs["size"] = 5
        self.fields["categories"].widget.attrs["size"] = 5
        self.fields["description"].widget.attrs["rows"] = 4
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "form-select" if name in ("publisher", "authors", "categories") else "form-control",
            )

    def clean_isbn(self):
        return re.sub(r"[\s-]", "", self.cleaned_data["isbn"]).upper()


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ("name", "biography")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["biography"].widget.attrs["rows"] = 4


class PublisherForm(forms.ModelForm):
    class Meta:
        model = Publisher
        fields = ("name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["class"] = "form-control"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["description"].widget.attrs["rows"] = 4
