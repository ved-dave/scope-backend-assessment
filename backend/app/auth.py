"""Caller identity without a login system.

The client sends `X-User-Id`; role and theater access are always looked up in
the database, never trusted from the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from psycopg import Connection

from .db import get_conn

Conn = Annotated[Connection, Depends(get_conn)]


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    name: str
    email: str
    role: str
    can_view_all: bool
    theater_ids: list[UUID]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def can_access(self, theater_id: UUID) -> bool:
        return self.can_view_all or theater_id in self.theater_ids

    def theater_scope_sql(self, column: str) -> tuple[str, dict[str, Any]]:
        """WHERE fragment limiting `column` to theaters this user may see."""
        if self.can_view_all:
            return "true", {}
        return f"{column} = any(%(scope_theater_ids)s)", {"scope_theater_ids": self.theater_ids}


USER_QUERY = """
select u.id, u.name, u.email, u.role::text as role, u.can_view_all,
       coalesce(array_agg(ut.theater_id) filter (where ut.theater_id is not null), '{{}}') as theater_ids
from users u
left join user_theaters ut on ut.user_id = u.id
{where}
group by u.id
order by u.role, u.name
"""


def get_current_user(
    conn: Conn,
    x_user_id: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if not x_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-User-Id header")
    try:
        user_id = UUID(x_user_id)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-User-Id header") from None

    row = conn.execute(USER_QUERY.format(where="where u.id = %s"), (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return CurrentUser(**row)


def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


User = Annotated[CurrentUser, Depends(get_current_user)]
Admin = Annotated[CurrentUser, Depends(require_admin)]
