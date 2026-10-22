"""Pure value-cleaning and parsing helpers.

Every ``parse_*`` function follows one rule: **convert only when the conversion is
unambiguous**. Otherwise it returns ``value=None`` with a status explaining why, so
callers can keep the original text and raise a warning instead of guessing.
"""

from __future__ import annotations

import calendar
import math
import numbers
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from scholarpath_data.reference import (
    CENTRAL_TERMS,
    GOVERNMENT_DOMAIN_SUFFIXES,
    STATE_ALIASES,
    alias_key,
)
from scholarpath_data.schema import ALL_SENTINEL

# --------------------------------------------------------------------------- #
# Text cleaning & missing values
# --------------------------------------------------------------------------- #

MISSING_TOKENS: frozenset[str] = frozenset(
    {
        "", "nan", "none", "null", "nil", "n/a", "na", "n.a.", "#n/a", "<na>", "nat",
        "-", "--", "---", "–", "—", "?", "unknown", "not available", "not applicable", "tbd",
    }
)

_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
_WHITESPACE = re.compile(r"\s+")


def _normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("−", "-")
    return _ZERO_WIDTH.sub("", text)


def clean_text(value: Any) -> str | None:
    """Trim/collapse whitespace; return ``None`` for empty or 'missing' placeholders."""
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        text = str(int(value)) if value.is_integer() else repr(value)
    elif isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and value != value:  # pandas NaT
            return None
        text = value.isoformat()
    else:
        text = str(value)
    text = _WHITESPACE.sub(" ", _normalize_unicode(text)).strip()
    return None if text.casefold() in MISSING_TOKENS else text


def match_key(text: str | None) -> str:
    """Normalized form used to compare names/providers (case, punctuation, '&' insensitive)."""
    if not text:
        return ""
    t = _normalize_unicode(str(text)).casefold().replace("&", " and ")
    t = re.sub(r"[’'`]", "", t)
    t = re.sub(r"[\W_]+", " ", t)
    return " ".join(t.split())


_LIST_SEPARATORS = re.compile(r"[,;|]")
_ALL_TOKEN = re.compile(r"^all(?:\s*(?:courses?|streams?|categor(?:y|ies)|states?|levels?|india))?$", re.I)


def split_list(
    value: Any,
    *,
    separators: re.Pattern[str] = _LIST_SEPARATORS,
    upper: bool = False,
    all_sentinel: bool = False,
) -> list[str]:
    """Split a delimited cell into clean, de-duplicated tokens (order preserved)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = value if isinstance(value, str) else (clean_text(value) or "")
    text = re.sub(r"[\r\n]+", "|", _normalize_unicode(text))
    seen: set[str] = set()
    tokens: list[str] = []
    for part in separators.split(text):
        token = clean_text(part)
        if token is None:
            continue
        if all_sentinel and _ALL_TOKEN.match(token):
            token = ALL_SENTINEL
        elif upper:
            token = token.upper()
        key = token.casefold()
        if key not in seen:
            seen.add(key)
            tokens.append(token)
    return tokens


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #

Status = Literal["ok", "missing", "ambiguous"]

# 12,34,567 (Indian) | 1,234,567 (western) | 1234567, each with an optional fraction.
_NUMBER = r"(?:\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_AMOUNT_RE = re.compile(
    rf"^(?P<neg>-)?\s*(?:₹|rs\.?|inr)?\s*(?P<num>{_NUMBER})\s*"
    r"(?P<mult>lakhs?|lacs?|crores?|cr)?\s*(?:/-|only)?$",
    re.IGNORECASE,
)
_MULTIPLIERS = {"lakh": 1e5, "lac": 1e5, "crore": 1e7, "cr": 1e7}
_RANGE_SPLIT = re.compile(r"\s*(?:-|–|—|\bto\b)\s*", re.IGNORECASE)
_COMPARATOR_RE = re.compile(
    r"^(?P<cmp><=|≤|<|up\s*to|upto|below|under|less\s+than|max(?:imum)?\.?|not\s+exceeding)\s*(?P<rest>.+)$",
    re.IGNORECASE,
)


def parse_number(value: Any) -> float | None:
    """A single plain number (Indian or western grouping, optional currency/lakh); else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, numbers.Real):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    text = clean_text(value)
    if text is None:
        return None
    match = _AMOUNT_RE.match(text)
    if not match:
        return None
    number = float(match["num"].replace(",", ""))
    if match["mult"]:
        number *= _MULTIPLIERS[match["mult"].lower().rstrip("s")]
    return -number if match["neg"] else number


