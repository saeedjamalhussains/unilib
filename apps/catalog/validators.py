import re

from django.core.exceptions import ValidationError


def validate_isbn(value: str) -> None:
    """Validate ISBN-10 or ISBN-13 check digits; hyphens/spaces are ignored."""
    compact = re.sub(r"[\s-]", "", value or "").upper()
    if len(compact) == 10 and re.fullmatch(r"\d{9}[\dX]", compact):
        total = sum((10 - index) * (10 if digit == "X" else int(digit))
                    for index, digit in enumerate(compact))
        if total % 11 == 0:
            return
    elif (
        len(compact) == 13
        and compact.isdigit()
        and compact.startswith(("978", "979"))
    ):
        total = sum(
            int(digit) * (1 if index % 2 == 0 else 3)
            for index, digit in enumerate(compact)
        )
        if total % 10 == 0:
            return
    raise ValidationError("Enter a valid ISBN-10 or ISBN-13.", code="invalid_isbn")
