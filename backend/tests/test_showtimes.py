from __future__ import annotations

from .conftest import (
    ADMIN,
    ADMIN_ALL,
    DOWNTOWN,
    RIVERSIDE,
    UPTOWN,
    VIEWER,
    VIEWER_ALL,
    VIEWER_MULTI,
    VIEWER_NONE,
    as_user,
)


def titles(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return [i["movieTitle"] for i in resp.json()["items"]]


def test_identity_required(client):
    assert client.get("/movies").status_code == 401
    assert client.get("/movies", headers={"X-User-Id": "not-a-uuid"}).status_code == 401
    assert client.get("/movies", headers=as_user("00000000-0000-4000-8000-000000000000")).status_code == 401


def test_users_and_me(client):
    users = client.get("/users").json()
    assert len(users) == 6
    me = client.get("/me", headers=as_user(VIEWER_MULTI)).json()
    assert me["role"] == "user"
    assert sorted(me["theaterIds"]) == sorted([DOWNTOWN, UPTOWN])


def test_theaters_scoped_to_user(client):
    def names(user):
        return {t["id"] for t in client.get("/theaters", headers=as_user(user)).json()}

    assert names(VIEWER) == {DOWNTOWN}
    assert names(VIEWER_NONE) == set()
    assert names(VIEWER_ALL) == {DOWNTOWN, RIVERSIDE, UPTOWN}
    assert names(ADMIN) == {DOWNTOWN, RIVERSIDE}  # admin role does not imply all theaters


def test_non_admin_sees_only_approved_in_own_theaters(client):
    items = client.get("/movies", headers=as_user(VIEWER)).json()["items"]
    assert items and all(i["movieStatus"] == "approved" for i in items)
    assert {i["theaterId"] for i in items} == {DOWNTOWN}

    assert client.get("/movies", headers=as_user(VIEWER_NONE)).json()["total"] == 0
    everywhere = client.get("/movies", headers=as_user(VIEWER_ALL)).json()["items"]
    assert {i["theaterId"] for i in everywhere} == {DOWNTOWN, RIVERSIDE, UPTOWN}


def test_movie_status_is_admin_only(client):
    assert client.get("/movies?movie_status=draft", headers=as_user(VIEWER)).status_code == 403
    assert client.get("/movies?sort=movie_status", headers=as_user(VIEWER)).status_code == 403
    drafts = client.get("/movies?movie_status=draft", headers=as_user(ADMIN_ALL)).json()["items"]
    assert {i["movieTitle"] for i in drafts} == {"Kung Fu Panda 4", "The Holdovers"}


def test_theater_filter_requires_access(client):
    assert client.get(f"/movies?theater_id={UPTOWN}", headers=as_user(VIEWER)).status_code == 403
    resp = client.get(f"/movies?theater_id={RIVERSIDE}", headers=as_user(ADMIN))
    assert {i["theaterId"] for i in resp.json()["items"]} == {RIVERSIDE}


def test_title_search_is_normalized(client):
    assert titles(client.get("/movies?q=spider man", headers=as_user(ADMIN))) == ["Spider-Man: Homecoming"]
    assert titles(client.get("/movies?q=SPIDER-MAN:", headers=as_user(ADMIN))) == ["Spider-Man: Homecoming"]
    assert titles(client.get("/movies?q=dune&status=active", headers=as_user(ADMIN))) == ["Dune: Part Two"] * 2


def test_sorting(client):
    h = as_user(ADMIN_ALL)
    asc = titles(client.get("/movies?sort=title&order=asc", headers=h))
    assert asc == sorted(asc, key=str.lower)
    desc = titles(client.get("/movies?sort=title&order=desc", headers=h))
    assert desc == sorted(desc, key=str.lower, reverse=True)

    starts = [i["startTime"] for i in client.get("/movies?sort=start_time&order=desc", headers=h).json()["items"]]
    assert starts == sorted(starts, reverse=True)


def test_filters(client):
    h = as_user(ADMIN_ALL)
    imax = client.get("/movies?format=IMAX", headers=h).json()["items"]
    assert imax and all(i["format"] == "IMAX" for i in imax)
    ko = titles(client.get("/movies?language=KO", headers=h))
    assert ko == ["Past Lives"]
    auds = client.get("/movies?auditorium=Screen 1&auditorium=Screen 2", headers=h).json()["items"]
    assert {i["auditorium"] for i in auds} == {"Screen 1", "Screen 2"}
    archived = client.get("/movies?status=archived", headers=h).json()["items"]
    assert {i["movieTitle"] for i in archived} == {"Wonka", "Oppenheimer", "The Holdovers"}


def test_date_filter_uses_theater_timezone(client):
    # Past Lives starts 2025-03-16T01:00Z, i.e. 18:00 on Mar 15 in Portland.
    h = as_user(ADMIN_ALL)
    mar15 = titles(client.get(f"/movies?theater_id={RIVERSIDE}&start_date=2025-03-15&end_date=2025-03-15", headers=h))
    assert "Past Lives" in mar15
    mar16 = titles(client.get(f"/movies?theater_id={RIVERSIDE}&start_date=2025-03-16", headers=h))
    assert "Past Lives" not in mar16


def test_pagination(client):
    h = as_user(ADMIN_ALL)
    assert client.get("/movies?page_size=51", headers=h).status_code == 422
    page1 = client.get("/movies?page_size=4&page=1", headers=h).json()
    page4 = client.get("/movies?page_size=4&page=4", headers=h).json()
    assert page1["total"] == 15 and page1["totalPages"] == 4
    assert len(page1["items"]) == 4 and len(page4["items"]) == 3
    seen = set()
    for page in range(1, 5):
        seen |= {i["id"] for i in client.get(f"/movies?page_size=4&page={page}", headers=h).json()["items"]}
    assert len(seen) == 15


def test_filter_options(client):
    opts = client.get("/movies/filters", headers=as_user(VIEWER)).json()
    assert opts["movieStatuses"] == ["approved"]
    assert "Screen 1" not in opts["auditoriums"]  # uptown isn't visible to Riley
    admin_opts = client.get(f"/movies/filters?theater_id={DOWNTOWN}", headers=as_user(ADMIN)).json()
    assert set(admin_opts["movieStatuses"]) == {"approved", "draft", "flagged", "needs-review"}


def _first_id(client, user, theater):
    return client.get(f"/movies?theater_id={theater}", headers=as_user(user)).json()["items"][0]["id"]


def test_admin_updates_movie_status(client):
    sid = _first_id(client, ADMIN, DOWNTOWN)
    resp = client.patch(f"/showtimes/{sid}", json={"movieStatus": "flagged"}, headers=as_user(ADMIN))
    assert resp.status_code == 200 and resp.json()["movieStatus"] == "flagged"

    assert client.patch(f"/showtimes/{sid}", json={"movieStatus": "approved"}, headers=as_user(VIEWER)).status_code == 403
    assert client.patch(f"/showtimes/{sid}", json={"movieStatus": "bogus"}, headers=as_user(ADMIN)).status_code == 422


def test_admin_cannot_update_other_theaters(client):
    sid = _first_id(client, ADMIN_ALL, UPTOWN)
    assert client.patch(f"/showtimes/{sid}", json={"status": "inactive"}, headers=as_user(ADMIN)).status_code == 404


def test_reactivating_duplicate_conflicts(client, db):
    # Archive a live showtime, add a new live copy, then try to un-archive the old one.
    row = db.execute(
        "select id, movie_id, theater_id, start_time, end_time from showtimes where status = 'active' limit 1"
    ).fetchone()
    db.execute("update showtimes set status = 'archived' where id = %s", (row["id"],))
    db.execute(
        "insert into showtimes (movie_id, theater_id, start_time, end_time) values (%s, %s, %s, %s)",
        (row["movie_id"], row["theater_id"], row["start_time"], row["end_time"]),
    )
    resp = client.patch(f"/showtimes/{row['id']}", json={"status": "active"}, headers=as_user(ADMIN_ALL))
    assert resp.status_code == 409


def test_clear_schedule(client):
    assert client.post(f"/theaters/{DOWNTOWN}/clear-schedule", headers=as_user(VIEWER)).status_code == 403
    assert client.post(f"/theaters/{UPTOWN}/clear-schedule", headers=as_user(ADMIN)).status_code == 403

    resp = client.post(f"/theaters/{DOWNTOWN}/clear-schedule", headers=as_user(ADMIN))
    assert resp.json() == {"theaterId": DOWNTOWN, "archived": 5}
    live = client.get(f"/movies?theater_id={DOWNTOWN}&status=active", headers=as_user(ADMIN)).json()
    assert live["total"] == 0
    other = client.get(f"/movies?theater_id={RIVERSIDE}&status=active", headers=as_user(ADMIN)).json()
    assert other["total"] == 4
