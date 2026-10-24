from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.accounts.role_matrix import ROLES
from apps.accounts.services import is_administrator


class AccountCreateForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    role = forms.ChoiceField()

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_roles = ROLES if is_administrator(actor) else ("Faculty", "Student")
        self.fields["role"].choices = [(role, role) for role in allowed_roles]
        self._style_fields()

    def _style_fields(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["role"].widget.attrs["class"] = "form-select"


class AccountUpdateForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            "username": "username",
            "email": "email",
            "first_name": "given-name",
            "last_name": "family-name",
        }
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        for name, value in autocomplete.items():
            self.fields[name].widget.attrs["autocomplete"] = value
        if is_administrator(actor):
            self.fields["role"] = forms.ChoiceField(
                label="Library role",
                required=False,
                choices=[("", "Keep current role")]
                + [(role, role) for role in ROLES],
                initial="",
                widget=forms.Select(attrs={"class": "form-select"}),
            )
