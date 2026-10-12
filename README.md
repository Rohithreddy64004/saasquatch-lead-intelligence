# SaaSquatch Lead Intelligence

## Project Overview

SaaSquatch Lead Intelligence is a portfolio concept for a B2B sourcing team deciding which companies to contact first. It combines explainable company-fit scoring, data-quality gaps, saved leads, and grounded outreach drafts in one workspace.

This is an independent interview-assignment concept. It is not an official SaaSquatch product, integration, or deployment.

## Key Features

- Database-backed overview metrics, priority distribution, recent leads, and top-scoring companies.
- Search, sorting, pagination, and filters for industry, location, revenue, priority, and minimum score.
- Lead detail drawer with score breakdown, reasons, missing fields, completeness, and next action.
- Saved leads and selected or filtered CSV export.
- CSV preview/import with supported header aliases, Pydantic validation, per-row errors, and duplicate reporting.
- CSV export protects text cells from spreadsheet formula injection.
- Company-specific subject, editable email body, and LinkedIn note generated from the selected lead's recorded fields. The API also returns the personalization points and data limitations used. Groq runs in the backend; when unavailable, malformed, or ungrounded, a labeled deterministic company-aware template is returned.

## Scoring Methodology

The deterministic scorer in `backend/app/scoring/engine.py` sums five categories to 100 points. Score and category values are stored on each MongoDB lead document and recalculated by the score endpoint.

| Category | Weight | Implemented rule |
| --- | ---: | --- |
| Company/industry fit | 25 | Exact configured target industry earns full weight; adjacent software/SaaS/technology earns 60%; another known industry earns 32%; missing industry earns 0. |
| Revenue fit | 20 | Revenue inside the configured range earns full weight; within half the minimum to twice the maximum earns 60%; other known revenue earns 25%; missing revenue earns 0. |
| Decision-maker relevance | 20 | CEO/founder/owner/president/managing director earns full weight; executive or department-lead title earns 75%; another known title earns 40%; missing title earns 0. |
| Growth signals | 20 | A signal with an explicit source earns full weight. Missing or unsourced signals earn 0. Synthetic demo signals are explicitly labeled synthetic. |
| Data completeness | 15 | Nine company/contact fields contribute proportionally. Missing fields do not receive credit. |

Priority is High at 80-100, Medium at 60-79, and Low at 0-59. The target industries and revenue boundaries are configurable using `TARGET_INDUSTRIES`, `TARGET_REVENUE_MIN`, and `TARGET_REVENUE_MAX`.

**Demo-data caveat:** the synthetic seed includes a source label for its synthetic growth examples, so those rows can receive growth-signal points under the stated rule. Those points are illustrative only; they are not evidence of real company growth.

## Tech Stack and Architecture

- Frontend: React 19, TypeScript, Vite, Tailwind CSS 4, Lucide React, Recharts, and Papa Parse.
- Backend: Python 3.11+, FastAPI, Pydantic 2, and PyMongo's asynchronous API.
- Database: MongoDB Atlas, using a `leads` collection, Pydantic document validation, stored score fields, and indexes for normalized identity, location, industry, priority, score, saved state, and creation time.
- Dashboard: MongoDB `$facet` aggregation calculates counts, score averages, completeness, priority distribution, and ranked/recent records.
- Outreach: optional Groq structured JSON validated by Pydantic. Each request uses the selected lead's facts; responses are not cached, preventing stale cross-lead drafts. Provider errors or unsupported claims fall back to a deterministic template and sanitized diagnostics.

## Demo Data and Limitations

On an empty `leads` collection, startup seeds 48 fictional companies and contacts. The contacts use reserved `.invalid` email addresses that cannot receive mail. Demo growth signals are labeled synthetic and are not researched or verified. Imported and manually created records are not represented as verified research.

This demo has no authentication, authorization, tenant isolation, CRM/email integration, email verification, revenue verification, or live company-research feed. Generated outreach should be reviewed before use. The earlier SQLite file, if present under `backend/data/`, is not migrated automatically and is left untouched.

