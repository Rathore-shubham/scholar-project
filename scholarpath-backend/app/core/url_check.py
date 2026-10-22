"""Small URL validity check shared by the importer (no network access)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", re.IGNORECASE)
_TLD = re.compile(r"^(?:[a-z]{2,}|xn--[a-z0-9-]+)$", re.IGNORECASE)


def is_valid_http_url(text: str | None) -> bool:
    """http(s) URL with a dotted host and a letter TLD, no whitespace."""
    if not text or any(ch.isspace() for ch in text):
        return False
    try:
        parts = urlsplit(text)
        host = parts.hostname
        _ = parts.port
    except ValueError:
        return False
    if parts.scheme.lower() not in {"http", "https"} or not host:
        return False
    labels = host.split(".")
    return len(labels) >= 2 and all(_LABEL.match(label) for label in labels) and bool(_TLD.match(labels[-1]))
