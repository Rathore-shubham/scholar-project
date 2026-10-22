"""CSV / JSON exports: representation rules, round trips, determinism."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from conftest import NOW
from scholarpath_data.export import record_to_dict, rows_to_csv_text, write_dict_rows_csv, write_json, write_records_csv, write_records_json, write_verified_csv
from scholarpath_data.schema import ALL_FIELDS, ScholarshipRecord


def rec(sid: str = "SP-1", **kw: object) -> ScholarshipRecord:
    base: dict[str, object] = dict(
        scholarship_id=sid, scholarship_name="Alpha ₹ Scholarship", provider_name="Ministry", eligible_states=["Madhya Pradesh", "Ladakh"],
        eligible_categories=["SC", "ST"], maximum_family_income=800000.0, minimum_percentage=60.5, award_amount_min=12000, award_amount_max=12000,
        application_deadline=date(2026, 3, 31), extracted_at=NOW, extra_attributes={"gender": ["FEMALE"], "n": 2.0},
    )
    base.update(kw)
    return ScholarshipRecord(**base)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_json_export_structure_types_and_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    records = [rec("SP-1"), rec("SP-2", scholarship_name=None, eligible_states=[])]
    assert write_records_json(records, path) is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 2 and payload["schema_version"] == "1"
    first, second = payload["records"]
    assert list(first) == list(ALL_FIELDS)  # canonical order, every field present
    assert first["eligible_states"] == ["Madhya Pradesh", "Ladakh"]  # native list in JSON
    assert first["maximum_family_income"] == 800000 and isinstance(first["maximum_family_income"], int)
    assert first["minimum_percentage"] == 60.5
    assert first["application_deadline"] == "2026-03-31"
    assert first["extracted_at"] == "2026-01-15T10:00:00Z"
    assert first["verification_status"] == "pending" and first["source_type"] == "other"
    assert first["extra_attributes"] == {"gender": ["FEMALE"], "n": 2}
    assert second["scholarship_name"] is None and second["eligible_states"] == []
    assert "₹" in path.read_text(encoding="utf-8")  # not escaped


def test_csv_export_header_cells_and_list_encoding(tmp_path: Path) -> None:
    path = tmp_path / "out.csv"
    write_records_csv([rec(), rec("SP-2", scholarship_name=None, maximum_family_income=None)], path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM so Excel shows the rupee sign
    rows = read_csv(path)
    assert list(rows[0]) == list(ALL_FIELDS)
    one, two = rows
    assert one["scholarship_name"] == "Alpha ₹ Scholarship"
    assert json.loads(one["eligible_states"]) == ["Madhya Pradesh", "Ladakh"]  # JSON text round-trips
    assert json.loads(one["extra_attributes"]) == {"gender": ["FEMALE"], "n": 2}
    assert one["maximum_family_income"] == "800000.0" or one["maximum_family_income"] == "800000"
    assert one["application_deadline"] == "2026-03-31"
    assert two["scholarship_name"] == "" and two["maximum_family_income"] == ""  # missing -> empty, never 0
    assert two["required_documents"] == "[]"


def test_csv_and_json_agree_field_by_field(tmp_path: Path) -> None:
    records = [rec("SP-1"), rec("SP-2", award_amount_text="₹5,000 per month")]
    write_records_csv(records, tmp_path / "a.csv")
    write_records_json(records, tmp_path / "a.json")
    from_json = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["records"]
    for csv_row, json_row in zip(read_csv(tmp_path / "a.csv"), from_json):
        for name in ALL_FIELDS:
            value = json_row[name]
            if isinstance(value, (list, dict)):
                assert json.loads(csv_row[name]) == value, name
            elif value is None:
                assert csv_row[name] == "", name
            else:
                assert csv_row[name] == str(value), name


def test_integral_numbers_have_no_trailing_zero() -> None:
    row = record_to_dict(rec())
    assert row["award_amount_min"] == 12000 and isinstance(row["award_amount_min"], int)
    assert "800000.0" not in rows_to_csv_text([row], ALL_FIELDS)


def test_verified_export_contains_only_verified_records(tmp_path: Path) -> None:
    path = tmp_path / "v.csv"
    write_verified_csv([rec("A"), rec("B", verification_status="verified"), rec("C", verification_status="needs_review")], path)
    assert [r["scholarship_id"] for r in read_csv(path)] == ["B"]
    write_verified_csv([rec("A")], path)
    assert read_csv(path) == [] and path.read_text(encoding="utf-8-sig").startswith("scholarship_id,")  # header-only


def test_unchanged_content_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "o.json"
    assert write_records_json([rec()], path) is True
    mtime = path.stat().st_mtime_ns
    assert write_records_json([rec()], path) is False
    assert path.stat().st_mtime_ns == mtime
    assert write_records_json([rec(scholarship_name="Changed")], path) is True


def test_no_temp_files_are_left_behind(tmp_path: Path) -> None:
    write_records_csv([rec()], tmp_path / "x.csv")
    write_json({"a": 1.0}, tmp_path / "x.json")
    write_dict_rows_csv([{"a": 1, "b": None}], ["a", "b"], tmp_path / "y.csv")
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "x.json").read_text()) == {"a": 1}
    assert read_csv(tmp_path / "y.csv") == [{"a": "1", "b": ""}]
