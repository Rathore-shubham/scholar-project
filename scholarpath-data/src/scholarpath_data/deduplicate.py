"""Possible-duplicate detection on normalized scholarship + provider names.

Records are **never merged or deleted** here. Candidates are only grouped and flagged
(``duplicate_group_id`` + a validation warning) so a human can review them.

Match types, strongest first:
    exact_name_and_provider       same normalized name and same non-empty provider
    same_name_different_provider  same normalized name; provider differs or is unknown
    similar_name                  names are at least ``threshold`` similar (difflib ratio)

Complexity is O(n^2) in the number of records, which is fine for thousands of rows;
add blocking (e.g. by first token) before scaling much further.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

from scholarpath_data.parsers import match_key
from scholarpath_data.schema import Issue, ScholarshipRecord, make_issue

EXACT = "exact_name_and_provider"
SAME_NAME = "same_name_different_provider"
SIMILAR = "similar_name"
_RANK = {EXACT: 3, SAME_NAME: 2, SIMILAR: 1}
DEFAULT_THRESHOLD = 0.90


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: str
    match_type: str  # strongest match type found inside the group
    min_similarity: float  # weakest link inside the group (1.0 = identical names)
    members: tuple[int, ...]  # indices into the record sequence, ascending
    distinguishing_tokens: tuple[str, ...]  # name words not shared by every member


def _pair_match(a: str, b: str, provider_a: str, provider_b: str, threshold: float) -> tuple[str, float] | None:
    if a == b:
        return (EXACT if provider_a and provider_a == provider_b else SAME_NAME), 1.0
    matcher = SequenceMatcher(None, a, b)
    if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
        return None
    ratio = matcher.ratio()
    return (SIMILAR, ratio) if ratio >= threshold else None


def find_duplicate_groups(
    records: Sequence[ScholarshipRecord], threshold: float = DEFAULT_THRESHOLD
) -> list[DuplicateGroup]:
    names = [match_key(r.scholarship_name) for r in records]
    providers = [match_key(r.provider_name) for r in records]

    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges: list[tuple[int, int, str, float]] = []
    for i in range(len(records)):
        if not names[i]:
            continue
        for j in range(i + 1, len(records)):
            if not names[j]:
                continue
            match = _pair_match(names[i], names[j], providers[i], providers[j], threshold)
            if match:
                edges.append((i, j, *match))
                parent[find(j)] = find(i)

    components: dict[int, list[int]] = {}
    for i in range(len(records)):
        components.setdefault(find(i), []).append(i)

    groups: list[DuplicateGroup] = []
    for members in sorted((m for m in components.values() if len(m) > 1), key=lambda m: m[0]):
        member_set = set(members)
        group_edges = [e for e in edges if e[0] in member_set]
        token_sets = [set(names[i].split()) for i in members]
        distinguishing = sorted(set.union(*token_sets) - set.intersection(*token_sets))
        groups.append(
            DuplicateGroup(
                group_id=f"DG-{len(groups) + 1:04d}",
                match_type=max((e[2] for e in group_edges), key=_RANK.__getitem__),
                min_similarity=round(min(e[3] for e in group_edges), 4),
                members=tuple(members),
                distinguishing_tokens=tuple(distinguishing),
            )
        )
    return groups


def duplicate_issues(groups: Sequence[DuplicateGroup], records: Sequence[ScholarshipRecord]) -> dict[int, list[Issue]]:
    """Per-record-index warnings for every group member."""
    result: dict[int, list[Issue]] = {}
    for group in groups:
        code = "duplicate_scholarship_name" if group.match_type in (EXACT, SAME_NAME) else "possible_duplicate"
        for index in group.members:
            others = ", ".join(records[i].scholarship_id for i in group.members if i != index)
            detail = f"group {group.group_id} ({group.match_type}); compare with {others}"
            result.setdefault(index, []).append(make_issue(code, "scholarship_name", detail))
    return result


def duplicate_rows(groups: Sequence[DuplicateGroup], records: Sequence[ScholarshipRecord]) -> list[dict[str, object]]:
    """Flat rows (one per member) for the possible_duplicates.csv review file."""
    rows: list[dict[str, object]] = []
    for group in groups:
        for index in group.members:
            r = records[index]
            rows.append(
                {
                    "group_id": group.group_id,
                    "group_match_type": group.match_type,
                    "group_min_similarity": group.min_similarity,
                    "group_size": len(group.members),
                    "distinguishing_words": " ".join(group.distinguishing_tokens),
                    "scholarship_id": r.scholarship_id,
                    "source_record_id": r.source_record_id or "",
                    "source_file": r.source_file or "",
                    "source_sheet": r.source_sheet or "",
                    "source_row": r.source_row if r.source_row is not None else "",
                    "scholarship_name": r.scholarship_name or "",
                    "provider_name": r.provider_name or "",
                    "eligible_states": "; ".join(r.eligible_states),
                    "official_url": r.official_url or "",
                }
            )
    return rows


DUPLICATE_COLUMNS: tuple[str, ...] = (
    "group_id", "group_match_type", "group_min_similarity", "group_size", "distinguishing_words",
    "scholarship_id", "source_record_id", "source_file", "source_sheet", "source_row",
    "scholarship_name", "provider_name", "eligible_states", "official_url",
)
