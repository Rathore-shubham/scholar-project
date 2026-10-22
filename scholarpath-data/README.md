# ScholarPath Data

Data-collection foundation for **ScholarPath AI** (final-year B.Tech project): load scholarship
records for students in India, clean them into one canonical schema, validate them, flag possible
duplicates, and export them — **without ever marking a record "verified" on its own**.

This first stage works entirely on local files. No web scraping, no API calls, no database, no
LLM/embeddings. See [Source integration status](#source-integration-status) for what is pending.

## Contents

[Requirements](#requirements) · [Install](#install) · [Run](#run) · [Directory structure](#directory-structure) ·
[Input](#input-formats) · [Output](#output-files) · [Schema](#canonical-schema) ·
[Normalization policy](#normalization-policy) · [Validation rules](#validation-rules) ·
[Duplicates](#duplicate-detection) · [Verification workflow](#verification-workflow) ·
[Tests](#tests) · [Known limitations](#known-limitations) · [Adding a source](#adding-a-new-data-source) ·
[Source status](#source-integration-status)

## Requirements

- **Python 3.11 or newer** (developed and tested on 3.12).
- `pandas`, `openpyxl`, `pydantic`, and `pytest` (for the tests). Pinned ranges are in [requirements.txt](requirements.txt).
- `requests`, `beautifulsoup4` and `pymupdf` are deliberately **not** installed yet; they are added when
  permitted HTML/API extraction and PDF parsing are built.

> **pandas version note:** `requirements.txt` caps pandas at `<3.0.6`. On the development machine a
> Windows *Application Control* policy blocked one compiled module of pandas 3.0.6
> (`ImportError: DLL load failed ... An Application Control policy has blocked this file`), while 3.0.5
> works. Do not try to bypass such a policy; just install a version that runs, and raise the cap on a
> machine without the restriction.

## Install

PowerShell (Windows):

```powershell
cd D:\major\scholarpath-data
python -m venv .venv
.venv\Scripts\Activate.ps1            # if scripts are blocked: use .venv\Scripts\python.exe everywhere instead
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps  # makes `python -m scholarpath_data` work from any folder
```

macOS / Linux / Git Bash:

```bash
cd scholarpath-data
python -m venv .venv && source .venv/bin/activate    # Git Bash on Windows: source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

No environment variables, API keys or secrets are needed. Never commit any.

## Run

**1. Inspect a file first (read-only; writes nothing):**

```powershell
python -m scholarpath_data.load_excel --input "C:\Users\shubh\Downloads\scholarship 1.xlsx"
```

Shows sheets, header row, row counts, per-column missing/distinct counts, Python types, a sample
value, and which canonical field each column maps to. `--json` prints machine-readable output;
`--sheet NAME` limits it to one sheet.

**2. Run the full pipeline:**

```powershell
python -m scholarpath_data --input "C:\Users\shubh\Downloads\scholarship 1.xlsx" --output-dir data
```

The original file is only read. Everything is written under `--output-dir`. Safe to rerun: see
[Reruns](#reruns).

| Option | Meaning |
|---|---|
| `--input`, `-i` | `.xlsx` / `.xlsm` / `.csv`. If omitted, uses the single such file in `<output-dir>/raw/` or the current folder; errors if there are none or several. |
| `--output-dir`, `-o` | Root holding `raw/ processed/ verified/ reports/` (default `./data`). |
| `--sheet` | Only process this sheet (repeatable). Default: every non-empty sheet. |
| `--source-name` | Value for `source_name` (default: the file name). |
| `--source-type` | `source_type` (default `local_excel` / `local_csv`). |
| `--decisions` | Reviewer-decisions CSV (default `<output-dir>/verified/verification_decisions.csv` if present). |
| `--as-of YYYY-MM-DD` | Date for "deadline passed" / "outdated" checks (default today). |
| `--duplicate-threshold` | Name similarity 0-1 for possible duplicates (default `0.90`). |
| `--max-verification-age-days` | Verified records older than this are flagged outdated (default 365). |
| `--quiet`, `--debug` | Summary only / show tracebacks for unexpected errors. |

Exit codes: `0` success · `2` problem with the input/output you gave (missing file, unsupported type,
unreadable workbook, bad option) · `1` unexpected error · `130` interrupted. Expected problems print a
one-line `error: ...` with a hint, not a traceback.

Without activating the venv: `.venv\Scripts\python.exe -m scholarpath_data ...`. Installed console
commands `scholarpath-data` and `scholarpath-inspect` are equivalent.

## Directory structure

```
scholarpath-data/
  data/
    raw/         verbatim, text-only copy of every sheet + manifest.json (SHA-256) - never cleaned
    processed/   scholarships_cleaned.csv / .json   (normalized + validated, still UNverified)
    verified/    scholarships_verified.csv (reviewer-confirmed only) + your verification_decisions.csv
    reports/     data_quality_report.json, possible_duplicates.csv
  src/scholarpath_data/
    schema.py        canonical pydantic model, enums, issue catalog
    load_excel.py    find / load / inspect xlsx+csv, raw snapshot      (CLI: inspect)
    parsers.py       pure parsers: text, numbers, dates, URLs, states
    normalize.py     column-name normalization, mapping, row -> record
    validate.py      record-level and cross-record rules
    deduplicate.py   possible-duplicate grouping
    verification.py  reviewer decisions - the only path to `verified`
    export.py        deterministic CSV / JSON writers
    pipeline.py      orchestration + report + CLI                      (CLI: run)
    reference.py, errors.py, fileio.py, console.py   support code
  tests/             pytest, synthetic fixtures only, no network
  requirements.txt   pyproject.toml
```

## Input formats

- **Excel** `.xlsx` / `.xlsm` (read-only; formulas are read as their last cached value) and **CSV**
  (UTF-8 with or without BOM, or Windows-1252; `,` `;` tab or `|` delimiter detected). Legacy `.xls` is
  rejected with a hint to *Save As .xlsx*.
- Every non-empty sheet is loaded; empty sheets are reported and skipped.
- The header is the first row with at least two non-empty cells (title rows above it are ignored).
  Empty trailing columns, blank rows and fully-empty rows are dropped; **row numbers always match the
  original sheet**, so `source_row` can be used to find a record in Excel.
- Column names are normalized to `snake_case` (`Scholarship Name` -> `scholarship_name`) and mapped to
  canonical fields through an alias table (`_ALIASES` in [normalize.py](src/scholarpath_data/normalize.py)),
  e.g. `provider`/`department` -> `provider_name`, `min_percentage` -> `minimum_percentage`,
  `deadline`/`last_date` -> `application_deadline`. **Unmapped columns are never dropped**; they are kept in
  `extra_attributes`. If two columns claim the same field, the first wins and the other is kept in
  `extra_attributes`.
- Source-only columns used for the canonical fields: `government_level` -> `scheme_type`;
  `amount` -> `award_amount_min/max`; `key benefits` -> `award_amount_text`; `gender` -> `extra_attributes`
  (and `eligibility_rules` when restricted).

## Output files

| File | Content |
|---|---|
| `raw/<stem>-<sha8>/<sheet>.csv` | Every cell as text exactly as in the source (+ `source_row`). |
| `raw/<stem>-<sha8>/manifest.json` | File name, SHA-256, size, sheets/columns/row counts, first extraction time. |
| `processed/scholarships_cleaned.csv` | One row per source record; UTF-8 **with BOM** so Excel shows `₹`. |
| `processed/scholarships_cleaned.json` | `{schema_version, record_count, records:[...]}`; same fields, native lists. |
| `verified/scholarships_verified.csv` | Only records with `verification_status = verified` (header-only until you review). |
| `reports/data_quality_report.json` | Counts, issues, completeness, mapping, decisions, flagged records. |
| `reports/possible_duplicates.csv` | One row per member of each possible-duplicate group. |

Representation rules (identical in CSV and JSON): dates `YYYY-MM-DD`; `extracted_at` ISO-8601 UTC;
missing = JSON `null` / empty CSV cell (**never `0`**); list/object fields are native in JSON and
**JSON text in CSV** (e.g. `["SC","ST"]`) so they round-trip exactly; whole numbers print without
`.0`. Records keep the source order (sheet order, then row order).

### `data_quality_report.json`

`counts` (all computed from the records): `total_input_records`, `successfully_parsed_records`,
`records_failed_to_parse`, `records_with_validation_errors`, `records_with_warnings`,
`records_without_errors_or_warnings`, `possible_duplicate_groups`, `records_in_possible_duplicate_groups`,
`records_marked_verified`, `records_pending_review` (= `pending` + `needs_review`). Also:
`verification_status_counts`, `issue_summary` (per code: severity, records affected, fields),
`field_completeness` (present/missing per canonical field), `columns` (source column -> canonical field,
unmapped columns, canonical fields the source has no column for), `ids`, `verification_decisions`, and
`records_needing_attention` (every record with an error or warning and its issues, by `source_row`).

### Reruns

The pipeline is rerunnable: the same input produces the same records, ids and files. Unchanged
output files are not rewritten; the raw folder is named by file hash, so an identical file reuses it
and a *changed* file gets a **new** raw folder (earlier raw data is kept). `extracted_at` is stored in the
manifest and reused for identical content. Only `generated_at` in the report changes between reruns.
The pipeline refuses an `--input` that is one of its own output files.

## Canonical schema

Defined and validated by the pydantic model `ScholarshipRecord` in [schema.py](src/scholarpath_data/schema.py).
Conventions: unknown scalar = `null`; unknown collection = `[]`; `["ALL"]` = the source explicitly says
"all" (courses / states / categories / levels); anything with no canonical column goes to `extra_attributes`.
The model checks structure and types; *business* rules (ranges, date order, URL format) live in
`validate.py`, so a bad value is reported instead of making the record unparseable.

| Field | Type | Meaning |
|---|---|---|
| `scholarship_id` | str | Source id if present, else a deterministic id `SP-<10 hex>` hashed from name + provider + government level (repeated ids get `-2`, `-3`). |
| `scholarship_name` | str, nullable | Scheme name (whitespace-cleaned only). |
| `provider_name` | str, nullable | Ministry / department / organisation. |
| `scheme_type` | `central` / `state` / `other`, nullable | Derived from the source's government level (`CENTRAL` -> central, a recognised state -> state). |
| `academic_year` | str, nullable | `YYYY-YY` only when stated unambiguously (a bare `2024` is not guessed). |
| `education_level` | list[str] | Tokens as written (`12`, `UG`, `PG`...), order kept, duplicates removed. |
| `eligible_courses` | list[str] | Course/stream tokens; `["ALL"]` for "ALL COURSES" / "ALL STREAMS". |
| `eligible_states` | list[str] | Canonical state/UT names (`MP` -> Madhya Pradesh); `["ALL"]` = all states. |
| `eligible_categories` | list[str] | Upper-case codes (`SC`, `ST`, `OBC`, `EWS`...); `["ALL"]`. |
| `minimum_percentage` | float, nullable | One plain number only (`60`, `60%`). Board-specific text is **not** converted. |
| `maximum_family_income` | float, nullable | One annual ceiling in INR (`<8,00,000` -> 800000). Tiers, ranges and per-category limits are **not** converted. Missing is never 0. |
| `award_amount_min` / `award_amount_max` | float, nullable | A single plain number (both equal) or an explicit `A - B` range. Tiered/worded amounts stay empty. Assumed INR; the period (month/year) is **not** captured. |
| `award_amount_text` | str, nullable | Source's benefit description (`key benefits`); falls back to the raw `amount` text only when it could not be parsed. |
| `application_open_date`, `application_deadline` | date, nullable | Only unambiguous dates (see below). |
| `required_documents` | list[str] | Split on `, ; \|` / newline. |
| `eligibility_rules` | list[str] | Source conditions no column can hold, **quoted as stated, never interpreted**, e.g. `Family income limit (as stated in source): HIGHER ED. - 120000,SCHOOL-54000`. |
| `application_procedure` | str, nullable | Free text. |
| `official_url` | str, nullable | First valid URL found in the source cell. |
| `source_url` | str, nullable | Where the record was extracted from (null for local files). |
| `source_name` | str, nullable | Defaults to the file name. |
| `source_type` | enum | `local_excel`, `local_csv`, `myscheme`, `data_gov_in`, `huggingface`, `nsp`, `manual`, `other`. |
| `extracted_at` | datetime (UTC) | When this exact file content was first extracted. |
| `last_verified_at` | date, nullable | Set only by a reviewer decision. |
| `verification_status` | enum | `pending` (default) / `needs_review` / `verified` / `rejected`. |
| `review_notes` | str, nullable | Pipeline notes + reviewer notes (appended with ` \| `). |

Pipeline metadata (not part of the 27 canonical fields): `source_record_id` (id exactly as in the
source, null if none), `source_file`, `source_sheet`, `source_row`, `duplicate_group_id`,
`validation_status` (`ok` / `warning` / `error`), `validation_issue_codes` (warnings and errors),
`extra_attributes`.

Keys you may find in `extra_attributes`: `gender`, `government_level`, `<field>_raw` (original text of a value
that could not be read unambiguously), `maximum_family_income_comparator` (`<` or `<=` when the source gave
one), `official_urls_all`, `provider_raw`, `amount_raw`, `verification_evidence_url`, and any unmapped source column.

## Normalization policy

1. **Clean:** trim, collapse whitespace (including non-breaking and zero-width characters), and turn these into
   "missing": empty, `nan`, `none`, `null`, `nil`, `n/a`, `na`, `-`, `--`, `—`, `?`, `unknown`, `not available`,
   `not applicable`, `tbd`. (A real `0` is kept.)
2. **Convert only when unambiguous.** Numbers: Indian (`3,00,000`) or western grouping, optional `₹`/`Rs`/`INR`,
   `lakh`/`crore`. Income may carry a `<`, `up to`, `below`... prefix. Dates: ISO; `DD/MM/YYYY` or
   `MM/DD/YYYY` **only** when one side is > 12 (or both are equal); month names (`31 Mar 2026`). `03/04/2026`
   is **ambiguous** and left empty.
3. **If a value is present but not unambiguous**, the canonical field stays `null`, the original text is kept
   (`extra_attributes.<field>_raw` and, for eligibility conditions, `eligibility_rules`), and a *warning* is raised.
4. **If a value is present but invalid** (e.g. a malformed URL), it is kept as-is and the validator raises an *error*.
5. A provider that merely repeats the scheme name is not a provider: it is set to `null`, kept in
   `extra_attributes.provider_raw`, and warned.
6. URL cells such as `https://a.gov.in (Portal)` or `https://a.gov.in / https://b.gov.in` yield the first
   well-formed URL; all of them are kept in `extra_attributes.official_urls_all` when several are present.
7. A source `verification_status` of `verified` is **not trusted** (becomes `needs_review`).
8. Nothing is dropped, merged or invented: every source row becomes one record.

## Validation rules

Severity: **error** = a value is present but invalid/contradictory · **warning** = important information is
unavailable, ambiguous or unconfirmed · **info** = optional information simply is not in the source.
A missing optional field is never an error. Records with errors are still exported (flagged), never silently dropped.

| Code | Severity | Meaning |
|---|---|---|
| `missing_scholarship_name` | error | Scholarship name is missing. |
| `invalid_url` | error | `official_url` / `source_url` is not a valid http(s) URL. |
| `date_invalid` | error | Looks like a date but is not a real date (e.g. 31/02/2026). |
| `deadline_before_open_date` | error | Deadline earlier than opening date (when both known). |
| `negative_income` / `negative_amount` | error | Negative income limit or award amount. |
| `amount_min_exceeds_max` | error | Minimum award greater than maximum. |
| `percentage_out_of_range` | error | Minimum percentage outside 0-100. |
| `duplicate_scholarship_id` | error | Same `scholarship_id` on several records. |
| `verified_without_evidence` | error | Status `verified` but no `last_verified_at` or no valid source URL. |
| `missing_provider` | warning | No provider. |
| `official_url_missing` | warning | No official URL. |
| `missing_academic_year` | warning | No academic year. |
| `missing_eligibility_details` | warning | None of level/courses/states/categories/percentage/income/rules present. |
| `percentage_not_numeric` / `income_not_numeric` / `amount_not_numeric` | warning | Value could not be read unambiguously; kept as text. |
| `percentage_possibly_fraction` | warning | Percentage between 0 and 1 (may be a fraction). |
| `date_ambiguous` / `date_unparsed` | warning | Date could be DD/MM or MM/DD / not a date at all; left empty. |
| `academic_year_unparsed` | warning | Not a recognizable `YYYY-YY`. |
| `provider_copies_scheme_name` | warning | Provider column repeats the scheme name. |
| `unrecognized_state` | warning | State name not in the reference list (kept as written). |
| `duplicate_scholarship_name` / `possible_duplicate` | warning | Same normalized name / similar name as another record. |
| `record_needs_review` | warning | Status is `needs_review`. |
| `verification_claim_unconfirmed` / `verification_status_unrecognized` | warning | Source status not trusted → `needs_review`. |
| `verification_outdated` | warning | Verified longer ago than `--max-verification-age-days`. |
| `deadline_passed` | warning | Deadline is before `--as-of`; record may be outdated. |
| `verification_decision_rejected` | warning | A reviewer decision was not applied (reason given). |
| `source_url_missing`, `missing_application_open_date`, `missing_application_deadline`, `unverified_record`, `record_rejected`, `scheme_type_unmapped`, `official_url_multiple`, `official_url_cleaned`, `official_url_non_government_domain` | info | Informational. |

Every code, its severity and message is defined in one place: `ISSUE_CATALOG` in [schema.py](src/scholarpath_data/schema.py).
Because academic year is missing in many sources, expect the `missing_academic_year` warning to put most records
under "records with warnings"; use `issue_summary` to see what else is flagged.

## Duplicate detection

[deduplicate.py](src/scholarpath_data/deduplicate.py) compares **normalized** names (case, punctuation, `&`/`and`
ignored) and providers, then groups candidates (`DG-0001`, ...):

| `group_match_type` | Meaning | Confidence |
|---|---|---|
| `exact_name_and_provider` | Same normalized name and the same non-empty provider | high |
| `same_name_different_provider` | Same name; provider differs **or is unknown** | medium |
| `similar_name` | Names are >= threshold similar (difflib ratio, default 0.90) | low |

**Nothing is merged or deleted**; groups are only flagged (`duplicate_group_id`, a warning, and a row per member in
`possible_duplicates.csv` with `source_record_id`, `source_file`, `source_sheet`, `source_row`).
`distinguishing_words` lists name words that differ inside the group (e.g. `sc st`), which usually shows
immediately that per-category variants are *different* schemes.

## Verification workflow

`verified` means: **a named human compared the record to an authoritative source and recorded the evidence.**
The pipeline never sets it by itself; running it successfully proves nothing about correctness.

1. Run the pipeline. All records are `pending`.
2. Review records (start with `reports/data_quality_report.json` -> `records_needing_attention`, and
   `possible_duplicates.csv`). Check each against its official page.
3. Record decisions in `data/verified/verification_decisions.csv` (header in `verification_decisions.template.csv`):

   ```csv
   scholarship_id,decision,reviewer,reviewed_at,evidence_url,notes
   SP-469A4D1B8C,verified,Your Name,2026-10-12,https://scholarships.gov.in/...,Matches NSP scheme page
   ```

   `decision`: `verified` / `needs_review` / `rejected` / `pending`. Append new rows at the bottom; **a later row for
   the same id overrides an earlier one**.
4. Rerun the pipeline. A `verified` decision is applied only if: the id matches exactly one record; `reviewer` is
   set; `reviewed_at` is an unambiguous, non-future date; `evidence_url` is a valid http(s) URL; and the record has
   **no validation errors**. Otherwise it is refused, the record keeps its status, and the reason appears in
   the record's issues and in `verification_decisions.refused` in the report. Unknown ids are listed in
   `unmatched_scholarship_ids`. Applied decisions set `last_verified_at`, append to `review_notes`, store
   `extra_attributes.verification_evidence_url`, and the record appears in `verified/scholarships_verified.csv`.
5. `scholarship_id` is a hash of name + provider + government level: if you later change one of those in the source,
   the id changes and earlier decisions become *unmatched* (reported, not lost).
6. Verified records older than 365 days are flagged `verification_outdated`.

## Tests

```powershell
python -m pytest
```

291 tests using small synthetic fixtures (no network, no real data): loading Excel/CSV, column normalization,
missing values, date and amount parsing, invalid URLs, duplicate detection, schema validation, CSV/JSON export,
original-file preservation, repeated runs, verification rules and CLI exit codes.

## Known limitations

- **Local files only.** No source is downloaded or scraped yet (see below).
- Awards: only single numbers/explicit ranges become numeric; **currency and period (per month / per year) are not
  captured** (assumed INR; read `award_amount_text`). Amounts mentioned only inside the benefits text are not extracted.
- `education_level` is kept as written. In the initial dataset `12` can mean "completed Class 12" for one scheme
  and "studying Class 12" for another; the pipeline does not reinterpret it.
- `minimum_percentage` cannot distinguish a *percentage* from a *percentile* or from a rank cut-off. Review numbers
  such as the `80` on the CSSS row against the official scheme page.
- Tokens are not repaired: `B.Tech.MBBS` (probably two courses missing a comma) and `UG`/`PG` inside
  `required_documents` are kept as written. Review them manually.
- Ambiguous numeric dates (`03/04/2026`) are left empty rather than assumed DD/MM; there is no `--dayfirst` option yet.
- State recognition covers states/UTs and common abbreviations (`MP`, `UP`, `WB`...). Others are kept as written and warned.
- Domain check (`.gov.in`, `.nic.in`, `.ac.in`, `.edu.in`, `.res.in`) is informational: official sites on other domains
  (e.g. `aicte-india.org`) get an *info* note, and the reviewer decides whether they are authoritative.
- Duplicate detection is O(n²); fine for thousands of rows, add blocking before scaling further.
- Excel formulas are read as cached values; a workbook never opened in Excel after being generated by a script may show
  empty formula cells.
- The generated `scholarship_id` changes if name, provider or government level change (see Verification workflow).
- Hyperlink *targets* of Excel cells are not read; the visible cell text is used.

## Adding a new data source

1. **Check permission first.** Read the site's terms and robots rules; prefer an official API or downloadable dataset.
   Do not bypass authentication, CAPTCHAs, paywalls or rate limits. Treat third-party datasets as *candidates*, not truth.
2. **Fetch into the raw layer** (a new module, e.g. `sources/myscheme.py`; add `requests` to requirements then): save the
   response/file untouched under `data/raw/<source>/`, with a manifest (URL, retrieval time, hash).
3. **Produce rows**, then reuse the pipeline: either write them to CSV and run `python -m scholarpath_data --input ...
   --source-type <type> --source-name "<label>"`, or build a `LoadedSource` and call `normalize_sheet`.
4. **Map columns**: add the new source's column names to `_ALIASES` in `normalize.py` (anything unmapped lands in
   `extra_attributes` automatically). Set `source_url` for every record, since remote sources have one.
5. **Extend the enum** `SourceType` in `schema.py` if needed (already includes `myscheme`, `data_gov_in`, `huggingface`, `nsp`).
6. **Add tests** with a tiny synthetic fixture. Never rely on the network in tests.
7. **Deduplicate across sources** by running the combined records through `find_duplicate_groups`; review the groups,
   do not auto-merge. New-source records start as `pending`.

## Source integration status

| Source | Status |
|---|---|
| Local file `scholarship 1.xlsx` (provided by the project owner) | **Integrated** - loaded, normalized, validated; unverified. |
| myScheme (`myscheme.gov.in`) | **Pending.** Needs a permission/terms check and an official API or dataset first. |
| Open Government Data (`data.gov.in`) | **Pending.** Check for a downloadable scholarship dataset / official API (may need an API key; never commit keys). |
| Hugging Face `Navraj025/gov_myscheme` | **Pending.** Candidate dataset, not ground truth; check licence, then import as `source_type=huggingface`, status `pending`. |
| National Scholarship Portal (`scholarships.gov.in`) | **Pending.** Likely the best verification evidence source; no scraping without confirmed permission. |
