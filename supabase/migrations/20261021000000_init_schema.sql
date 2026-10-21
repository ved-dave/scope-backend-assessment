-- Theater showtimes schema.
--
-- All access goes through the FastAPI service using a direct Postgres connection,
-- so RLS is enabled with no policies: this locks the tables away from Supabase's
-- auto-generated PostgREST API (anon/authenticated roles) without affecting the
-- service, which connects as the table owner.

create extension if not exists pg_trgm with schema extensions;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type public.user_role as enum ('admin', 'user');
create type public.showtime_status as enum ('active', 'inactive', 'archived');
create type public.movie_status as enum ('approved', 'draft', 'flagged', 'needs-review');
create type public.upload_status as enum ('staged', 'committed', 'superseded');
create type public.upload_row_action as enum ('add', 'update', 'unchanged', 'duplicate', 'invalid');

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Canonical form used to match movie titles across partner drops:
-- lowercase, any run of non-alphanumerics (punctuation, odd hyphens, extra
-- whitespace) collapsed to a single space, trimmed.
--   'Spider‑Man: Homecoming' / '  Spider Man - Homecoming  ' -> 'spider man homecoming'
create function public.normalize_title(title text)
returns text
language sql
immutable
parallel safe
as $$
  select btrim(regexp_replace(lower(title), '[^[:alnum:]]+', ' ', 'g'));
$$;

create function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Core tables
-- ---------------------------------------------------------------------------

create table public.theaters (
  id uuid primary key default gen_random_uuid(),
  name varchar(255) not null,
  location varchar(255) not null default '',
  timezone varchar(64) not null default 'UTC',
  created_at timestamptz not null default now()
);

-- CSV rows reference theaters by name, so names must be unique (case-insensitive).
create unique index theaters_name_key on public.theaters (lower(name));

create table public.users (
  id uuid primary key default gen_random_uuid(),
  name varchar(255) not null,
  email varchar(320) not null,
  role public.user_role not null default 'user',
  -- Theater access is independent of role: can_view_all grants every theater,
  -- otherwise access comes from user_theaters.
  can_view_all boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index users_email_key on public.users (lower(email));

create table public.user_theaters (
  user_id uuid not null references public.users (id) on delete cascade,
  theater_id uuid not null references public.theaters (id) on delete cascade,
  primary key (user_id, theater_id)
);

create index user_theaters_theater_id_idx on public.user_theaters (theater_id);

create table public.movies (
  id uuid primary key default gen_random_uuid(),
  title varchar(500) not null,
  normalized_title text generated always as (public.normalize_title(title)) stored,
  language varchar(32) not null default '',
  rating varchar(32) not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint movies_normalized_title_key unique (normalized_title)
);

-- Supports substring title search (normalized_title LIKE '%term%') at scale.
create index movies_normalized_title_trgm_idx
  on public.movies using gin (normalized_title extensions.gin_trgm_ops);

create trigger movies_touch_updated_at
  before update on public.movies
  for each row execute function public.touch_updated_at();

create table public.uploads (
  id uuid primary key default gen_random_uuid(),
  uploaded_by uuid references public.users (id) on delete set null,
  filename varchar(500),
  status public.upload_status not null default 'staged',
  -- Theaters with at least one valid row; reconciliation (and archiving) is
  -- scoped to these.
  theater_ids uuid[] not null default '{}',
  summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  committed_at timestamptz
);

create index uploads_status_idx on public.uploads (status, created_at);

create table public.showtimes (
  id uuid primary key default gen_random_uuid(),
  movie_id uuid not null references public.movies (id) on delete restrict,
  theater_id uuid not null references public.theaters (id) on delete cascade,
  auditorium varchar(255) not null default '',
  start_time timestamptz not null,
  end_time timestamptz not null,
  status public.showtime_status not null default 'active',
  movie_status public.movie_status not null default 'draft',
  format varchar(32) not null default '',
  -- Partner-supplied timestamp from the CSV drop.
  last_updated timestamptz not null default now(),
  last_upload_id uuid references public.uploads (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint showtimes_time_order check (end_time >= start_time)
);

-- At most one non-archived showtime per movie + start time per theater.
-- Archived rows are kept as history and may repeat.
create unique index showtimes_live_key
  on public.showtimes (theater_id, movie_id, start_time)
  where status <> 'archived';

create index showtimes_theater_start_idx on public.showtimes (theater_id, start_time);
create index showtimes_movie_id_idx on public.showtimes (movie_id);
create index showtimes_review_idx on public.showtimes (movie_status) where movie_status <> 'approved';

create trigger showtimes_touch_updated_at
  before update on public.showtimes
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- CSV staging
-- ---------------------------------------------------------------------------

-- One row per CSV line, already validated/parsed by the API and loaded via COPY.
-- Classification (add/update/...) is computed set-based in SQL.
create table public.upload_rows (
  upload_id uuid not null references public.uploads (id) on delete cascade,
  row_number integer not null,
  theater_name text not null default '',
  movie_title text not null default '',
  auditorium text not null default '',
  start_time timestamptz,
  end_time timestamptz,
  language text not null default '',
  format text not null default '',
  rating text not null default '',
  last_updated timestamptz,
  error text,
  normalized_title text generated always as (public.normalize_title(movie_title)) stored,
  theater_id uuid references public.theaters (id) on delete cascade,
  action public.upload_row_action,
  matched_showtime_id uuid references public.showtimes (id) on delete set null,
  diffs jsonb not null default '[]'::jsonb,
  primary key (upload_id, row_number)
);

create index upload_rows_match_idx
  on public.upload_rows (upload_id, theater_id, normalized_title, start_time);
create index upload_rows_action_idx on public.upload_rows (upload_id, action, row_number);

-- Live showtimes that a staged upload would archive (present in the schedule,
-- missing from the drop).
create table public.upload_archives (
  upload_id uuid not null references public.uploads (id) on delete cascade,
  showtime_id uuid not null references public.showtimes (id) on delete cascade,
  primary key (upload_id, showtime_id)
);

-- ---------------------------------------------------------------------------
-- Lock down PostgREST access (see header comment)
-- ---------------------------------------------------------------------------

alter table public.theaters enable row level security;
alter table public.users enable row level security;
alter table public.user_theaters enable row level security;
alter table public.movies enable row level security;
alter table public.showtimes enable row level security;
alter table public.uploads enable row level security;
alter table public.upload_rows enable row level security;
alter table public.upload_archives enable row level security;
