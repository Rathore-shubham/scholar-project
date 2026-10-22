"""Mapping between user-facing labels and the ETL's tokens.

The ETL stores education levels as tokens ('9', '10', '12', 'UG', 'PG', 'DIPLOMA'), genders as MALE / FEMALE /
OTHERS and categories as upper-case codes. The UI and the eligibility form use readable labels.
"""

from __future__ import annotations

EDUCATION_LABELS: dict[str, str] = {
    "8": "Class 8", "9": "Class 9", "10": "Class 10", "11": "Class 11", "12": "Class 12",
    "DIPLOMA": "Diploma", "UG": "Undergraduate", "PG": "Postgraduate",
}
_EDUCATION_BY_TEXT: dict[str, str] = {label.casefold(): token for token, label in EDUCATION_LABELS.items()}
_EDUCATION_BY_TEXT.update({token.casefold(): token for token in EDUCATION_LABELS})
_EDUCATION_BY_TEXT.update({"graduate": "UG", "graduation": "UG", "post graduate": "PG", "postgraduation": "PG"})

GENDER_LABELS = {"MALE": "Male", "FEMALE": "Female", "OTHERS": "Other"}
_GENDER_BY_TEXT = {"male": "MALE", "female": "FEMALE", "other": "OTHERS", "others": "OTHERS"}
_UNSPECIFIED = {"", "prefer not to say", "not specified", "none"}


def education_token(value: str | None) -> str | None:
    """'Undergraduate' / 'UG' / 'Class 12' / '12' -> ETL token; unknown -> None."""
    if value is None:
        return None
    return _EDUCATION_BY_TEXT.get(value.strip().casefold())


def education_label(token: str) -> str:
    return EDUCATION_LABELS.get(token.upper(), token)


def education_sort_key(token: str) -> tuple[int, str]:
    order = ["8", "9", "10", "11", "12", "DIPLOMA", "UG", "PG"]
    upper = token.upper()
    return (order.index(upper) if upper in order else len(order), upper)


def gender_token(value: str | None) -> str | None:
    """'Male' -> 'MALE'; 'Prefer not to say' / blank -> None (unknown); unrecognized -> ValueError."""
    if value is None or value.strip().casefold() in _UNSPECIFIED:
        return None
    token = _GENDER_BY_TEXT.get(value.strip().casefold())
    if token is None:
        raise ValueError("gender must be Male, Female, Other or Prefer not to say")
    return token


def category_token(value: str | None) -> str | None:
    if value is None or value.strip().casefold() in _UNSPECIFIED:
        return None
    return value.strip().upper()


def state_value(value: str | None) -> str | None:
    """Blank and the old UI's 'Other' mean 'state not specified'."""
    if value is None or value.strip().casefold() in _UNSPECIFIED | {"other"}:
        return None
    return value.strip()
