"""Partner CSV ingestion: stage -> preview -> commit.

1. `stage_upload` streams the CSV, validates/cleans each row in Python and
   loads it into `upload_rows` with COPY (no per-row INSERTs).
2. `classify` reconciles the staged rows against the live schedule with
   set-based SQL: each row becomes add / update / unchanged / duplicate /
   invalid, and live showtimes missing from the drop go to `upload_archives`.
3. `commit_upload` re-runs `classify` under a lock on the affected theaters
   (the schedule may have changed since preview) and applies everything in one
   transaction.

A showtime's identity is (theater, normalize_title(title), start_time). Fuzzy
matching beyond normalization (e.g. "DUNE PART 2" vs "Dune: Part Two") is
phase 2; such rows currently show up as an add plus an archive.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import IO, Any
from uuid import UUID

from psycopg import Connection

from .auth import CurrentUser

REQUIRED_COLUMNS = ("theater_name", "movie_title", "start_time", "end_time")
OPTIONAL_COLUMNS = ("auditorium", "language", "format", "rating", "last_updated")

STAGE_COLUMNS = (
    "upload_id", "row_number", "theater_name", "movie_title", "auditorium", "start_time",
    "end_time", "language", "format", "rating", "last_updated", "error",
)

_WHITESPACE = re.compile(r"\s+")


class CsvFormatError(ValueError):
    """The file as a whole is unusable (bad encoding, missing header columns)."""


class UploadStateError(Exception):
    """Upload can't be committed in its current state (maps to 409)."""


def _clean(value: str | None) -> str:
    return _WHITESPACE.sub(" ", value or "").strip()


