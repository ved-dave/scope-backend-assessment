from __future__ import annotations

from collections.abc import Iterator

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool: ConnectionPool[Connection[DictRow]] = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    open=False,
    kwargs={"row_factory": dict_row},
)


def get_conn() -> Iterator[Connection[DictRow]]:
    """One connection per request; commits on success, rolls back on error."""
    with pool.connection() as conn:
        yield conn
