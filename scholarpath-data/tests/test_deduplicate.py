"""Duplicate detection: grouping, match types, no merging."""

from __future__ import annotations

from conftest import NOW
from scholarpath_data.deduplicate import EXACT, SAME_NAME, SIMILAR, duplicate_issues, duplicate_rows, find_duplicate_groups
from scholarpath_data.schema import ScholarshipRecord


def rec(sid: str, name: str | None, provider: str | None = "Dept", **kw: object) -> ScholarshipRecord:
    return ScholarshipRecord(scholarship_id=sid, scholarship_name=name, provider_name=provider, extracted_at=NOW, **kw)


def test_no_duplicates_in_distinct_records() -> None:
    records = [rec("1", "National Means-cum-Merit Scholarship"), rec("2", "AICTE Pragati Scholarship Scheme"), rec("3", "Kanyashree Prakalpa")]
    assert find_duplicate_groups(records) == []


def test_same_name_and_provider_ignoring_case_punctuation_and_spacing() -> None:
    records = [rec("1", "Post-Matric Scholarship (SSP)", "Social Welfare Dept."), rec("2", "post matric  scholarship SSP", "social welfare dept"), rec("3", "Other")]
    (group,) = find_duplicate_groups(records)
    assert group.match_type == EXACT and group.members == (0, 1) and group.min_similarity == 1.0


def test_same_name_different_or_unknown_provider_is_lower_confidence() -> None:
    (g1,) = find_duplicate_groups([rec("1", "Merit Award", "A"), rec("2", "Merit Award", "B")])
    assert g1.match_type == SAME_NAME
    (g2,) = find_duplicate_groups([rec("1", "Merit Award", None), rec("2", "Merit Award", None)])
    assert g2.match_type == SAME_NAME  # unknown providers cannot confirm identity


def test_similar_names_above_threshold_are_grouped_and_below_are_not() -> None:
    records = [rec("1", "Post Matric Scholarship Scheme for SC Students"), rec("2", "Post Matric Scholarship Scheme for ST Students")]
    (group,) = find_duplicate_groups(records, threshold=0.9)
    assert group.match_type == SIMILAR and 0.9 <= group.min_similarity < 1
    assert set(group.distinguishing_tokens) == {"sc", "st"}  # tells the reviewer what differs
    assert find_duplicate_groups(records, threshold=0.99) == []


def test_groups_are_transitive_and_numbered_deterministically() -> None:
    records = [rec("1", "Alpha Scholarship Yojana"), rec("2", "Zeta Different"), rec("3", "Alpha Scholarship Yojna"), rec("4", "Alpha Scholarship Yojanaa"), rec("5", "Zeta Different")]
    groups = find_duplicate_groups(records)
    assert [g.group_id for g in groups] == ["DG-0001", "DG-0002"]
    assert groups[0].members == (0, 2, 3) and groups[1].members == (1, 4)
    assert groups == find_duplicate_groups(records)  # rerun gives the same result


def test_records_without_names_are_never_matched() -> None:
    assert find_duplicate_groups([rec("1", None), rec("2", None), rec("3", "")]) == []


def test_records_are_not_modified_or_removed_by_detection() -> None:
    records = [rec("1", "Same Name", "A"), rec("2", "Same Name", "A")]
    snapshot = [r.model_dump() for r in records]
    find_duplicate_groups(records)
    assert [r.model_dump() for r in records] == snapshot and len(records) == 2


def test_issue_codes_depend_on_match_strength() -> None:
    records = [rec("1", "Same Name", "A"), rec("2", "Same Name", "A"), rec("3", "Other Scheme For Girls"), rec("4", "Other Scheme For Girl")]
    groups = find_duplicate_groups(records)
    issues = duplicate_issues(groups, records)
    assert issues[0][0].code == "duplicate_scholarship_name" and "2" in issues[0][0].message
    assert issues[2][0].code == "possible_duplicate"
    assert set(issues) == {0, 1, 2, 3}


def test_report_rows_keep_original_identifiers_and_source_references() -> None:
    records = [
        rec("1", "Same Name", "A", source_record_id="ORIG-7", source_file="f.xlsx", source_sheet="S", source_row=5, eligible_states=["Bihar"]),
        rec("2", "Same Name", "A", source_file="f.xlsx", source_sheet="S", source_row=9),
    ]
    rows = duplicate_rows(find_duplicate_groups(records), records)
    assert [r["source_row"] for r in rows] == [5, 9]
    assert rows[0]["source_record_id"] == "ORIG-7" and rows[0]["eligible_states"] == "Bihar"
    assert {r["group_id"] for r in rows} == {"DG-0001"} and rows[0]["group_size"] == 2