def _parse_ts(value: str, column: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError(f"{column} is required")
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{column} is not an ISO-8601 timestamp: {raw!r}") from None
    if ts.tzinfo is None:
        raise ValueError(f"{column} must include a timezone offset (e.g. 'Z'): {raw!r}")
    return ts


def _clean_row(raw: dict[str, str | None], now: datetime) -> tuple[list[Any], str | None]:
    """Returns the cleaned staging values and the first validation error, if any."""
    theater_name = _clean(raw.get("theater_name"))
    movie_title = _clean(raw.get("movie_title"))
    values: dict[str, Any] = {
        "theater_name": theater_name,
        "movie_title": movie_title,
        "auditorium": _clean(raw.get("auditorium")),
        "language": _clean(raw.get("language")).upper(),
        "format": _clean(raw.get("format")).upper(),
        "rating": _clean(raw.get("rating")).upper(),
        "start_time": None,
        "end_time": None,
        "last_updated": now,
    }
    error = None
    try:
        if not theater_name:
            raise ValueError("theater_name is required")
        if not movie_title:
            raise ValueError("movie_title is required")
        values["start_time"] = _parse_ts(raw.get("start_time") or "", "start_time")
        values["end_time"] = _parse_ts(raw.get("end_time") or "", "end_time")
        if values["end_time"] < values["start_time"]:
            raise ValueError("end_time is before start_time")
        if _clean(raw.get("last_updated")):
            values["last_updated"] = _parse_ts(raw.get("last_updated") or "", "last_updated")
    except ValueError as exc:
        error = str(exc)

    ordered = [values[c] for c in STAGE_COLUMNS[2:-1]]
    return ordered, error


def stage_upload(
    conn: Connection,
    user: CurrentUser,
    file: IO[bytes],
    filename: str | None,
    theater_id: UUID | None,
) -> UUID:
    upload_id: UUID = conn.execute(
        "insert into uploads (uploaded_by, filename) values (%s, %s) returning id",
        (user.id, filename),
    ).fetchone()["id"]

    text = io.TextIOWrapper(file, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    try:
        header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    except UnicodeDecodeError:
        raise CsvFormatError("File must be UTF-8 encoded CSV") from None
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvFormatError(f"CSV is missing required column(s): {', '.join(missing)}")
    reader.fieldnames = header

    now = datetime.now(timezone.utc)
    copy_sql = f"copy upload_rows ({', '.join(STAGE_COLUMNS)}) from stdin"
    try:
        with conn.cursor().copy(copy_sql) as copy:
            for raw in reader:
                if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
                    continue  # blank line
                values, error = _clean_row(raw, now)
                copy.write_row([upload_id, reader.line_num, *values, error])
    except UnicodeDecodeError:
        raise CsvFormatError("File must be UTF-8 encoded CSV") from None
    except csv.Error as exc:
        raise CsvFormatError(f"Malformed CSV near line {reader.line_num}: {exc}") from None

    _resolve_theaters(conn, upload_id, user, theater_id)
    classify(conn, upload_id)
    return upload_id


def _resolve_theaters(conn: Connection, upload_id: UUID, user: CurrentUser, theater_id: UUID | None) -> None:
    """Map theater names to ids and reject rows the uploader may not touch."""
    conn.execute(
        """
        update upload_rows r set theater_id = t.id
        from theaters t
        where r.upload_id = %s and r.error is null and lower(t.name) = lower(r.theater_name)
        """,
        (upload_id,),
    )
    conn.execute(
        "update upload_rows set error = 'unknown theater: ' || theater_name "
        "where upload_id = %s and error is null and theater_id is null",
        (upload_id,),
    )
    if not user.can_view_all:
        conn.execute(
            "update upload_rows set error = 'no access to theater: ' || theater_name "
            "where upload_id = %s and error is null and not (theater_id = any(%s))",
            (upload_id, user.theater_ids),
        )
    if theater_id is not None:
        conn.execute(
            "update upload_rows set error = 'row is for a different theater than the one selected' "
            "where upload_id = %s and error is null and theater_id <> %s",
            (upload_id, theater_id),
        )


def classify(conn: Connection, upload_id: UUID) -> None:
    """(Re)compute row actions, diffs and archives for a staged upload. Idempotent."""
    p = {"upload_id": upload_id}

    conn.execute(
        """
        update upload_rows
        set action = case when error is null then null else 'invalid'::upload_row_action end,
            matched_showtime_id = null,
            diffs = '[]'
        where upload_id = %(upload_id)s
        """,
        p,
    )

    # Keep one row per showtime identity: newest last_updated, then last in file.
    conn.execute(
        """
        update upload_rows r set action = 'duplicate'
        from (
          select row_number, row_number() over (
                   partition by theater_id, normalized_title, start_time
                   order by last_updated desc, row_number desc) as rank
          from upload_rows
          where upload_id = %(upload_id)s and error is null
        ) ranked
        where r.upload_id = %(upload_id)s and r.row_number = ranked.row_number and ranked.rank > 1
        """,
        p,
    )

    # Match against live (non-archived) showtimes; the partial unique index
    # guarantees at most one candidate per identity.
    conn.execute(
        """
        update upload_rows r
        set matched_showtime_id = x.showtime_id,
            diffs = x.diffs
        from (
          select ur.row_number, s.id as showtime_id, d.diffs
          from upload_rows ur
          join showtimes s
            on s.theater_id = ur.theater_id
           and s.start_time = ur.start_time
           and s.status <> 'archived'
          join movies m
            on m.id = s.movie_id
           and m.normalized_title = ur.normalized_title
          cross join lateral (
            select coalesce(jsonb_agg(jsonb_build_object('field', f, 'oldValue', o, 'newValue', n)), '[]') as diffs
            from (values
              ('auditorium', s.auditorium, ur.auditorium),
              ('endTime', to_json(s.end_time) #>> '{}', to_json(ur.end_time) #>> '{}'),
              ('format', s.format, ur.format),
              ('language', m.language, ur.language),
              ('rating', m.rating, ur.rating)
            ) as v(f, o, n)
            where o is distinct from n
          ) d
          where ur.upload_id = %(upload_id)s and ur.action is null
        ) x
        where r.upload_id = %(upload_id)s and r.row_number = x.row_number
        """,
        p,
    )
    conn.execute(
        """
        update upload_rows
        set action = case
          when matched_showtime_id is null then 'add'
          when diffs = '[]' then 'unchanged'
          else 'update' end::upload_row_action
        where upload_id = %(upload_id)s and action is null
        """,
        p,
    )

    # Reconciliation scope: only theaters with valid rows in this drop. A file
    # with no usable rows for a theater must never wipe its schedule.
    conn.execute(
        """
        update uploads set theater_ids = coalesce((
          select array_agg(distinct theater_id) from upload_rows
          where upload_id = %(upload_id)s and action <> 'invalid'), '{}')
        where id = %(upload_id)s
        """,
        p,
    )
    conn.execute("delete from upload_archives where upload_id = %(upload_id)s", p)
    conn.execute(
        """
        insert into upload_archives (upload_id, showtime_id)
        select %(upload_id)s, s.id
        from showtimes s
        join uploads u on u.id = %(upload_id)s
        where s.theater_id = any(u.theater_ids)
          and s.status <> 'archived'
          and not exists (
            select 1 from upload_rows r
            where r.upload_id = %(upload_id)s and r.matched_showtime_id = s.id)
        """,
        p,
    )

    conn.execute(
        """
        update uploads set summary = (
          select jsonb_build_object(
            'totalRows', count(*),
            'adds', count(*) filter (where action = 'add'),
            'updates', count(*) filter (where action = 'update'),
            'unchanged', count(*) filter (where action = 'unchanged'),
            'duplicates', count(*) filter (where action = 'duplicate'),
            'invalid', count(*) filter (where action = 'invalid'),
            'archives', (select count(*) from upload_archives where upload_id = %(upload_id)s))
          from upload_rows where upload_id = %(upload_id)s)
        where id = %(upload_id)s
        """,
        p,
    )


def commit_upload(conn: Connection, upload_id: UUID) -> None:
    upload = conn.execute("select status from uploads where id = %s for update", (upload_id,)).fetchone()
    if upload["status"] != "staged":
        raise UploadStateError(f"Upload is {upload['status']} and can no longer be committed")

    p = {"upload_id": upload_id}
    theater_ids = conn.execute("select theater_ids from uploads where id = %(upload_id)s", p).fetchone()[
        "theater_ids"
    ]
    # Serialize with other commits / schedule clears for the same theaters.
    conn.execute("select 1 from theaters where id = any(%s) order by id for update", (theater_ids,))

    classify(conn, upload_id)

    # Movies: create new titles; refresh language/rating from the newest row.
    conn.execute(
        """
        insert into movies (title, language, rating)
        select distinct on (normalized_title) movie_title, language, rating
        from upload_rows
        where upload_id = %(upload_id)s and action in ('add', 'update', 'unchanged')
        order by normalized_title, last_updated desc, row_number desc
        on conflict on constraint movies_normalized_title_key do update
        set language = coalesce(nullif(excluded.language, ''), movies.language),
            rating = coalesce(nullif(excluded.rating, ''), movies.rating)
        where (movies.language, movies.rating) is distinct from
              (coalesce(nullif(excluded.language, ''), movies.language),
               coalesce(nullif(excluded.rating, ''), movies.rating))
        """,
        p,
    )
    # Missing from the drop: archive and flag for admin review.
    conn.execute(
        """
        update showtimes s
        set status = 'archived', movie_status = 'needs-review', last_upload_id = %(upload_id)s
        from upload_archives a
        where a.upload_id = %(upload_id)s and a.showtime_id = s.id
        """,
        p,
    )
    conn.execute(
        """
        update showtimes s
        set auditorium = r.auditorium, end_time = r.end_time, format = r.format,
            last_updated = r.last_updated, last_upload_id = %(upload_id)s
        from upload_rows r
        where r.upload_id = %(upload_id)s and r.action in ('update', 'unchanged')
          and r.matched_showtime_id = s.id
        """,
        p,
    )
    conn.execute(
        """
        insert into showtimes
          (movie_id, theater_id, auditorium, start_time, end_time, format, last_updated, last_upload_id)
        select m.id, r.theater_id, r.auditorium, r.start_time, r.end_time, r.format, r.last_updated,
               %(upload_id)s
        from upload_rows r
        join movies m on m.normalized_title = r.normalized_title
        where r.upload_id = %(upload_id)s and r.action = 'add'
        """,
        p,
    )

    conn.execute("update uploads set status = 'committed', committed_at = now() where id = %(upload_id)s", p)
    # Older previews for these theaters are now stale; committing them would
    # roll the schedule back.
    conn.execute(
        """
        update uploads set status = 'superseded'
        where status = 'staged' and id <> %(upload_id)s
          and created_at <= (select created_at from uploads where id = %(upload_id)s)
          and theater_ids && %(theater_ids)s
        """,
        {**p, "theater_ids": theater_ids},
    )


# --- Reading previews -------------------------------------------------------

_ROW_CHANGES = """
select r.action::text as type, r.row_number, r.matched_showtime_id as showtime_id,
       r.theater_name, r.movie_title, r.auditorium, r.start_time, r.end_time,
       r.language, r.format, r.rating, r.diffs, r.error
from upload_rows r
where r.upload_id = %(upload_id)s and r.action = %(type)s::upload_row_action
order by r.row_number
limit %(limit)s offset %(offset)s
"""

_ARCHIVE_CHANGES = """
select 'archive' as type, null::int as row_number, s.id as showtime_id,
       t.name as theater_name, m.title as movie_title, s.auditorium, s.start_time, s.end_time,
       m.language, s.format, m.rating, '[]'::jsonb as diffs, null as error
from upload_archives a
join showtimes s on s.id = a.showtime_id
join movies m on m.id = s.movie_id
join theaters t on t.id = s.theater_id
where a.upload_id = %(upload_id)s
order by s.start_time, s.id
limit %(limit)s offset %(offset)s
"""

_SUMMARY_KEYS = {
    "add": "adds", "update": "updates", "unchanged": "unchanged",
    "archive": "archives", "duplicate": "duplicates", "invalid": "invalid",
}


def get_upload(conn: Connection, upload_id: UUID) -> dict | None:
    return conn.execute(
        "select id, uploaded_by, filename, status::text as status, theater_ids, summary, created_at, committed_at "
        "from uploads where id = %s",
        (upload_id,),
    ).fetchone()


def list_changes(conn: Connection, upload: dict, change_type: str, limit: int, offset: int) -> tuple[list[dict], int]:
    sql = _ARCHIVE_CHANGES if change_type == "archive" else _ROW_CHANGES
    rows = conn.execute(
        sql, {"upload_id": upload["id"], "type": change_type, "limit": limit, "offset": offset}
    ).fetchall()
    total = upload["summary"].get(_SUMMARY_KEYS[change_type], 0)
    return rows, total


def preview(conn: Connection, upload: dict, sample_size: int) -> dict:
    samples = {t: list_changes(conn, upload, t, sample_size, 0)[0] for t in _SUMMARY_KEYS if t != "unchanged"}
    return {
        "upload_id": upload["id"],
        "status": upload["status"],
        "filename": upload["filename"],
        "theater_ids": upload["theater_ids"],
        "created_at": upload["created_at"],
        "committed_at": upload["committed_at"],
        "summary": {
            "total_rows": upload["summary"].get("totalRows", 0),
            **{v: upload["summary"].get(v, 0) for v in _SUMMARY_KEYS.values()},
        },
        "samples": samples,
    }

