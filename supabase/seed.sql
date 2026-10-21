-- Local dev seed, mirrors the original mock data in src/data/assessment-data.ts.
-- Fixed UUIDs so the frontend user picker and tests can reference them.

insert into public.theaters (id, name, location, timezone) values
  ('11111111-0000-4000-8000-000000000001', 'Downtown Cinema 7',   'Seattle, WA',       'America/Los_Angeles'),
  ('11111111-0000-4000-8000-000000000002', 'Riverside Multiplex', 'Portland, OR',      'America/Los_Angeles'),
  ('11111111-0000-4000-8000-000000000003', 'Uptown Arts Theater', 'San Francisco, CA', 'America/Los_Angeles');

insert into public.users (id, name, email, role, can_view_all) values
  ('22222222-0000-4000-8000-000000000001', 'Avery Admin',      'avery.admin@example.com',      'admin', false),
  ('22222222-0000-4000-8000-000000000002', 'Casey Operator',   'casey.operator@example.com',   'admin', true),
  ('22222222-0000-4000-8000-000000000003', 'Riley Viewer',     'riley.viewer@example.com',     'user',  false),
  ('22222222-0000-4000-8000-000000000004', 'Morgan Multi',     'morgan.multi@example.com',     'user',  false),
  ('22222222-0000-4000-8000-000000000005', 'Jordan NoTheater', 'jordan.notheater@example.com', 'user',  false),
  ('22222222-0000-4000-8000-000000000006', 'Sam Everywhere',   'sam.everywhere@example.com',   'user',  true);

insert into public.user_theaters (user_id, theater_id) values
  ('22222222-0000-4000-8000-000000000001', '11111111-0000-4000-8000-000000000001'),
  ('22222222-0000-4000-8000-000000000001', '11111111-0000-4000-8000-000000000002'),
  ('22222222-0000-4000-8000-000000000003', '11111111-0000-4000-8000-000000000001'),
  ('22222222-0000-4000-8000-000000000004', '11111111-0000-4000-8000-000000000001'),
  ('22222222-0000-4000-8000-000000000004', '11111111-0000-4000-8000-000000000003');

insert into public.movies (title, language, rating) values
  ('Spider-Man: Homecoming',      'EN', 'PG-13'),
  ('Inside Out 2',                'EN', 'PG'),
  ('Dune: Part Two',              'EN', 'PG-13'),
  ('Wonka',                       'EN', 'PG'),
  ('Oppenheimer',                 'EN', 'R'),
  ('Kung Fu Panda 4',             'EN', 'PG'),
  ('The Fall Guy',                'EN', 'PG-13'),
  ('Ghostbusters: Frozen Empire', 'EN', 'PG-13'),
  ('Civil War',                   'EN', 'R'),
  ('Past Lives',                  'KO', 'PG-13'),
  ('The Holdovers',               'EN', 'R'),
  ('Perfect Days',                'JA', 'PG'),
  ('Anatomy of a Fall',           'FR', 'R'),
  ('The Boy and the Heron',       'JA', 'PG-13');

insert into public.showtimes
  (theater_id, movie_id, auditorium, start_time, end_time, format, movie_status, status, last_updated)
select s.theater_id::uuid, m.id, s.auditorium, s.start_time::timestamptz, s.end_time::timestamptz,
       s.format, s.movie_status::public.movie_status, s.status::public.showtime_status,
       s.last_updated::timestamptz
from (values
  ('11111111-0000-4000-8000-000000000001', 'Spider-Man: Homecoming',      'Auditorium 1', '2025-03-15T18:00:00Z', '2025-03-15T20:13:00Z', '2D',   'approved',     'active',   '2025-03-10T12:00:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Inside Out 2',                'Auditorium 2', '2025-03-15T17:30:00Z', '2025-03-15T19:20:00Z', '3D',   'approved',     'active',   '2025-03-10T12:00:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Dune: Part Two',              'Auditorium 1', '2025-03-15T20:00:00Z', '2025-03-15T22:46:00Z', 'IMAX', 'needs-review', 'active',   '2025-03-12T15:30:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Dune: Part Two',              'Auditorium 1', '2025-03-15T22:45:00Z', '2025-03-16T01:31:00Z', '2D',   'approved',     'active',   '2025-03-12T15:30:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Wonka',                       'Auditorium 3', '2025-03-15T16:00:00Z', '2025-03-15T17:56:00Z', '2D',   'flagged',      'archived', '2025-03-01T09:00:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Oppenheimer',                 'Auditorium 4', '2025-03-15T21:00:00Z', '2025-03-16T00:00:00Z', 'IMAX', 'approved',     'archived', '2025-03-01T09:00:00Z'),
  ('11111111-0000-4000-8000-000000000001', 'Kung Fu Panda 4',             'Auditorium 3', '2025-03-16T17:30:00Z', '2025-03-16T19:05:00Z', '2D',   'draft',        'active',   '2025-03-14T11:00:00Z'),
  ('11111111-0000-4000-8000-000000000002', 'The Fall Guy',                'Auditorium A', '2025-03-15T19:15:00Z', '2025-03-15T21:21:00Z', '2D',   'approved',     'active',   '2025-03-11T10:20:00Z'),
  ('11111111-0000-4000-8000-000000000002', 'Ghostbusters: Frozen Empire', 'Auditorium B', '2025-03-15T18:00:00Z', '2025-03-15T20:05:00Z', '3D',   'approved',     'active',   '2025-03-11T10:20:00Z'),
  ('11111111-0000-4000-8000-000000000002', 'Civil War',                   'Auditorium C', '2025-03-15T20:30:00Z', '2025-03-15T22:25:00Z', 'IMAX', 'needs-review', 'active',   '2025-03-13T09:10:00Z'),
  ('11111111-0000-4000-8000-000000000002', 'Past Lives',                  'Auditorium D', '2025-03-16T01:00:00Z', '2025-03-16T02:45:00Z', '2D',   'approved',     'active',   '2025-03-13T09:10:00Z'),
  ('11111111-0000-4000-8000-000000000002', 'The Holdovers',               'Auditorium E', '2025-03-14T22:30:00Z', '2025-03-15T00:42:00Z', '2D',   'draft',        'archived', '2025-02-25T08:00:00Z'),
  ('11111111-0000-4000-8000-000000000003', 'Perfect Days',                'Screen 1',     '2025-03-15T17:00:00Z', '2025-03-15T18:55:00Z', '2D',   'approved',     'active',   '2025-03-09T14:00:00Z'),
  ('11111111-0000-4000-8000-000000000003', 'Anatomy of a Fall',           'Screen 2',     '2025-03-15T19:30:00Z', '2025-03-15T21:50:00Z', '2D',   'approved',     'active',   '2025-03-09T14:00:00Z'),
  ('11111111-0000-4000-8000-000000000003', 'The Boy and the Heron',       'Screen 1',     '2025-03-15T22:10:00Z', '2025-03-16T00:20:00Z', 'IMAX', 'flagged',      'active',   '2025-03-09T14:00:00Z')
) as s(theater_id, title, auditorium, start_time, end_time, format, movie_status, status, last_updated)
join public.movies m on m.normalized_title = public.normalize_title(s.title);