## Project Structure

```text
.
|-- backend/
|   |-- .env.example
|   |-- Dockerfile
|   |-- .dockerignore
|   |-- requirements.txt
|   |-- app/
|   |   |-- api/routes.py
|   |   |-- database.py
|   |   |-- main.py
|   |   |-- models.py
|   |   |-- schemas.py
|   |   |-- seed.py
|   |   |-- scoring/engine.py
|   |   `-- services/
|   |       |-- leads.py
|   |       `-- outreach.py
|   `-- tests/
|       |-- conftest.py
|       |-- test_api.py
|       |-- test_mongo_documents.py
|       |-- test_outreach.py
|       `-- test_scoring.py
|-- frontend/
|   |-- .env.example
|   |-- Dockerfile
|   |-- .dockerignore
|   |-- nginx.conf
|   |-- public/
|   |   |-- favicon.svg
|   |   `-- icons.svg
|   |-- src/
|   |   |-- App.tsx
|   |   |-- App.css
|   |   |-- index.css
|   |   |-- main.tsx
|   |   `-- assets/
|   |       |-- hero.png
|   |       |-- react.svg
|   |       `-- vite.svg
|   |-- package.json
|   |-- package-lock.json
|   |-- vercel.json
|   `-- vite.config.ts
|-- .gitignore
|-- .dockerignore
|-- docker-compose.yml
|-- QA_REPORT.md
|-- README.md
`-- render.yaml
```

Generated content such as `node_modules/`, `frontend/dist/`, Python virtual environments, caches, and local data are excluded from this outline.

## Prerequisites

- Python 3.11 or newer and Node.js 20.19+ or 22.12+.
- Windows PowerShell 5.1 or PowerShell 7.
- Docker Desktop with Docker Compose v2, with the Linux container engine running (Docker use only).
- A MongoDB Atlas cluster, database user, and Network Access rule for the development machine.
- Optional Groq API key for provider-generated drafts.

## MongoDB Atlas Setup

Create an Atlas project/cluster and least-privilege database user, allow the current development IP in Atlas Network Access, and copy the Atlas connection string. URL-encode special characters in the username/password. The app reads `backend/.env` directly without overriding environment variables already set by the process.

If a local backend env file is absent, copy the placeholder template. Never replace an existing local `.env` automatically:

```powershell
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Edit `backend\.env` locally with your own values. The example template contains placeholders only.

## Environment Variables

| Variable | Required | Purpose/default |
| --- | --- | --- |
| `MONGODB_URI` | Yes | Atlas connection URI; keep only in backend environment configuration. |
| `MONGODB_DATABASE` | Yes | Database name selected for the `leads` collection. |
| `FRONTEND_ORIGINS` | No | Comma-separated CORS origins; defaults to localhost ports 5173. |
| `GROQ_API_KEY` | No | Provider credential; blank means deterministic template outreach. |
| `GROQ_MODEL` | No | Model ID; default `openai/gpt-oss-20b`. |
| `TARGET_INDUSTRIES` | No | Comma-separated target industries; default `SaaS,Software,IT Services`. |
| `TARGET_REVENUE_MIN` | No | Revenue lower bound; default `1000000`. |
| `TARGET_REVENUE_MAX` | No | Revenue upper bound; default `50000000`. |
| `VITE_API_URL` | No | Optional public frontend API base URL. Leave empty for same-origin `/api` requests through the Vite development proxy or Docker Nginx proxy. |

The backend pings MongoDB during startup, creates indexes, and fails startup if the database is unavailable. It seeds the 48 synthetic rows only when the collection is empty; startup does not clear or overwrite records. MongoDB and Groq credentials belong only in `backend/.env` or another backend runtime environment, never in frontend variables or image build arguments.

## Docker Compose (Windows PowerShell)

