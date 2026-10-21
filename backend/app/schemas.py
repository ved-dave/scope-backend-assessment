"""API models. JSON uses camelCase to match the frontend types in src/types/assessment.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

ShowtimeStatus = Literal["active", "inactive", "archived"]
MovieStatus = Literal["approved", "draft", "flagged", "needs-review"]
UserRole = Literal["admin", "user"]
SortField = Literal["title", "start_time", "end_time", "last_updated", "theater", "movie_status"]
SortOrder = Literal["asc", "desc"]
ChangeType = Literal["add", "update", "unchanged", "archive", "duplicate", "invalid"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class HealthResponse(ApiModel):
    status: str = "ok"
    timestamp: datetime


class UserOut(ApiModel):
    id: UUID
    name: str
    email: str
    role: UserRole
    can_view_all: bool
    theater_ids: list[UUID]


class TheaterOut(ApiModel):
    id: UUID
    name: str
    location: str
    timezone: str


class ShowtimeOut(ApiModel):
    id: UUID
    theater_id: UUID
    theater_name: str
    movie_id: UUID
    movie_title: str
    movie_status: MovieStatus
    auditorium: str
    start_time: datetime
    end_time: datetime
    language: str
    format: str
    rating: str
    last_updated: datetime
    status: ShowtimeStatus


class ShowtimePage(ApiModel):
    items: list[ShowtimeOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class FilterOptions(ApiModel):
    formats: list[str]
    languages: list[str]
    ratings: list[str]
    auditoriums: list[str]
    movie_statuses: list[MovieStatus]


class ShowtimeUpdateIn(ApiModel):
    movie_status: MovieStatus | None = None
    status: ShowtimeStatus | None = None


class ClearScheduleOut(ApiModel):
    theater_id: UUID
    archived: int


# --- CSV upload -------------------------------------------------------------


class FieldDiff(ApiModel):
    field: str
    old_value: str | None
    new_value: str | None


class UploadChange(ApiModel):
    """One row of an upload diff. Which fields are set depends on `type`."""

    type: ChangeType
    row_number: int | None = None
    showtime_id: UUID | None = None
    theater_name: str
    movie_title: str
    auditorium: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    language: str | None = None
    format: str | None = None
    rating: str | None = None
    diffs: list[FieldDiff] = []
    error: str | None = None


class UploadSummary(ApiModel):
    total_rows: int = 0
    adds: int = 0
    updates: int = 0
    unchanged: int = 0
    archives: int = 0
    duplicates: int = 0
    invalid: int = 0


class UploadPreview(ApiModel):
    upload_id: UUID
    status: Literal["staged", "committed", "superseded"]
    filename: str | None
    theater_ids: list[UUID]
    created_at: datetime
    committed_at: datetime | None
    summary: UploadSummary
    # First N of each category; page through the rest with /uploads/{id}/changes.
    samples: dict[ChangeType, list[UploadChange]]


class UploadChangePage(ApiModel):
    items: list[UploadChange]
    page: int
    page_size: int
    total: int
