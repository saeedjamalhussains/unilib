from django import forms
from django.contrib.auth import get_user_model

from apps.membership.models import LibraryPolicy, MemberProfile


class MemberProfileForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Required when creating a new member account.",
    )
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = MemberProfile
        fields = ("university_id", "department", "member_type", "status", "membership_expiry")

    def __init__(self, *args, **kwargs):
        self.user_instance = kwargs.pop("user_instance", None)
        super().__init__(*args, **kwargs)
        self.fields["membership_expiry"].widget = forms.DateInput(attrs={"type": "date"})
        user = self.user_instance or (self.instance.user if self.instance.pk else None)
        if user:
            for field in ("username", "email", "first_name", "last_name"):
                self.fields[field].initial = getattr(user, field)

    def clean_username(self):
        username = self.cleaned_data["username"]
        users = get_user_model().objects.filter(username=username)
        current_user = self.user_instance or (self.instance.user if self.instance.pk else None)
        if current_user:
            users = users.exclude(pk=current_user.pk)
        if users.exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        users = get_user_model().objects.filter(email__iexact=email)
        current_user = self.user_instance or (self.instance.user if self.instance.pk else None)
        if current_user:
            users = users.exclude(pk=current_user.pk)
        if users.exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.instance.pk and not password:
            raise forms.ValidationError("Enter an initial password for this account.")
        return password


class LibraryPolicyForm(forms.ModelForm):
    class Meta:
        model = LibraryPolicy
        fields = (
            "member_type",
            "max_active_loans",
            "loan_days",
            "max_renewals",
            "renewal_days",
            "fine_per_day",
            "grace_days",
            "max_fine_per_loan",
            "fine_block_threshold",
            "reservation_hold_hours",
            "max_active_reservations",
        )
