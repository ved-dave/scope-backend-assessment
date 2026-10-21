from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# backend/.env (not the repo-root .env, which points at the remote project).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

LOCAL_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:55322/postgres"


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str]
    page_size_max: int = 50
    preview_sample_size: int = 100


def load_settings() -> Settings:
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    return Settings(
        database_url=os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
    )


settings = load_settings()
