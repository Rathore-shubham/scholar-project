# ScholarPath Backend

FastAPI service for ScholarPath AI: scholarship search, scholarship detail and rule-based eligibility checks,
backed by PostgreSQL and fed by the cleaned output of the ETL in `..\scholarpath-data`.

## Status: what is done, and what still needs PostgreSQL

| | Implemented and tested | Needs a configured PostgreSQL |
|---|---|---|
| App, config, CORS, Swagger, `GET /health`, `GET /health/db` | yes | `/health/db` reports `ok` only with a database |
| SQLAlchemy models, Pydantic schemas, repository + service layers | yes (queries run on in-memory SQLite in tests) | running them on PostgreSQL |
| Alembic migration `0001_initial_schema` | written; its PostgreSQL SQL is verified **offline** against the models | **not run yet** - no database schema exists |
| Importer (validate, map, upsert, report) | yes (transactions and reruns tested on SQLite; `--dry-run` works on the real files) | **no real import has been done** |
| `GET /api/v1/scholarships`, `/scholarships/{id}`, `/meta/filters`, `POST /api/v1/eligibility/check` | yes (stubbed repository + SQLite) | they answer `503 database_not_configured` until a database is set up |
| Eligibility engine | yes (pure, deterministic) | - |

> No database, role or schema has been created. Nothing here claims PostgreSQL is connected or migrated.
> Until you complete **[Configure PostgreSQL Later](#configure-postgresql-later)**, data endpoints return an honest
> `503` with `"code": "database_not_configured"` - never placeholder scholarships.

SQLite is used **only as a test harness**: it executes the repository/importer SQL in unit tests without a server.
PostgreSQL-specific behaviour (JSONB, `BIGSERIAL`, real constraint enforcement on your server) is covered only by the
offline migration check until you run the migration on a real database.

## Setup (PowerShell)

```powershell
cd D:\major\scholarpath-backend
python -m venv .venv                      # Python 3.12
.venv\Scripts\Activate.ps1                # or call .venv\Scripts\python.exe directly
python -m pip install -r requirements.txt
copy .env.example .env                    # optional for now; edit it later (Git ignores it)
```

The app starts **without** a database; `/health` works regardless.

## Run

```powershell
uvicorn app.main:app --reload --port 8001
```

Port **8001** (8000 was already taken on this machine; any free port works - update the frontend's `NEXT_PUBLIC_API_URL`).
Swagger UI: <http://127.0.0.1:8001/docs> · ReDoc `/redoc` · OpenAPI `/openapi.json`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness. Never touches the database. |
| `GET /health/db` | `200 {"status":"ok"}`, or `503` with `not_configured` / `unavailable` (never leaks URL, host or credentials). |
| `GET /api/v1/scholarships` | Paginated search (below). |
| `GET /api/v1/scholarships/{scholarship_id}` | Detail: criteria (with review status + evidence), documents, dates, sources, provenance, verification. `404` + `scholarship_not_found`. |
| `GET /api/v1/meta/filters` | Values that exist in the stored data (states, education levels, categories, genders, scheme types, counts) for filter dropdowns. |
| `POST /api/v1/eligibility/check` | Rule-based check for 1-50 scholarships (below). |

**Search parameters** (`GET /api/v1/scholarships`): `q` (name, provider, benefits, level, states, courses; all words must match),
`state`, `education_level` (label `Undergraduate` or token `UG`/`12`), `category`, `gender`, `scheme_type` (`central|state|other`),
`student_percentage`, `student_income`, `min_award`, `verified_only`, `ids` (comma-separated, max 50),
`sort` (`name` default, `amount_desc`, `deadline`, `recently_verified`; unknown values sort last), `page` (>=1), `page_size` (1-50, default 12).
Response: `{items, total, page, page_size, pages}`.

Search semantics:
* **Rejected** records are never returned.
* **Unverified records are returned by default**, each with `verification_status`, `is_verified` and a plain-language `data_notice`
  ("Unverified: ... do not treat it as a confirmed, currently available opportunity"). Use `verified_only=true` for the verified set
  (today: empty - nothing is verified).
* A value filter (`state`, `education_level`, `category`, `gender`) matches records that list that value **or `ALL`**. Records that are
  silent about the attribute do not match an explicit filter.
* `student_percentage` / `student_income` keep records whose requirement is unknown (null) or satisfied. Null is never treated as 0.
* Missing information stays `null` in responses (`application_deadline`, `source_url`, amounts...). Nothing is invented.

**Errors** are `{"detail": "...", "code": "..."}`: `database_not_configured`, `database_unavailable`, `database_not_migrated`
(all `503`), `scholarship_not_found` (`404`), `invalid_education_level` / `invalid_gender` / `invalid_ids` (`422`). Request-validation errors use FastAPI's standard `422` body.

### Eligibility

`POST /api/v1/eligibility/check` with `{"profile": {...}, "scholarship_ids": ["SP-..."]}`. Every profile field is optional
(`state`, `education_level`, `percentage`, `family_income`, `category`, `gender`, `course`); unknown fields (e.g. an Aadhaar number) are refused.
Each result has `outcome` (`eligible` | `not_eligible` | `cant_tell_yet`), a `summary`, `missing_information`, `limitations`, and per-criterion rows
with the required value, the student's value, `status` (`pass` | `fail` | `missing` | `unable_to_verify`), a plain-language `explanation`, `reliable`
and `evidence` (text / URL / the ETL source reference).

* `eligible` / `not_eligible` are returned **only** when the scholarship is `verified` and the deciding mandatory criteria are `reviewed` **and**
  backed by evidence. Otherwise: `cant_tell_yet`.
* Criteria derived from the ETL are always `unreviewed` with no evidence, so on today's data (34 `pending` records) **every result is `cant_tell_yet`**.
  `indicative` (`all_listed_criteria_met` | `some_criteria_not_met` | `incomplete` | `no_criteria_listed`) is only a hint and is labelled as such.
* An education-level mismatch is `unable_to_verify`, never `fail`: the ETL does not say whether `12` means "studying in" or "completed" Class 12.
  Course names and free-text conditions are `unable_to_verify`.

## Configure PostgreSQL Later

Everything below is for **when you are ready**. Nothing in this repository creates a database for you, and the placeholders are not real credentials.

**1. Create the database and a user** (PostgreSQL 18 is installed as a Windows service; `psql` is not on `PATH`). You will be asked for the
`postgres` superuser password you chose when installing PostgreSQL:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres
```

Inside `psql` (replace the placeholder; avoid `@ : / ? # %` in the password, or URL-encode it):

```sql
CREATE ROLE scholarpath_app LOGIN PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';
CREATE DATABASE scholarpath OWNER scholarpath_app;
\q
```

**2. Configure `DATABASE_URL`** in `.env` (Git-ignored; created from the template if you have not yet):

```powershell
cd D:\major\scholarpath-backend
if (-not (Test-Path .env)) { copy .env.example .env }
notepad .env
```

```
DATABASE_URL=postgresql+psycopg://scholarpath_app:REPLACE_WITH_A_STRONG_PASSWORD@localhost:5432/scholarpath
```

**3. Test the connection** (read-only; prints which step fails, never your credentials):

```powershell
python -m app.scripts.check_database
```

`[1/3]` URL set, `[2/3]` connection works, `[3/3]` migrations applied. Steps 1-2 passing and step 3 saying "NOT APPLIED" is expected before step 4.
Once the API is running, `GET /health/db` must also say `{"status":"ok"}`.

**4. Run the migrations** (preview first if you like - this needs no database):

```powershell
alembic upgrade head --sql      # print the SQL only
alembic upgrade head            # create the tables
alembic current                 # should show 0001_initial_schema (head)
python -m app.scripts.check_database   # now all three steps should be OK
```

**5. Import the reconciled scholarship data.** The authoritative input is the ETL's cleaned output (derived from `scholarship 1.xlsx`; the JSON and
CSV are identical, see `docs/data-reconciliation.md`). Always dry-run first - it validates the file and needs no database:

```powershell
$DATA = "D:\major\scholarpath-data\data\processed\scholarships_cleaned.json"
python -m app.scripts.import_scholarships --input $DATA --dry-run
python -m app.scripts.import_scholarships --input $DATA
```

Safe to repeat: records are matched by their stable ETL `scholarship_id`; unchanged records are left alone; the whole run is one transaction
(on any database error nothing is imported). Options: `--include-errors` (also import records the ETL flagged with validation errors; default skips them),
`--report-json PATH`. Exit codes: `0` ok, `3` imported but some records failed validation, `2` bad input/configuration, `1` database error.
The report lists read / valid / inserted / updated / unchanged / skipped / failed, and how many database records are absent from the file (never deleted).
The input file is only read.

**6. Start the backend and verify the imported records:**

```powershell
uvicorn app.main:app --reload --port 8001
```

In a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health/db
(Invoke-RestMethod "http://127.0.0.1:8001/api/v1/scholarships?page_size=3").total        # expect 34
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/scholarships?state=Madhya%20Pradesh&page_size=3"
Invoke-RestMethod "http://127.0.0.1:8001/api/v1/scholarships/SP-E7F4708E55"               # an id from the ETL output
$body = '{"profile":{"state":"Madhya Pradesh","education_level":"Class 12","percentage":72,"family_income":300000,"category":"OBC"},"scholarship_ids":["SP-E7F4708E55"]}'
Invoke-RestMethod http://127.0.0.1:8001/api/v1/eligibility/check -Method Post -ContentType 'application/json' -Body $body
```

Every record should show `"verification_status": "pending"`, and the eligibility outcome should be `cant_tell_yet` (the rules are unreviewed).
Swagger at `/docs` lets you try the same calls in the browser.

Troubleshooting: `503 database_not_configured` -> step 2; `database_unavailable` -> PostgreSQL stopped or wrong URL/password (step 3);
`database_not_migrated` -> step 4.

## Tests

```powershell
python -m pytest
```

No test needs PostgreSQL, a network connection, or your `.env`. Each test runs in an empty temp directory with the relevant environment
variables removed. Coverage: configuration and secret handling; health/CORS/Swagger; model constraints; **migration vs model parity** (offline PostgreSQL
SQL); importer input validation, mapping of all 35 ETL columns, transactional upserts, idempotent reruns, rollback, reviewed-criteria preservation;
repository filters/search/sort/pagination; eligibility matrix; API validation and structured error responses; command-line behaviour.

## Layout

```
app/
  main.py                 app factory, CORS, exception -> structured 503/404 handlers
  core/                   config (Settings), errors, url_check
  db/                     Base (naming convention), lazy engine (no connection on import)
  models/scholarship.py   Scholarship, ScholarshipValue, ScholarshipCriterion, ImportRun
  domain.py               database-agnostic dataclasses (views, query, options)
  schemas/                Pydantic request/response models
  repositories/           ScholarshipRepository protocol + SQL implementation
  services/               scholarships, eligibility (pure engine), eligibility_service, vocabulary, importer/
  api/                    deps, router, routes (health, scholarships, eligibility)
  scripts/                import_scholarships, check_database
alembic/                  env.py + versions/0001_initial_schema.py
tests/  docs/
```

Data model: `scholarships` mirrors the 35 ETL columns (nulls stay null); `scholarship_values` holds filterable multi-valued attributes (state, category,
education level, course, gender; `ALL` = explicit "all"); `scholarship_criteria` holds individual criteria with `is_mandatory`, `review_status`,
`evidence_text/url`, `source_ref`, `origin` (`etl` rows are replaced on re-import, `reviewer` rows never; review state carries over when a rule is unchanged);
`import_runs` audits every import. A database CHECK refuses a `verified` row without `last_verified_at`. Nothing is ever marked verified automatically.
