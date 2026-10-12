# QA Report: SaaSquatch Lead Intelligence

**Date:** 2026-10-10  
**Workspace:** `C:\Users\rohit\saasquatch-lead-intelligence`

## Summary

Real MongoDB Atlas connectivity was verified using the configured local backend environment. The Atlas ping succeeded, the configured database was selected, all 11 required indexes were present, and the `leads` collection contained 48 records. A uniquely marked temporary QA lead was written/read and then removed by its exact ObjectId; existing records were not edited or deleted.

The original application failure was not an Atlas connection failure. The live dashboard endpoint returned HTTP 500 because the async PyMongo `aggregate()` coroutine was not awaited before calling `.to_list()`. The await order is fixed, and the live dashboard now responds successfully.

## Results

| Check | Result |
| --- | --- |
| `backend/.env` exists and settings load | Pass; values were not printed or included in this report. |
| Atlas connection and `ping` | Pass against the configured cluster. |
| Selected database | Pass; the collection's database matched the configured database name. The name is intentionally not repeated here. |
| Required indexes | Pass; all 10 application indexes were present, plus MongoDB's automatic `_id` index (11 total). |
| Existing data | Pass; 48 leads were readable before and after QA probes. |
| Temporary Mongo write/read/cleanup | Pass; only test-created records were removed by exact IDs and QA markers. |
| FastAPI health | Pass; live `/api/health` returned `200` and `ok`. |
| Dashboard aggregation | Pass after fix; live `/api/dashboard` returned 48 total, 29 high priority, 82.9 average score, and 88% complete contacts. |
| Listing, search, pagination, detail | Pass against Atlas. |
| Industry, location, revenue, priority, minimum-score filters | Pass; combined live filter returned 29 matching records and each result met all criteria. |
| Saved leads | Pass; live saved listing contained only records marked saved. QA exercised save/filter on its temporary lead. |
| Score and missing-data handling | Pass; real API scoring returned category values summing to the total. Unit tests cover missing information and score categories. |
| CSV import/duplicate/malformed rows | Pass; live import accepted one temporary row and counted its duplicate; malformed headers and bad rows were handled. Temporary imported rows were removed. |
| CSV export/formula injection | Pass; selected live export returned CSV; pytest verifies formula-leading text is escaped. |
| CORS | Pass; preflight succeeded for both `http://localhost:5173` and `http://127.0.0.1:5173`. |
| Groq outreach | Pass after changing the unavailable model; a live FastAPI outreach call returned `generated_by=groq` with all required fields. The test lead was synthetic and removed afterward. |
| Missing-key fallback and diagnostic redaction | Pass in pytest; fallback is labeled `template_generated`, and test sentinels for API keys/URIs/database names do not appear in logs. |
| Frontend production build | Pass. A custom `VITE_API_URL` was embedded in a separate build, then the normal build was restored and passed. |
| Frontend browser workflow | Pass; live dashboard, search, lead details, saved leads, import page, export response/toast, and Groq draft UI were exercised. |
| Browser console/page errors | None in the final browser run. |
| Responsive layout | Pass at 390px and 1440px; document width matched the viewport's layout width with no horizontal overflow. |
| Workspace diagnostics | No editor errors. |
| Backend dependencies/syntax | `pip check` passed; `compileall` passed. |

### Test totals

- Backend pytest after company-specific outreach changes: **28 passed, 0 failed**.
- Live Atlas/API smoke: **19/19 checks passed**, with additional live numeric-filter, Groq, browser, and export checks also passing.
- One non-failing Starlette/httpx deprecation warning was emitted by the FastAPI test client.

## Bugs Fixed

1. **Dashboard 500:** the captured exception was `AttributeError: 'coroutine' object has no attribute 'to_list'` (with an un-awaited coroutine warning). PyMongo's async `collection.aggregate()` must be awaited to obtain its cursor. `dashboard_data()` now awaits `aggregate()` first, then awaits `cursor.to_list()`. Health/listing and the real dashboard are verified afterward.
2. **Groq model unavailable:** the configured `llama-3.3-70b-versatile` produced provider `NotFoundError` with code `model_not_found`. The account's model catalog listed `openai/gpt-oss-20b`; that model was tested successfully with structured outreach and is now configured in `backend/.env`, `.env.example`, and the service default.
3. **Connection diagnostics:** `connect_database()` now logs stage, exception type, and a sanitized error detail without logging the URI, userinfo, database name, environment values, or traceback. Failure tests confirm sentinel values are redacted, and failed startup still fails rather than reporting health.
4. **Setup safety:** restored the missing credential-free `backend/.env.example`; README setup copies it only when `backend/.env` is absent, preventing existing credentials from being overwritten.

## Commands Run

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest -q
uvicorn app.main:app --reload
```

From `frontend/`:

```powershell
npm run build
npm run lint
```

Additional verified operations included a real async Atlas ping/index/read/write probe, Atlas-backed TestClient API checks with `seed_data=False`, a temporary live Groq request, CORS preflights for both local origins, a custom-`VITE_API_URL` build check, and browser interaction checks. Probe code did not print connection strings or credentials.

## Security and Data Safety

- The actual `backend/.env` was not printed. `backend/.env.example` contains placeholders only. `.gitignore` includes `.env`, `.env.*`, virtual environments, build output, `backend/data/`, and local database file extensions.
- No Mongo settings or credential patterns were found in frontend source or build output. Source scan matches were limited to the deliberate URI-sanitizing code and test-only sentinel fixtures.
- This workspace has no `.git` metadata, so Git's tracked-file list and `git check-ignore` could not be verified. Ignore rules were inspected directly; tracked status cannot be asserted.
- An old ignored local file `backend/data/leads.db` remains from the earlier SQLite version. It was not opened, migrated, or deleted.
- Demo contacts are fictional and use `.invalid` addresses. Live QA records used fictional names/domains and were removed after testing.
- No deployment was performed.

## Remaining Warnings

- `npm run lint` reports two non-fatal `react(set-state-in-effect)` warnings in the dashboard fetch effects.
- Vite reports the minified JavaScript bundle is larger than 500 kB (current output approximately 633 kB). Build succeeds.
- Pytest reports the Starlette/httpx TestClient deprecation warning noted above.

## Windows PowerShell Run Commands

From the workspace root, install backend dependencies and preserve an existing `.env`:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Set `MONGODB_URI` and `MONGODB_DATABASE` in `backend\.env` locally. Do not paste credentials into source or frontend files. Start each service in its own PowerShell terminal:

```powershell
# Backend terminal
cd C:\Users\rohit\saasquatch-lead-intelligence\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

```powershell
# Frontend terminal
cd C:\Users\rohit\saasquatch-lead-intelligence\frontend
npm install
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

The live API docs are at `http://localhost:8000/docs`; Vite normally serves `http://localhost:5173`.