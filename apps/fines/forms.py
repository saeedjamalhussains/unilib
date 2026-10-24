from decimal import Decimal

from django import forms


class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal("0.01"))
    method = forms.CharField(max_length=50)


class WaiverForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea, max_length=1000)