Start Docker Desktop and wait for its Linux engine to become available. Prepare `backend/.env` without replacing an existing local file:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Edit `backend\.env` and set `MONGODB_URI` and `MONGODB_DATABASE` for a MongoDB Atlas database. `GROQ_API_KEY` is optional; without it, the existing deterministic outreach fallback is used. Use a dedicated nonproduction Atlas database for runtime verification: the application may insert its 48 demo records if that database's `leads` collection is empty.

Build and start the services:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

The frontend is served at `http://localhost:5173`. It sends `/api` requests through Nginx to the backend over the private Compose network, so browser requests do not use the Docker-only backend hostname. The backend is also published at `http://localhost:8000`; its API docs are at `http://localhost:8000/docs`.

Check frontend availability and backend connectivity:

```powershell
Invoke-WebRequest http://localhost:5173/
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:5173/api/health
docker compose logs --tail 100
```

The health endpoint pings Atlas. Compose waits for the backend health check before starting the frontend. Stop the services with:

```powershell
docker compose down
```

No MongoDB container or volume is created; Atlas remains the configured database.

### Docker troubleshooting

- If Docker reports that it cannot connect to the engine, start or restart Docker Desktop and check `docker info` before building.
- If the backend exits or remains unhealthy, verify the Atlas URI/database name, Atlas Network Access allowlist, and database-user permissions in `backend/.env`; inspect `docker compose logs backend` for sanitized diagnostics.
- If a port is already in use, stop the conflicting process or change the host-side port before the container port in `docker-compose.yml` (frontend container port 80, backend container port 8000).
- If Groq is unavailable or no key is configured, outreach continues through the existing deterministic fallback.

## Run Locally (Windows PowerShell)

From the workspace root, prepare the backend without recreating an existing virtual environment or local `.env`:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence
if (-not (Test-Path backend\.venv\Scripts\python.exe)) { python -m venv backend\.venv }
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Set the Atlas values in `backend\.env` before launching. In **terminal 1**:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

In **terminal 2**, install dependencies and start Vite:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence\frontend
npm install
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

Open the URL Vite prints, normally `http://localhost:5173`. The Vite development proxy forwards `/api` to `http://127.0.0.1:8000`; the API docs are at `http://localhost:8000/docs`. If using a different API host, set the public `VITE_API_URL` in `frontend/.env.local` and restart Vite.

## API Documentation

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Pings MongoDB; returns 503 when unavailable. |
| GET | `/api/dashboard` | Aggregated metrics and rankings. |
| GET | `/api/leads` | Search, filter, sort, and paginate; includes `saved_only=true`. |
| GET | `/api/leads/{lead_id}` | Lead details and score explanation. |
| POST | `/api/leads` | Pydantic-validated create; duplicates return 409. |
| POST | `/api/leads/import` | Multipart CSV import and accepted/rejected/duplicate counts. |
| POST | `/api/leads/{lead_id}/score` | Recalculate and store score fields. |
| POST | `/api/leads/{lead_id}/outreach` | Groq or deterministic template draft. |
| POST | `/api/leads/{lead_id}/save` | Set `{ "saved": true }` or false. |
| GET | `/api/leads/export` | Filtered CSV or comma-separated `selected_ids` ObjectIds. |

Interactive Swagger documentation is served by FastAPI at `/docs` while the local backend is running.

## Testing and QA

Backend tests use an isolated in-memory asynchronous Mongo fake; they do not connect to Atlas or use configured database credentials. From the workspace root:

```powershell
cd C:\Users\rohit\saasquatch-lead-intelligence\backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
npm run lint
```

**Outreach QA rerun (2026-10-10):** pytest reported 28 passed, 0 failed; the frontend production build succeeded. Oxlint completed with two non-fatal `react(set-state-in-effect)` warnings. Vite printed a bundle-size advisory for the approximately 634 kB minified JavaScript bundle. Pytest printed one Starlette/httpx TestClient deprecation warning.