def _number_or_text(value: Any) -> Any:
    """Real numbers pass through (NaN -> None); everything else is cleaned text."""
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        return None if math.isnan(float(value)) else value
    return clean_text(value)


@dataclass(frozen=True)
class AmountParse:
    minimum: float | None
    maximum: float | None
    status: Status


def parse_amount(value: Any) -> AmountParse:
    """Award amount: a single number or an explicit 'A - B' range. Tiered/worded text is ambiguous."""
    text = _number_or_text(value)
    if text is None:
        return AmountParse(None, None, "missing")
    single = parse_number(text)
    if single is not None:
        return AmountParse(single, single, "ok")
    parts = _RANGE_SPLIT.split(str(text))
    if len(parts) == 2 and all(parts):
        low, high = parse_number(parts[0]), parse_number(parts[1])
        if low is not None and high is not None:
            return AmountParse(min(low, high), max(low, high), "ok")
    return AmountParse(None, None, "ambiguous")


@dataclass(frozen=True)
class IncomeParse:
    value: float | None
    comparator: Literal["<", "<="] | None
    status: Status


def parse_income(value: Any) -> IncomeParse:
    """Family-income ceiling. Accepts one amount with an optional '<'/'up to' style prefix."""
    text = _number_or_text(value)
    if text is None:
        return IncomeParse(None, None, "missing")
    comparator: Literal["<", "<="] | None = None
    if isinstance(text, str):
        match = _COMPARATOR_RE.match(text)
        if match:
            token = match["cmp"].lower()
            comparator = "<" if token in {"<", "below", "under"} or token.startswith("less") else "<="
            text = match["rest"]
    number = parse_number(text)
    if number is None:
        return IncomeParse(None, None, "ambiguous")
    return IncomeParse(number, comparator, "ok")


_PERCENT_RE = re.compile(r"^(?P<num>-?\d+(?:\.\d+)?)\s*%?$")


def parse_percentage(value: Any) -> tuple[float | None, Status]:
    """A single percentage. Board-specific / multi-value text is ambiguous."""
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        number = float(value)
        return (None, "missing") if math.isnan(number) else (number, "ok")
    text = clean_text(value)
    if text is None:
        return None, "missing"
    match = _PERCENT_RE.match(text)
    return (float(match["num"]), "ok") if match else (None, "ambiguous")


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

DateStatus = Literal["ok", "missing", "ambiguous", "invalid", "unparsed"]


@dataclass(frozen=True)
class DateParse:
    value: date | None
    status: DateStatus


_ISO_RE = re.compile(
    r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"
    r"(?:[T ]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_NUMERIC_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_DAY_MONTHNAME_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+([A-Za-z]{3,9})\.?,?[\s\-/]+(\d{4})$")
_MONTHNAME_DAY_RE = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$")


def _month_number(token: str) -> int | None:
    token = token.lower()
    if len(token) < 3:
        return None
    for number in range(1, 13):
        if calendar.month_name[number].lower().startswith(token):
            return number
    return None


def _make_date(year: int, month: int, day: int) -> DateParse:
    try:
        return DateParse(date(year, month, day), "ok")
    except ValueError:
        return DateParse(None, "invalid")


def parse_date(value: Any) -> DateParse:
    """Parse a date only when its meaning is unambiguous (see README, 'Date rules')."""
    if value is None:
        return DateParse(None, "missing")
    if isinstance(value, datetime):
        return DateParse(None, "missing") if value != value else DateParse(value.date(), "ok")
    if isinstance(value, date):
        return DateParse(value, "ok")
    text = clean_text(value)
    if text is None:
        return DateParse(None, "missing")

    if match := _ISO_RE.match(text):
        return _make_date(int(match[1]), int(match[2]), int(match[3]))

    if match := _NUMERIC_RE.match(text):
        first, second, year = int(match[1]), int(match[2]), int(match[3])
        if first > 12 and second <= 12:
            return _make_date(year, second, first)  # DD/MM/YYYY
        if second > 12 and first <= 12:
            return _make_date(year, first, second)  # MM/DD/YYYY
        if first == second and first <= 12:
            return _make_date(year, first, second)  # same either way
        if first <= 12 and second <= 12:
            return DateParse(None, "ambiguous")
        return DateParse(None, "invalid")

    if match := _DAY_MONTHNAME_RE.match(text):
        month = _month_number(match[2])
        return _make_date(int(match[3]), month, int(match[1])) if month else DateParse(None, "unparsed")

    if match := _MONTHNAME_DAY_RE.match(text):
        month = _month_number(match[1])
        return _make_date(int(match[3]), month, int(match[2])) if month else DateParse(None, "unparsed")

    return DateParse(None, "unparsed")


