"""Human verification decisions - the ONLY way a record can become ``verified``.

The pipeline itself never grants ``verified``. A reviewer records a decision in
``data/verified/verification_decisions.csv`` (one row per decision, newest last)::

    scholarship_id,decision,reviewer,reviewed_at,evidence_url,notes

A ``verified`` decision is applied only when ALL of these hold:
  * the scholarship_id matches exactly one record;
  * ``reviewer`` is filled in and ``reviewed_at`` is an unambiguous date, not in the future;
  * ``evidence_url`` is a valid http(s) URL (the reviewer asserts it is an authoritative source);
  * the record has no error-level validation issues.
Otherwise the decision is refused, the record keeps its status, and the refusal is
reported. ``needs_review`` / ``rejected`` / ``pending`` need a reviewer and date only.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from scholarpath_data.errors import SourceError
from scholarpath_data.normalize import NormalizedRecord
from scholarpath_data.parsers import clean_text, is_government_domain, is_valid_url, parse_date
from scholarpath_data.schema import VerificationStatus, make_issue

DECISION_COLUMNS: tuple[str, ...] = ("scholarship_id", "decision", "reviewer", "reviewed_at", "evidence_url", "notes")
_DECISIONS = {s.value: s for s in VerificationStatus}


@dataclass
class DecisionOutcome:
    rows_read: int = 0
    applied: list[dict[str, Any]] = field(default_factory=list)
    refused: list[dict[str, Any]] = field(default_factory=list)
    unmatched_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_rows_read": self.rows_read,
            "applied": self.applied,
            "refused": self.refused,
            "unmatched_scholarship_ids": self.unmatched_ids,
        }


def load_decisions(path: Path) -> list[dict[str, str]]:
    """Read the decisions CSV; each dict also carries ``_row`` (file line number)."""
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = [(name or "").strip().casefold() for name in (reader.fieldnames or [])]
            missing = {"scholarship_id", "decision", "reviewer", "reviewed_at"} - set(fieldnames)
            if missing:
                raise SourceError(
                    f"{Path(path).name} is missing column(s): {', '.join(sorted(missing))}. "
                    f"Expected header: {','.join(DECISION_COLUMNS)}"
                )
            rows = []
            for raw in reader:
                row = {(k or "").strip().casefold(): (v or "").strip() for k, v in raw.items() if k is not None}
                if any(row.values()):
                    row["_row"] = str(reader.line_num)  # real file line, even when blank lines are skipped
                    rows.append(row)
            return rows
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise SourceError(f"Cannot read decisions file {path}: {exc}") from exc


def apply_decisions(
    items: Sequence[NormalizedRecord],
    decisions: Sequence[dict[str, str]],
    as_of: date,
    ids_with_errors: set[str],
) -> DecisionOutcome:
    """Apply reviewer decisions in place. Later rows for the same id override earlier ones."""
    outcome = DecisionOutcome(rows_read=len(decisions))
    by_id: dict[str, list[NormalizedRecord]] = {}
    for item in items:
        by_id.setdefault(item.record.scholarship_id, []).append(item)

    latest: dict[str, dict[str, str]] = {}
    for decision in decisions:
        latest[decision.get("scholarship_id", "")] = decision

    for sid, decision in latest.items():
        row = decision.get("_row", "?")
        targets = by_id.get(sid, [])
        if not targets:
            outcome.unmatched_ids.append(sid)
            continue

        def refuse(reason: str) -> None:
            outcome.refused.append({"scholarship_id": sid, "row": row, "reason": reason})
            for target in targets:
                target.issues.append(make_issue("verification_decision_rejected", "verification_status", f"decisions row {row}: {reason}"))

        value = (clean_text(decision.get("decision")) or "").casefold()
        reviewer = clean_text(decision.get("reviewer"))
        reviewed = parse_date(decision.get("reviewed_at"))
        evidence = clean_text(decision.get("evidence_url"))
        notes = clean_text(decision.get("notes"))

        if len(targets) > 1:
            refuse("scholarship_id is shared by several records; fix the duplicate id first")
        elif value not in _DECISIONS:
            refuse(f"unknown decision {value!r}; use one of {', '.join(_DECISIONS)}")
        elif not reviewer:
            refuse("reviewer is required")
        elif reviewed.status != "ok" or reviewed.value is None:
            refuse("reviewed_at must be an unambiguous date (YYYY-MM-DD)")
        elif reviewed.value > as_of:
            refuse("reviewed_at is in the future")
        elif value == "verified" and not (evidence and is_valid_url(evidence)):
            refuse("a 'verified' decision needs a valid http(s) evidence_url")
        elif value == "verified" and sid in ids_with_errors:
            refuse("record still has validation errors; fix them before verifying")
        else:
            _apply(targets[0], _DECISIONS[value], reviewer, reviewed.value, evidence, notes)
            outcome.applied.append({"scholarship_id": sid, "decision": value, "reviewer": reviewer, "reviewed_at": reviewed.value.isoformat()})
    return outcome


def _apply(
    item: NormalizedRecord,
    status: VerificationStatus,
    reviewer: str,
    reviewed_at: date,
    evidence: str | None,
    notes: str | None,
) -> None:
    record = item.record
    record.verification_status = status
    parts = [f"{status.value} by {reviewer} on {reviewed_at.isoformat()}"]
    if status is VerificationStatus.VERIFIED:
        record.last_verified_at = reviewed_at
        record.extra_attributes["verification_evidence_url"] = evidence
        parts.append(f"evidence: {evidence}")
        if not is_government_domain(evidence):
            parts.append("evidence domain is not .gov.in/.nic.in/.ac.in/.edu.in - reviewer asserts it is authoritative")
    elif evidence:
        parts.append(f"evidence: {evidence}")
    if notes:
        parts.append(notes)
    new_note = "; ".join(parts)
    record.review_notes = f"{record.review_notes} | {new_note}" if record.review_notes else new_note
