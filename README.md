# Theater Showtimes Backend Assessment

This repository contains a frontend-only Next.js application with static JSON data. The backend logic has been intentionally removed so candidates can implement it as part of the assessment. The UI is wired to mock data and stubbed actions to illustrate the expected behaviors.

## Quick Start

1. Install dependencies

```bash
npm install
```

2. Create a `.env` file

```bash
cp .env.example .env
```

3. Add your database connection string

- `DATABASE_URL`

4. Run the dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Running the Full Stack Locally

Requires Docker, the Supabase CLI, Python 3.11+ and Node.

```bash
# 1. Database: local Supabase (applies supabase/migrations + supabase/seed.sql)
supabase start          # Postgres on 127.0.0.1:55322, Studio on http://127.0.0.1:55323
supabase db reset       # wipe + re-migrate + re-seed at any time

# 2. API
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # DATABASE_URL -> local Supabase
uvicorn app.main:app --reload --port 8000   # docs at http://localhost:8000/docs

# 3. Frontend (repo root)
npm install && npm run dev                  # http://localhost:3000
```

Local Supabase ports are shifted to 553xx (see `supabase/config.toml`) so they don't collide with other local Supabase projects.

Tests (need local Supabase running; they create and use a separate `theater_test` database):

```bash
cd backend && .venv/bin/pytest -q
```

### Deploying the schema to the remote project

```bash
supabase link --project-ref <project-ref>
supabase db push        # applies supabase/migrations; seed.sql is local-only
```

Then run the API with `DATABASE_URL` pointing at the remote database.

## Backend Design

**Schema** (`supabase/migrations/`): `theaters`, `users` (`role` = admin | user, `can_view_all`), `user_theaters` (join table, since Postgres can't FK an array), `movies`, `showtimes`, plus CSV staging tables `uploads`, `upload_rows`, `upload_archives`.

- `movie_status` (approved / draft / flagged / needs-review) lives on the showtime; only admins can change it.
- A showtime's identity is (theater, `normalize_title(title)`, start_time). `normalize_title` lowercases and collapses punctuation and whitespace, so `"  Spider Man - Homecoming "` matches `Spider‑Man: Homecoming`. A partial unique index enforces at most one non-archived showtime per movie, start time and theater.
- RLS is enabled with no policies, so Supabase's auto-generated REST API can't reach the tables. All access goes through FastAPI.

**Auth stand-in:** there is no login. Clients send `X-User-Id`, and the API loads the role and theater access from the database, so a client can't claim to be an admin. Theater access is independent of role: admins are limited to their theaters unless `can_view_all` is set.

**Endpoints**

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| GET | `/users` | anyone | Backs the mock user picker |
| GET | `/me`, `/theaters` | user | Theaters the caller can access |
| GET | `/movies` | user | Paged showtime search (≤ 50/page). `q`, `status`, `format`, `language`, `rating`, `movie_status` (admin only), `start_date`/`end_date` (in each theater's timezone), `auditorium`/`theater_id` (repeatable), `sort` = title, start_time, end_time, last_updated, theater, movie_status (admin only), `order` = asc/desc. Non-admins only see approved showtimes |
| GET | `/movies/filters` | user | Distinct values for the filter dropdowns |
| PATCH | `/showtimes/{id}` | admin | `{movieStatus?, status?}` |
| POST | `/theaters/{id}/clear-schedule` | admin | Archives every live showtime for the theater |
| POST | `/uploadshowtime` | admin | Multipart `file`, optional `theater_id`. **201**: stages the CSV and returns a summary plus the first 100 of each change type |
| GET | `/uploads/{id}`, `/uploads/{id}/changes?type=` | admin | Re-read the preview and page through the full diff |
| POST | `/uploads/{id}/commit` | admin | Applies the staged upload in one transaction |

**CSV pipeline (built for large files)**

1. Upload streams the file. Rows are cleaned and validated in Python (trimmed whitespace, uppercased codes, ISO-8601 timestamps that must include a timezone, end time after start time) and loaded into `upload_rows` with `COPY`.
2. Reconciliation is set-based SQL. Each row is classified as add / update / unchanged / duplicate / invalid (unknown theater, no access, bad data). Live showtimes that are missing from the drop become archive candidates. Only theaters with at least one valid row are reconciled, so a broken file can't wipe a schedule.
3. Commit locks the affected theaters, re-runs reconciliation against the current schedule, and then applies the result. Missing showtimes are archived **and** set to `needs-review`. Any older staged upload for the same theaters is marked `superseded`, so committing a stale preview can't roll the schedule back.

Benchmark from the test suite: 100k rows stage in about 4s and commit in about 3s on a laptop.

**Phase 2 (not built yet):** fuzzy title and auditorium matching (e.g. `DUNE PART 2` vs `Dune: Part Two` currently shows up as an add plus an archive), keyset pagination and caching for very large result sets, background jobs for very large files, and real authentication.

## What’s in the Frontend

- Users, theaters and showtimes come from the FastAPI backend (`src/lib/api.ts`). Set `NEXT_PUBLIC_API_URL` if the API isn't on `http://localhost:8000`.
- The user picker is a mock session that sets `X-User-Id`.
- Search, filters, sorting and paging run on the server. CSV upload shows the staged diff, and Confirm commits it.

## Backend Requirements (Implement These)

Build the backend for a website to ingest a partner CSV and reconcile it against the current schedule for a single theater that currently has hard coded JSON data.

The backend must support:

- Admin and non-admin views
  - Admin has full read/write access
  - Non-admin has read access to limited data
  - All users belong to some, none, or all theaters
  - Users can only see movies for theaters they belong to
  - Admin can update a movie status field that non-admins cannot update
- A database schema based on the given hardcoded JSON data
- Search at scale (hundreds of thousands of movies) - scaling phase 2 (paging, caching etc)
  - Search by movie name
  - Reasonable filters for other columns
  - Sort by reasonable columns
- CSV data cleaning on upload
  - At most one active showtime per unique movie + start time per theater
  - Minor differences (title spelling, auditorium rename) should update the same showtime - for phase 2
  - Missing showtimes in a new drop should be archived
  - Schedule must be persisted in the database

## Notes

- The frontend currently shows a callout indicating mock behavior. Replace mock logic with real API calls once the backend is implemented.
