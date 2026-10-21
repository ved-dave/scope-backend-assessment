"""Tests run against a throwaway `theater_test` database on the local Supabase
Postgres, built from the real migrations + seed so schema drift is caught."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER_URL = os.environ.get("TEST_DATABASE_SERVER_URL", "postgresql://postgres:postgres@127.0.0.1:55322")
TEST_DB = "theater_test"
TEST_URL = f"{SERVER_URL}/{TEST_DB}"

# Must be set before the app (and its pool) is imported.
os.environ["DATABASE_URL"] = TEST_URL

TABLES = "upload_archives, upload_rows, showtimes, uploads, movies, user_theaters, users, theaters"

ADMIN = "22222222-0000-4000-8000-000000000001"  # Avery: downtown + riverside
ADMIN_ALL = "22222222-0000-4000-8000-000000000002"  # Casey: can_view_all
VIEWER = "22222222-0000-4000-8000-000000000003"  # Riley: downtown
VIEWER_MULTI = "22222222-0000-4000-8000-000000000004"  # Morgan: downtown + uptown
VIEWER_NONE = "22222222-0000-4000-8000-000000000005"  # Jordan: no theaters
VIEWER_ALL = "22222222-0000-4000-8000-000000000006"  # Sam: can_view_all
DOWNTOWN = "11111111-0000-4000-8000-000000000001"
RIVERSIDE = "11111111-0000-4000-8000-000000000002"
UPTOWN = "11111111-0000-4000-8000-000000000003"


@pytest.fixture(scope="session", autouse=True)
def test_database():
    with psycopg.connect(f"{SERVER_URL}/postgres", autocommit=True) as admin:
        admin.execute(f"drop database if exists {TEST_DB} with (force)")
        admin.execute(f"create database {TEST_DB}")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("create schema if not exists extensions")  # provided by Supabase in its own DB
        for migration in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
            conn.execute(migration.read_text())
    yield


@pytest.fixture(autouse=True)
def seeded(test_database):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(f"truncate {TABLES} cascade")
        conn.execute((ROOT / "supabase" / "seed.sql").read_text())


@pytest.fixture(scope="session")
def client(test_database):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with psycopg.connect(TEST_URL, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        yield conn


def as_user(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}
