from __future__ import annotations

import math
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

import psycopg.errors
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from . import showtimes as showtime_repo
from . import uploads as upload_repo
from .auth import USER_QUERY, Admin, Conn, CurrentUser, User
from .config import settings
from .db import pool
from .schemas import (
    ChangeType,
    ClearScheduleOut,
    FilterOptions,
    HealthResponse,
    MovieStatus,
    ShowtimeOut,
    ShowtimePage,
    ShowtimeStatus,
    ShowtimeUpdateIn,
    SortField,
    SortOrder,
    TheaterOut,
    UploadChangePage,
    UploadPreview,
    UserOut,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    title="Scope Backend Assessment API",
    version="0.2.0",
    description="Theater showtimes API. Identify the caller with the X-User-Id header.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_theater_access(user: CurrentUser, theater_ids: list[UUID]) -> None:
    denied = [str(t) for t in theater_ids if not user.can_access(t)]
    if denied:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"No access to theater(s): {', '.join(denied)}")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(timestamp=datetime.now(timezone.utc))


# --- Users & theaters -------------------------------------------------------


@app.get("/users", response_model=list[UserOut])
def list_users(conn: Conn) -> list[dict]:
    """Backs the frontend's mock user picker (there is no login system)."""
    return conn.execute(USER_QUERY.format(where="")).fetchall()


@app.get("/me", response_model=UserOut)
def me(user: User) -> CurrentUser:
    return user


@app.get("/theaters", response_model=list[TheaterOut])
def list_theaters(conn: Conn, user: User) -> list[dict]:
    scope, params = user.theater_scope_sql("id")
    return conn.execute(f"select id, name, location, timezone from theaters where {scope} order by name", params).fetchall()


# --- Showtime search --------------------------------------------------------


@app.get("/movies", response_model=ShowtimePage)
def search_movies(
    conn: Conn,
    user: User,
    q: Annotated[str | None, Query(description="Movie title search")] = None,
    status_: Annotated[ShowtimeStatus | None, Query(alias="status")] = None,
    format: str | None = None,
    language: str | None = None,
    rating: str | None = None,
    movie_status: Annotated[MovieStatus | None, Query(description="Admin only")] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    auditorium: Annotated[list[str], Query(description="Repeatable")] = [],
    theater_id: Annotated[list[UUID], Query(description="Repeatable")] = [],
    sort: SortField = "start_time",
    order: SortOrder = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=settings.page_size_max)] = settings.page_size_max,
) -> ShowtimePage:
    """Paged showtime search. Non-admins only see approved showtimes."""
    if not user.is_admin and (movie_status is not None or sort == "movie_status"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can filter or sort by movie status")
    _require_theater_access(user, theater_id)

    query = showtime_repo.ShowtimeQuery(
        q=q, status=status_, format=format, language=language, rating=rating,
        movie_status=movie_status, start_date=start_date, end_date=end_date,
        auditoriums=auditorium, theater_ids=theater_id, sort=sort, order=order,
        page=page, page_size=page_size,
    )
    rows, total = showtime_repo.search_showtimes(conn, user, query)
    return ShowtimePage(
        items=rows, page=page, page_size=page_size, total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@app.get("/movies/filters", response_model=FilterOptions)
def movie_filters(
    conn: Conn,
    user: User,
    theater_id: Annotated[list[UUID], Query(description="Repeatable")] = [],
) -> dict:
    """Distinct values for the filter dropdowns, within the caller's theaters."""
    _require_theater_access(user, theater_id)
    return showtime_repo.filter_options(conn, user, theater_id)


@app.patch("/showtimes/{showtime_id}", response_model=ShowtimeOut)
def update_showtime(conn: Conn, admin: Admin, showtime_id: UUID, body: ShowtimeUpdateIn) -> dict:
    """Admin-only: change movie status (review workflow) and/or showtime status."""
    current = showtime_repo.get_showtime(conn, showtime_id)
    if current is None or not admin.can_access(current["theater_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Showtime not found")
    try:
        showtime_repo.update_showtime(conn, showtime_id, body.movie_status, body.status)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another live showtime already exists for this movie and start time",
        ) from None
    return showtime_repo.get_showtime(conn, showtime_id)


@app.post("/theaters/{theater_id}/clear-schedule", response_model=ClearScheduleOut)
def clear_schedule(conn: Conn, admin: Admin, theater_id: UUID) -> ClearScheduleOut:
    """Admin-only: archive every live showtime for a theater."""
    _require_theater_access(admin, [theater_id])
    if conn.execute("select 1 from theaters where id = %s", (theater_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Theater not found")
    archived = showtime_repo.clear_schedule(conn, theater_id)
    return ClearScheduleOut(theater_id=theater_id, archived=archived)


# --- CSV upload -------------------------------------------------------------


def _get_upload_for(conn: Conn, admin: CurrentUser, upload_id: UUID) -> dict:
    upload = upload_repo.get_upload(conn, upload_id)
    if upload is None or not (
        upload["uploaded_by"] == admin.id or all(admin.can_access(t) for t in upload["theater_ids"])
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return upload


@app.post("/uploadshowtime", response_model=UploadPreview, status_code=status.HTTP_201_CREATED)
def upload_showtimes(
    conn: Conn,
    admin: Admin,
    file: Annotated[UploadFile, File(description="Partner CSV")],
    theater_id: Annotated[
        UUID | None, Query(description="If set, rows for any other theater are rejected")
    ] = None,
) -> dict:
    """Stage a partner CSV and return a preview of the changes. Nothing is
    applied until POST /uploads/{id}/commit."""
    if theater_id is not None:
        _require_theater_access(admin, [theater_id])
    try:
        upload_id = upload_repo.stage_upload(conn, admin, file.file, file.filename, theater_id)
    except upload_repo.CsvFormatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    upload = upload_repo.get_upload(conn, upload_id)
    return upload_repo.preview(conn, upload, settings.preview_sample_size)


@app.get("/uploads/{upload_id}", response_model=UploadPreview)
def get_upload(conn: Conn, admin: Admin, upload_id: UUID) -> dict:
    upload = _get_upload_for(conn, admin, upload_id)
    return upload_repo.preview(conn, upload, settings.preview_sample_size)


@app.get("/uploads/{upload_id}/changes", response_model=UploadChangePage)
def list_upload_changes(
    conn: Conn,
    admin: Admin,
    upload_id: UUID,
    type: ChangeType,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> UploadChangePage:
    upload = _get_upload_for(conn, admin, upload_id)
    rows, total = upload_repo.list_changes(conn, upload, type, page_size, (page - 1) * page_size)
    return UploadChangePage(items=rows, page=page, page_size=page_size, total=total)


@app.post("/uploads/{upload_id}/commit", response_model=UploadPreview)
def commit_upload(conn: Conn, admin: Admin, upload_id: UUID) -> dict:
    """Apply a staged upload. Re-reconciles against the current schedule first,
    so the result is correct even if the schedule changed after the preview."""
    _get_upload_for(conn, admin, upload_id)
    try:
        upload_repo.commit_upload(conn, upload_id)
    except upload_repo.UploadStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    upload = upload_repo.get_upload(conn, upload_id)
    return upload_repo.preview(conn, upload, settings.preview_sample_size)
