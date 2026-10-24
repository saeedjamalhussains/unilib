from django import forms


class IssueCopyForm(forms.Form):
    accession_number = forms.CharField(max_length=100)
    university_id = forms.CharField(max_length=64)


class ReturnCopyForm(forms.Form):
    accession_number = forms.CharField(max_length=100, required=False)
    university_id = forms.CharField(max_length=64, required=False)

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("accession_number") and not cleaned_data.get("university_id"):
            raise forms.ValidationError("Enter an accession number or a member university ID.")
        return cleaned_data


class AccessionLookupForm(forms.Form):
    accession_number = forms.CharField(max_length=100)