**Dockerization checks (2026-10-12):** all 28 backend tests passed and the frontend production build succeeded. `docker compose config --quiet` passed. Docker image builds and container runtime checks were not run because the Docker Desktop engine was unavailable; the frontend build still reports the bundle-size advisory above.

**Previously recorded live QA:** [QA_REPORT.md](QA_REPORT.md) records the Atlas ping/index/write-read-cleanup probe, 19/19 live API smoke checks, browser checks, and the Groq model correction. Those live checks were recorded during the earlier QA run and were not all repeated during this README-only review. The report distinguishes the app's live Atlas checks from mocked pytest checks.

## 1-2 Minute Demo Walkthrough

1. Open the dashboard and point out that the four metrics and priority chart are populated from the API/database.
2. Open **Leads**, search a company, apply an industry/location/revenue/priority/score filter, and select a row.
3. In the detail drawer, explain the five weighted categories, reasons, missing fields, and suggested next action. Note that unknown/unsourced evidence earns no positive signal credit.
4. Save a lead, visit **Saved Leads**, and demonstrate filtered or selected CSV export.
5. Open **Import Data**, choose a CSV to preview, and show how duplicates/rejected rows are reported.
6. Generate outreach. Review the company/contact facts used and limitations, then edit the subject or email before copying. Regenerate to request a fresh draft for the currently selected company. Groq output is labeled Groq-assisted; failures or unsupported claims use the labeled template fallback.

## Design Decisions and Trade-offs

- Scores are deterministic and separate from the LLM so users can inspect and test each category. The trade-off is that rules are intentionally simple and do not replace analyst judgment.
- Unknown industry, revenue, title, or growth evidence does not receive full credit. Growth gets points only when a signal and source are both present; synthetic seed sources remain clearly synthetic.
- The app stores score breakdowns and normalized identity keys on Pydantic-validated documents so filters and indexes can use them. Scores are recalculated through the score endpoint.
- Groq is optional and never exposed to the frontend. Provider output is checked for company/industry anchors and obvious unsupported claims; invalid output uses a deterministic fallback. Drafts are not cached, so switching leads cannot reuse a previous response.
- Duplicate checks use normalized domain and normalized company name/location fallback, backed by unique indexes. CSV export escapes formula-leading text.

## Security and Repository Hygiene

- Keep populated `.env` files out of version control and never put Atlas/Groq credentials in frontend variables. `backend/.env.example` and `frontend/.env.example` are placeholder/default templates.
- `.gitignore` excludes `.env`, `.env.*`, virtual environments, Python caches, `node_modules`, build output, local data, logs, and SQLite files. `.dockerignore` files apply the corresponding secret and generated-file exclusions to Docker build contexts.
- The backend CORS allowlist is configured by `FRONTEND_ORIGINS`; configure the exact deployed frontend origin for deployment.
- Sample emails use `.invalid`. Synthetic companies/contacts and growth signals are not real research.
- This workspace had no Git metadata or remote when Docker work began, so a fresh local repository was initialized after the file and secret review. No commit or remote is configured; inspect the staged file list before committing. Nothing is pushed by this setup.

## Known Limitations

- Authentication, authorization, role management, audit history, and tenant isolation are not implemented. Do not use real customer/contact data without adding these controls.
- No external research, CRM integration, verified financial data, email verification, or real-time growth data is included.

## Future Improvements

- Add authenticated roles and tenant isolation before supporting multiple customer workspaces.
- Add migration/backfill tooling for existing records and configurable scoring rules in the UI.
- Expand integration coverage against disposable Atlas clusters and add observability for database/provider health.

## Deployment Status

Deployment has not been performed or verified. `frontend/vercel.json` and `render.yaml` provide starting configuration only; follow the Atlas/network/CORS/secrets guidance in this document and [QA_REPORT.md](QA_REPORT.md). Atlas is external managed storage, not Render's ephemeral filesystem.
