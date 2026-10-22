# Data reconciliation (Stage A)

Checked on 2026-10-12 before anything was imported. Everything was read-only.

## Which scholarship files exist

Searched `D:\`, `C:\Users\shubh\{Downloads,Desktop,Documents,OneDrive}` and `C:\` (name match on `scholar`, `mp level`, `state level`, `central`, `final`):

| File | Found? |
|---|---|
| `scholarship 1.xlsx` (`C:\Users\shubh\Downloads`) | **yes - the only scholarship workbook** |
| `SCHOLARSHIP_FINAL.xlsx`, `mp level scholarship.xlsx`, `state level scholarship.xlsx`, `central scholarship.xlsx` | **no** - not present on this machine |
| `scholarpath-data\data\processed\scholarships_cleaned.csv` / `.json`, `data\verified\scholarships_verified.csv` | yes (ETL outputs) |

The central / MP / state split mentioned for separate workbooks is *inside* `scholarship 1.xlsx` (`government_level`: CENTRAL 12, MP 8, other states 14).

## `scholarship 1.xlsx`

* `Sheet1`: 34 data rows, 20 columns. `central`: empty sheet.
* Empty in every row: `SCHOLARSHIP_ID`, `academic_year`, `application_open_date`, `deadline`, `last_verified_at`, `verification_status`.
* No exact duplicate names. The ETL flagged one *possible*-duplicate group of three similar per-category variants (MP Post-Matric SC / ST / OBC) - likely distinct schemes, kept as three records, linked by `duplicate_group_id = DG-0001`.
* SHA-256 `a3d1c0b689ee...aac9` (unchanged since the first inspection).

## Reconciliation result

| Check | Result |
|---|---|
| ETL manifest SHA-256 vs the workbook's current SHA-256 | **identical** - the cleaned outputs were produced from exactly this file |
| Workbook rows vs cleaned records | 34 = 34, same order, names equal after whitespace cleaning |
| Cleaned JSON vs cleaned CSV | 34 records each, same ids and order, **0 field differences** |
| Importer validation (`--dry-run`) of both files | 34 valid, 0 failed, 0 skipped; both formats yield identical records and identical content hashes |
| Verification status | 34 `pending`; no `last_verified_at`, no `source_url`, no deadlines |

**Authoritative input for the importer: `scholarpath-data\data\processed\scholarships_cleaned.json`** (the CSV is equivalent and also accepted).
There are no extra Excel records to reconcile, so nothing was merged. The Excel file and ETL outputs were never modified.
