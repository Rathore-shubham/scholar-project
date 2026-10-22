# ScholarPath AI

Scholarship discovery and eligibility checker for students in India (final-year B.Tech project).

Students search scholarships, filter them, and check their eligibility. The result comes from fixed rules, not from an AI score.

> **Data status:** the 34 scholarship records are loaded from one Excel file and are all **unverified**. The app says so on every record, and every eligibility result is "Can't Tell Yet" until a person reviews a record against its official source.

## How the folders fit together

```
scholarpath-data/       1. Cleans the Excel file into JSON/CSV   (Python)
        |
        v
scholarpath-backend/    2. API + PostgreSQL database             (Python, FastAPI)
        |
        v
scholarpath-nextjs/     3. The website you open in the browser   (Next.js)

scholarpath-frontend/   Old Lovable prototype with fake data. NOT needed. Ignore it.
```

**Use `scholarpath-nextjs` as the frontend.** `scholarpath-frontend` is the earlier prototype. It is kept only as a fallback.

## What to download

| Tool | Version | Needed for | Download |
|---|---|---|---|
| Git | any | cloning the repo | https://git-scm.com/downloads |
| Python | 3.12 (3.11+ works) | data + backend | https://www.python.org/downloads/ (tick **Add python.exe to PATH**) |
| Node.js | 20.9 or newer (24 used here) | Next.js frontend | https://nodejs.org (LTS) |
| PostgreSQL | 18 used here | database | https://www.postgresql.org/download/ |

Check them in a terminal:

```powershell
git --version
python --version
node -v
npm -v
```

## Quick start (the short version)

Open **two terminals**. Do the database setup first (next section), then:

**Terminal 1: backend**

```powershell
cd scholarpath-backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env            # then put your DB password in .env
alembic upgrade head
python -m app.scripts.import_scholarships --input ..\scholarpath-data\data\processed\scholarships_cleaned.json
uvicorn app.main:app --reload --port 8001
```

**Terminal 2: frontend**

```powershell
cd scholarpath-nextjs
npm install
copy .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. The API docs are at <http://127.0.0.1:8001/docs>.

> The cleaned data file is already in the repo, so you do **not** need to run `scholarpath-data` unless you want to rebuild it from the Excel file.

## Set up PostgreSQL

1. Install PostgreSQL from the link above. Remember the password you give the `postgres` user.
2. Open `psql`. On Windows it is usually not on PATH, so use the full path (change `18` to your version):

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres
   ```

3. Create the database and a user for the app. Choose your own password. Avoid the characters `@ : / ? # %` in it:

   ```sql
   CREATE ROLE scholarpath_app LOGIN PASSWORD 'your_password_here';
   CREATE DATABASE scholarpath OWNER scholarpath_app;
   \q
   ```

4. Put the connection string in `scholarpath-backend\.env` (created by `copy .env.example .env`):

   ```
   DATABASE_URL=postgresql+psycopg://scholarpath_app:your_password_here@localhost:5432/scholarpath
   ```

   `.env` is ignored by Git, so your password is never committed.

5. Check the connection:

   ```powershell
   cd scholarpath-backend
   python -m app.scripts.check_database
   ```

   Three steps are checked: URL set, connection works, tables created. Before `alembic upgrade head`, step 3 is expected to say "NOT APPLIED".

6. Create the tables, then load the data (both are in the quick start above). Import is safe to run again.

7. Check it worked. Open <http://127.0.0.1:8001/health/db>. It should say `{"status":"ok"}`. Then <http://127.0.0.1:8001/api/v1/scholarships?page_size=3> should show `"total": 34`.

## Run each folder

### `scholarpath-nextjs/` (frontend)

```powershell
cd scholarpath-nextjs
npm install                  # first time only
copy .env.example .env.local # first time only
npm run dev                  # http://localhost:3000
```

| Command | What it does |
|---|---|
| `npm run dev` | Development server on port 3000 |
| `npm run build` then `npm run start` | Production build and serve |
| `npm test` | Tests (no backend or network needed) |

`.env.local` holds `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001`, the address of the backend. If you change the backend port, change it here and restart.

The frontend has **no scholarship data of its own**. If the backend is off, you see an error with a Retry button.

### `scholarpath-backend/` (API)

```powershell
cd scholarpath-backend
.venv\Scripts\Activate.ps1                         # every new terminal
uvicorn app.main:app --reload --port 8001          # API on http://127.0.0.1:8001
python -m pytest                                   # tests (no database needed)
```

First-time setup is in the quick start above. It also needs the PostgreSQL steps. More detail is in [scholarpath-backend/README.md](scholarpath-backend/README.md).

### `scholarpath-data/` (data cleaning, optional)

Only needed to rebuild the cleaned data from an Excel file. The Excel file itself is **not** in the repo, so use your own `.xlsx` or `.csv`.

```powershell
cd scholarpath-data
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps

python -m scholarpath_data --input "path\to\scholarship 1.xlsx" --output-dir data
python -m pytest                                   # tests
```

Output goes to `data\processed\scholarships_cleaned.json` and `.csv`. After changing it, re-run the backend import command above. More detail is in [scholarpath-data/README.md](scholarpath-data/README.md).

### `scholarpath-frontend/` (old prototype, skip)

Not part of the running system. Ignore it unless you want to see the original Lovable design.

## Ports

| Part | Port |
|---|---|
| Next.js frontend | 3000 |
| FastAPI backend | 8001 |
| PostgreSQL | 5432 |

## Common problems

| You see | Fix |
|---|---|
| "Can't reach the ScholarPath API" | Backend is not running. Start it on port 8001. |
| "The scholarship database is not set up yet" | `DATABASE_URL` is missing in `scholarpath-backend\.env`. |
| "The database has no tables yet" | Run `alembic upgrade head` in `scholarpath-backend`. |
| "No scholarships on record yet" | Run the import command in `scholarpath-backend`. |
| `database_unavailable` | PostgreSQL is stopped, or the password or URL is wrong. Run `python -m app.scripts.check_database`. |
| Browser CORS error | Add the frontend address to `CORS_ORIGINS` in the backend `.env` and restart the backend. |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call `.venv\Scripts\python.exe` directly. |
| `psql` is not recognised | Use the full path to `psql.exe` shown above. |
| pandas `DLL load failed` (data folder) | A Windows Application Control policy is blocking it. `requirements.txt` already pins a working version. |

## Notes

- Never commit `.env` or `.env.local`. Both are in `.gitignore`.
- Profile, saved scholarships and application statuses are stored in the browser only (no accounts yet).
- Scholarship records are never marked "verified" automatically. See the verification section in [scholarpath-data/README.md](scholarpath-data/README.md).
