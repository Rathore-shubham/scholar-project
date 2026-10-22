# ScholarPath Next.js

The ScholarPath AI student web app: the Lovable-generated UI from `..\scholarpath-frontend` migrated to
**Next.js (App Router), JavaScript only, Tailwind CSS v4 and Lucide React**, and connected to the FastAPI backend in
`..\scholarpath-backend`. The original frontend is untouched and remains the fallback.

All scholarship data comes from the API. This app contains **no scholarship records, no mock results and no
fallback data**: if the backend or its database is unavailable, you see an explanation and a retry button instead.

## Requirements

Node.js 20.9+ (developed on Node 24, npm 11) and the backend running (see its README).

## Setup and run

```powershell
cd D:\major\scholarpath-nextjs
npm install
copy .env.example .env.local        # already present on this machine; sets NEXT_PUBLIC_API_URL
npm run dev                         # http://localhost:3000   (also http://127.0.0.1:3000)
```

Run the backend in a **separate terminal** (port 8001; see `..\scholarpath-backend\README.md`):

```powershell
cd D:\major\scholarpath-backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8001
```

| Command | What it does |
|---|---|
| `npm run dev` | Development server on port 3000 |
| `npm run build` | Production build (verified: succeeds, 8 routes) |
| `npm run start` | Serve the production build on port 3000 |
| `npm test` | Vitest + Testing Library (84 tests, no network, no backend needed) |

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8001` | Base URL of the FastAPI backend. It is baked into the build, so change it and rebuild/restart. |

Only `NEXT_PUBLIC_*` variables reach the browser. **Database credentials exist only in the backend's own `.env`** and never in this
project. The backend's CORS must allow this app's origin: it allows `http://localhost:3000` and `http://127.0.0.1:3000` by default
(`CORS_ORIGINS` in the backend `.env`).

## Routes (App Router)

| URL | File | Original TanStack route |
|---|---|---|
| `/` | `app/page.js` -> Dashboard | `/` |
| `/scholarships` (`?q=`) | `app/scholarships/page.js` -> Discovery | `/scholarships` |
| `/scholarships/[id]` | `app/scholarships/[id]/page.js` -> Details | `/scholarships/$id` |
| `/eligibility` | `app/eligibility/page.js` -> Eligibility Checker | `/eligibility` |
| `/saved` | `app/saved/page.js` | `/saved` |
| `/applications` | `app/applications/page.js` | `/applications` |
| `/profile` | `app/profile/page.js` | `/profile` |

Plus `app/not-found.js` (404) and `app/error.js` (route error boundary). `app/layout.js` loads the same Google fonts as the original and wraps
every page in the providers and the application shell (sidebar, header, notifications, help, account dialogs).

## API calls

All HTTP goes through `lib/api.js` (one reusable client) and the hooks in `lib/use-api.js`:

| Screen | Endpoint |
|---|---|
| Discovery: results, search, filters, sort, "Load more" | `GET /api/v1/scholarships` (server-side filtering, paging, sorting) |
| Filter dropdown values, dashboard counts | `GET /api/v1/meta/filters` |
| Details | `GET /api/v1/scholarships/{id}` |
| Eligibility badges on cards, details panel, checker | `POST /api/v1/eligibility/check` (batched, up to 50 ids per request) |
| Saved / Applications | `GET /api/v1/scholarships?ids=...` |

Every screen has loading skeletons, an empty state, and an error state with a retry. Errors use the backend's structured codes:
`database_not_configured`, `database_unavailable`, `database_not_migrated` each get a specific, non-technical explanation; a stopped backend is reported as
"Can't reach the ScholarPath API". Eligibility results (outcome, summary, per-criterion required value / your value / status / explanation / source,
limitations, missing information) are displayed exactly as the API returns them; the UI never computes eligibility itself.

## What changed in the migration

Preserved from the original: the design (the stylesheet is the original `styles.css`, copied verbatim; only Tailwind's `@source` paths changed, plus one clearly
marked block appended for the new loading/error states), layouts, sidebar/header/dialogs, dashboard, discovery, details, checker, saved, applications and profile
pages, form validation (Zod), Lucide icons, and the shadcn `Button` / `Dialog` (converted to JavaScript).

Adapted because the data is now real:

* **Fabricated scholarships and eligibility rules removed.** The original's 8 "illustrative" records and its client-side eligibility engine are gone; nothing from them
  reaches any view. The demo student ("Rahul Sharma") and the pre-saved scholarships/applications are gone too: the profile starts empty. Browser storage moved to a new
  versioned key, so the prototype's mock ids are never read.
* **Verification is always visible.** Pending records show an "Unverified" badge, an explanatory notice, and "Can't Tell Yet". The API only returns "Eligible" / "Not Eligible"
  for verified scholarships with reviewed, evidence-backed rules; today every record is unverified, so every result is "Can't Tell Yet" with the full criterion breakdown.
* **Unavailable data is shown as unavailable.** The current data has no application deadlines, procedures or dates, and amounts are mostly text; those fields say
  "Not available" (the deadline sort, "Recently Verified" sort and "Upcoming Deadlines" panel explain why they have nothing to show). Funding shows the source's own wording.
* **Filters follow the real data.** "Scholarship Provider" (Government/NGO/CSR) became **Scheme Level** (Central/State); "Application Status" (Open/Closed) became
  **Verification**; Category was added; education levels now include Classes 8, 9, 11 and Diploma, and the state list covers all states and UTs. The profile preference
  "Preferred provider" became "Preferred scheme level" and is used by the dashboard.
* **Router and build:** TanStack Router -> App Router (`Link`, `usePathname`, server pages with metadata); Tailwind's Vite plugin -> `@tailwindcss/postcss`; TypeScript removed.
  Lovable-specific files (error reporting, server wrapper, route tree, Vite/TanStack config) and the 44 unused shadcn components were not migrated.

## Testing

```powershell
npm test
```

84 tests, with `fetch` mocked: the API client (URL building, error mapping, timeouts, batching), formatting, every page's loading / success / empty / error / retry
behaviour, filter-to-parameter mapping, "Load more", the eligibility checker and result display (including verified `eligible` / `not_eligible` outcomes), the details page
(unavailable fields, external-link confirmation, save/track), and the browser store (validation, corrupt storage, no seeded data).

## Known limitations

* Profile, saved scholarships and application statuses live only in this browser (no accounts yet), so they do not sync across devices.
* The eligibility checker lists the first 50 scholarships alphabetically; there is no scholarship search box there yet.
* Application deadlines, notifications about deadlines and "recently verified" ordering have no data until a source provides them / records are verified.
* `npm run dev` serves `localhost` and `127.0.0.1` only (`allowedDevOrigins`); add other hosts there if you browse from another device.

## Troubleshooting

| You see | Meaning / fix |
|---|---|
| "Can't reach the ScholarPath API" | The backend is not running at `NEXT_PUBLIC_API_URL`. Start it (port 8001) or fix the URL, then rebuild/restart. |
| "The scholarship database is not set up yet" | Backend is up, PostgreSQL is not configured. Follow the backend README, section **Configure PostgreSQL Later**. |
| "The database has no tables yet" | Run `alembic upgrade head` in the backend, then import the data. |
| "No scholarships on record yet" | Database connected but empty: run the importer (backend README, step 5). |
| Browser console CORS error | Add this app's origin to `CORS_ORIGINS` in the backend `.env` and restart the backend. |
