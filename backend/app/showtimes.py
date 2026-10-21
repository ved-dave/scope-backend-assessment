"""Showtime search, filter options, and admin mutations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from psycopg import Connection

from .auth import CurrentUser

SORT_COLUMNS = {
    "title": "lower(m.title)",
    "start_time": "s.start_time",
    "end_time": "s.end_time",
    "last_updated": "s.last_updated",
    "theater": "lower(t.name)",
    "movie_status": "s.movie_status",
}

SHOWTIME_COLUMNS = """
  s.id, s.theater_id, t.name as theater_name, s.movie_id, m.title as movie_title,
  s.movie_status::text as movie_status, s.auditorium, s.start_time, s.end_time,
  m.language, s.format, m.rating, s.last_updated, s.status::text as status
"""

BASE_FROM = """
from showtimes s
join movies m on m.id = s.movie_id
join theaters t on t.id = s.theater_id
"""


@dataclass
class ShowtimeQuery:
    q: str | None = None
    status: str | None = None
    format: str | None = None
    language: str | None = None
    rating: str | None = None
    movie_status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    auditoriums: list[str] = field(default_factory=list)
    theater_ids: list[UUID] = field(default_factory=list)
    sort: str = "start_time"
    order: str = "asc"
    page: int = 1
    page_size: int = 50


def _where(user: CurrentUser, query: ShowtimeQuery) -> tuple[str, dict[str, Any]]:
    scope_sql, params = user.theater_scope_sql("s.theater_id")
    clauses = [scope_sql]

    # Non-admins only ever see approved showtimes.
    if not user.is_admin:
        clauses.append("s.movie_status = 'approved'")
    elif query.movie_status:
        clauses.append("s.movie_status = %(movie_status)s::movie_status")
        params["movie_status"] = query.movie_status

    if query.q and query.q.strip():
        # Match on the normalized title so "spider man" finds "Spider-Man: Homecoming".
        # normalize_title strips non-alphanumerics, so LIKE wildcards in input are inert.
        clauses.append("m.normalized_title like '%%' || normalize_title(%(q)s) || '%%'")
        params["q"] = query.q
    if query.status:
        clauses.append("s.status = %(status)s::showtime_status")
        params["status"] = query.status
    if query.format:
        clauses.append("s.format = %(format)s")
        params["format"] = query.format
    if query.language:
        clauses.append("m.language = %(language)s")
        params["language"] = query.language
    if query.rating:
        clauses.append("m.rating = %(rating)s")
        params["rating"] = query.rating
    if query.auditoriums:
        clauses.append("s.auditorium = any(%(auditoriums)s)")
        params["auditoriums"] = query.auditoriums
    if query.theater_ids:
        clauses.append("s.theater_id = any(%(theater_ids)s)")
        params["theater_ids"] = query.theater_ids
    # Dates are calendar days in each theater's own timezone.
    if query.start_date:
        clauses.append("s.start_time >= (%(start_date)s::date::timestamp at time zone t.timezone)")
        params["start_date"] = query.start_date
    if query.end_date:
        clauses.append("s.start_time < ((%(end_date)s::date + 1)::timestamp at time zone t.timezone)")
        params["end_date"] = query.end_date

    return " and ".join(clauses), params


def search_showtimes(conn: Connection, user: CurrentUser, query: ShowtimeQuery) -> tuple[list[dict], int]:
    where, params = _where(user, query)
    direction = "desc" if query.order == "desc" else "asc"
    order_by = f"{SORT_COLUMNS[query.sort]} {direction}, s.start_time {direction}, s.id"

    total = conn.execute(f"select count(*) as n {BASE_FROM} where {where}", params).fetchone()["n"]
    rows = conn.execute(
        f"""
        select {SHOWTIME_COLUMNS}
        {BASE_FROM}
        where {where}
        order by {order_by}
        limit %(limit)s offset %(offset)s
        """,
        {**params, "limit": query.page_size, "offset": (query.page - 1) * query.page_size},
    ).fetchall()
    return rows, total


def filter_options(conn: Connection, user: CurrentUser, theater_ids: list[UUID]) -> dict[str, list[str]]:
    where, params = _where(user, ShowtimeQuery(theater_ids=theater_ids))

    def distinct(expr: str) -> list[str]:
        sql = f"select distinct {expr} as v {BASE_FROM} where {where} and {expr} <> '' order by 1"
        return [r["v"] for r in conn.execute(sql, params)]

    return {
        "formats": distinct("s.format"),
        "languages": distinct("m.language"),
        "ratings": distinct("m.rating"),
        "auditoriums": distinct("s.auditorium"),
        "movie_statuses": distinct("s.movie_status::text") if user.is_admin else ["approved"],
    }


def get_showtime(conn: Connection, showtime_id: UUID) -> dict | None:
    return conn.execute(f"select {SHOWTIME_COLUMNS} {BASE_FROM} where s.id = %s", (showtime_id,)).fetchone()


def update_showtime(conn: Connection, showtime_id: UUID, movie_status: str | None, status: str | None) -> None:
    conn.execute(
        """
        update showtimes
        set movie_status = coalesce(%(movie_status)s::movie_status, movie_status),
            status = coalesce(%(status)s::showtime_status, status)
        where id = %(id)s
        """,
        {"id": showtime_id, "movie_status": movie_status, "status": status},
    )


def clear_schedule(conn: Connection, theater_id: UUID) -> int:
    # Same lock the upload commit takes, so a clear can't interleave with a commit.
    conn.execute("select 1 from theaters where id = %s for update", (theater_id,))
    cur = conn.execute(
        "update showtimes set status = 'archived' where theater_id = %s and status <> 'archived'",
        (theater_id,),
    )
    return cur.rowcount