_YEAR_PREFIX = re.compile(r"^(?:a\.?y\.?|f\.?y\.?|session|academic year)\s*[:\-]?\s*", re.IGNORECASE)
_ACADEMIC_YEAR_RE = re.compile(r"^(\d{4})\s*[-/–]\s*(\d{2}|\d{4})$")


def parse_academic_year(value: Any) -> tuple[str | None, Literal["ok", "missing", "unparsed"]]:
    """'2024-25' / '2024-2025' / 'AY 2024-25' -> '2024-25'. A bare year like '2024' is ambiguous."""
    text = clean_text(value)
    if text is None:
        return None, "missing"
    match = _ACADEMIC_YEAR_RE.match(_YEAR_PREFIX.sub("", text))
    if not match:
        return None, "unparsed"
    start, end = int(match[1]), int(match[2])
    end_two_digits = end % 100
    if end_two_digits != (start + 1) % 100 or (len(match[2]) == 4 and end != start + 1):
        return None, "unparsed"
    return f"{start}-{end_two_digits:02d}", "ok"


# --------------------------------------------------------------------------- #
# URLs
# --------------------------------------------------------------------------- #

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", re.IGNORECASE)
_TLD = re.compile(r"^(?:[a-z]{2,}|xn--[a-z0-9-]+)$", re.IGNORECASE)


def is_valid_url(text: str | None) -> bool:
    """Strict-enough check: http(s), a dotted host with a letter TLD, no spaces."""
    if not text or any(ch.isspace() for ch in text):
        return False
    try:
        parts = urlsplit(text)
        host = parts.hostname
        _ = parts.port  # raises ValueError on a bad port
    except ValueError:
        return False
    if parts.scheme.lower() not in {"http", "https"} or not host:
        return False
    labels = host.split(".")
    return len(labels) >= 2 and all(_HOST_LABEL.match(label) for label in labels) and bool(_TLD.match(labels[-1]))


def url_host(url: str | None) -> str | None:
    try:
        return urlsplit(url).hostname if url else None
    except ValueError:
        return None


def is_government_domain(url: str | None) -> bool:
    host = url_host(url)
    return bool(host) and any(host == s[1:] or host.endswith(s) for s in GOVERNMENT_DOMAIN_SUFFIXES)


def extract_urls(text: str) -> list[str]:
    """Every well-formed http(s) URL inside free text, trailing punctuation removed."""
    found: list[str] = []
    for match in _URL_RE.finditer(text):
        candidate = match.group().rstrip(".,;:)]}'\"")
        if is_valid_url(candidate) and candidate not in found:
            found.append(candidate)
    return found


@dataclass(frozen=True)
class UrlCell:
    url: str | None  # value to store (may be invalid text, so the validator can flag it)
    all_urls: list[str]
    raw: str | None
    cleaned: bool  # extra text was dropped around the URL
    multiple: bool


def parse_url_cell(value: Any) -> UrlCell:
    """Pull the URL(s) out of a cell such as 'https://a.gov.in (Portal)' or 'A / B'."""
    raw = clean_text(value)
    if raw is None:
        return UrlCell(None, [], None, False, False)
    urls = extract_urls(raw)
    if urls:
        return UrlCell(urls[0], urls, raw, cleaned=raw != urls[0], multiple=len(urls) > 1)
    return UrlCell(raw, [], raw, False, False)  # not a URL: keep as-is so validation reports it


# --------------------------------------------------------------------------- #
# States & government level
# --------------------------------------------------------------------------- #


def resolve_states(value: Any) -> tuple[list[str], list[str]]:
    """Return (canonical state names, tokens that were not recognized)."""
    states: list[str] = []
    unknown: list[str] = []

    def add(name: str) -> None:
        if name not in states:
            states.append(name)

    for token in split_list(value):
        key = alias_key(token)
        if key in STATE_ALIASES:
            add(STATE_ALIASES[key])
            continue
        parts = [alias_key(p) for p in re.split(r"\s+and\s+", token, flags=re.IGNORECASE)]
        if len(parts) > 1 and all(p in STATE_ALIASES for p in parts):
            for part in parts:
                add(STATE_ALIASES[part])
        else:
            unknown.append(token)
            add(token)
    return states, unknown


def government_level_to_scheme_type(value: Any) -> str | None:
    """'CENTRAL' -> 'central'; a recognized state -> 'state'; anything else -> ``None``."""
    text = clean_text(value)
    if text is None:
        return None
    if text.casefold() in CENTRAL_TERMS:
        return "central"
    states, unknown = resolve_states(text)
    return "state" if states and not unknown and states != [ALL_SENTINEL] else None
