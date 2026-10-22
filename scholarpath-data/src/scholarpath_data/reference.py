"""Static reference data: Indian states / union territories and common aliases."""

from __future__ import annotations

import re

from scholarpath_data.schema import ALL_SENTINEL

STATES: tuple[str, ...] = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
)
UNION_TERRITORIES: tuple[str, ...] = (
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
)


def alias_key(text: str) -> str:
    """Lower-case, drop dots, unify '&'/'and', collapse spaces."""
    key = text.casefold().replace(".", "")
    key = re.sub(r"\s*&\s*", " and ", key) if " & " in key else key
    return " ".join(key.split())


_EXTRA_ALIASES: dict[str, str] = {
    # historical / alternate spellings
    "orissa": "Odisha", "uttaranchal": "Uttarakhand", "pondicherry": "Puducherry",
    "tamilnadu": "Tamil Nadu", "chattisgarh": "Chhattisgarh", "nct of delhi": "Delhi",
    "new delhi": "Delhi", "j&k": "Jammu and Kashmir", "jammu kashmir": "Jammu and Kashmir",
    "andaman and nicobar": "Andaman and Nicobar Islands", "a and n islands": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    # common abbreviations (only ones that are unambiguous in an Indian-scholarship context)
    "ap": "Andhra Pradesh", "mp": "Madhya Pradesh", "up": "Uttar Pradesh", "wb": "West Bengal",
    "tn": "Tamil Nadu", "hp": "Himachal Pradesh", "jk": "Jammu and Kashmir", "mh": "Maharashtra",
    "ka": "Karnataka", "kl": "Kerala", "gj": "Gujarat", "rj": "Rajasthan", "pb": "Punjab",
    "hr": "Haryana", "br": "Bihar", "jh": "Jharkhand", "cg": "Chhattisgarh", "ts": "Telangana",
    "tg": "Telangana", "dl": "Delhi",
}

STATE_ALIASES: dict[str, str] = {alias_key(name): name for name in STATES + UNION_TERRITORIES}
STATE_ALIASES.update({alias_key(k): v for k, v in _EXTRA_ALIASES.items()})
STATE_ALIASES.update(
    {alias_key(k): ALL_SENTINEL for k in ("all", "all india", "pan india", "all states", "all states and uts", "india")}
)

CENTRAL_TERMS: frozenset[str] = frozenset(
    {"central", "centre", "union", "national", "government of india", "govt of india", "gol"}
)

GOVERNMENT_DOMAIN_SUFFIXES: tuple[str, ...] = (".gov.in", ".nic.in", ".ac.in", ".edu.in", ".res.in")
