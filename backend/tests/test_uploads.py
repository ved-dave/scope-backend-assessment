from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from .conftest import ADMIN, ADMIN_ALL, DOWNTOWN, ROOT, UPTOWN, VIEWER, as_user

HEADER = "theater_name,movie_title,auditorium,start_time,end_time,language,format,rating,last_updated\n"


def upload(client, csv: str | bytes, user=ADMIN, theater_id: str | None = DOWNTOWN):
    params = {"theater_id": theater_id} if theater_id else {}
    data = csv.encode() if isinstance(csv, str) else csv
    return client.post(
        "/uploadshowtime", params=params, files={"file": ("drop.csv", data, "text/csv")}, headers=as_user(user)
    )


def commit(client, upload_id: str, user=ADMIN):
    return client.post(f"/uploads/{upload_id}/commit", headers=as_user(user))


def live(client, theater=DOWNTOWN):
    resp = client.get(f"/movies?theater_id={theater}&status=active&sort=start_time", headers=as_user(ADMIN_ALL))
    return [(i["movieTitle"], i["startTime"], i["auditorium"], i["format"]) for i in resp.json()["items"]]


def test_sample_drop_end_to_end(client):
    resp = upload(client, (ROOT / "sample-data" / "new-drop.csv").read_bytes())
    assert resp.status_code == 201, resp.text
    preview = resp.json()
    assert preview["status"] == "staged"
    assert preview["summary"] == {
        "totalRows": 6, "adds": 2, "updates": 2, "unchanged": 1, "archives": 2, "duplicates": 1, "invalid": 0,
    }
    updates = {u["movieTitle"]: u["diffs"] for u in preview["samples"]["update"]}
    # Messy titles still match the existing showtime via normalization.
    assert updates["Spider Man - Homecoming"] == [
        {"field": "auditorium", "oldValue": "Auditorium 1", "newValue": "Aud 1"}
    ]
    assert {a["movieTitle"] for a in preview["samples"]["archive"]} == {"Dune: Part Two", "Kung Fu Panda 4"}

    # Nothing applied before commit.
    assert ("Spider-Man: Homecoming", "2025-03-15T18:00:00Z", "Auditorium 1", "2D") in live(client)

    resp = commit(client, preview["uploadId"])
    assert resp.status_code == 200 and resp.json()["status"] == "committed"

    schedule = live(client)
    assert ("Spider-Man: Homecoming", "2025-03-15T18:00:00Z", "Aud 1", "2D") in schedule
    assert ("Kung Fu Panda 4", "2025-03-15T18:30:00Z", "Auditorium 5", "2D") in schedule
    assert sum(1 for s in schedule if s[0] == "Kung Fu Panda 4") == 1  # deduped, old 3/16 one archived

    # Missing showtimes are archived and flagged for admin review.
    review = client.get(
        f"/movies?theater_id={DOWNTOWN}&status=archived&movie_status=needs-review", headers=as_user(ADMIN)
    ).json()["items"]
    assert {(i["movieTitle"], i["startTime"]) for i in review} == {
        ("Dune: Part Two", "2025-03-15T20:00:00Z"),
        ("Kung Fu Panda 4", "2025-03-16T17:30:00Z"),
    }
    assert commit(client, preview["uploadId"]).status_code == 409


def test_reupload_is_idempotent(client):
    csv = (ROOT / "sample-data" / "new-drop.csv").read_bytes()
    commit(client, upload(client, csv).json()["uploadId"])
    before = live(client)
    second = upload(client, csv).json()
    assert second["summary"]["adds"] == 0
    assert second["summary"]["archives"] == 0
    assert second["summary"]["updates"] == 0
    commit(client, second["uploadId"])
    assert live(client) == before


def test_upload_requires_admin_and_access(client):
    csv = HEADER + "Downtown Cinema 7,X,A,2025-03-15T18:00:00Z,2025-03-15T20:00:00Z,EN,2D,PG,\n"
    assert upload(client, csv, user=VIEWER).status_code == 403
    assert upload(client, csv, user=ADMIN, theater_id=UPTOWN).status_code == 403


def test_bad_file_rejected(client):
    assert upload(client, "movie_title,start_time\nX,2025-03-15T18:00:00Z\n").status_code == 400
    assert upload(client, b"\xff\xfe\x00garbage").status_code == 400


def test_invalid_rows_reported_not_applied(client):
    csv = HEADER + "\n".join([
        "Downtown Cinema 7,Good Movie,A,2025-03-15T18:00:00Z,2025-03-15T20:00:00Z,en,2d,pg,",
        "Downtown Cinema 7,Bad Time,A,tomorrow,2025-03-15T20:00:00Z,EN,2D,PG,",
        "Downtown Cinema 7,No Zone,A,2025-03-15T18:00:00,2025-03-15T20:00:00Z,EN,2D,PG,",
        "Downtown Cinema 7,Backwards,A,2025-03-15T21:00:00Z,2025-03-15T20:00:00Z,EN,2D,PG,",
        "Nowhere Cinema,Lost,A,2025-03-15T18:00:00Z,2025-03-15T20:00:00Z,EN,2D,PG,",
        "Riverside Multiplex,Elsewhere,A,2025-03-15T18:00:00Z,2025-03-15T20:00:00Z,EN,2D,PG,",
        "Uptown Arts Theater,Forbidden,A,2025-03-15T18:00:00Z,2025-03-15T20:00:00Z,EN,2D,PG,",
        ",,,,,,,,",
    ]) + "\n"
    preview = upload(client, csv).json()
    assert preview["summary"]["totalRows"] == 7  # blank line skipped
    assert preview["summary"]["adds"] == 1
    errors = {c["movieTitle"]: c["error"] for c in preview["samples"]["invalid"]}
    assert "ISO-8601" in errors["Bad Time"]
    assert "timezone" in errors["No Zone"]
    assert "before" in errors["Backwards"]
    assert "unknown theater" in errors["Lost"]
    assert "different theater" in errors["Elsewhere"]
    assert "no access" in errors["Forbidden"]

    commit(client, preview["uploadId"])
    added = [s for s in live(client) if s[0] == "Good Movie"]
    assert added == [("Good Movie", "2025-03-15T18:00:00Z", "A", "2D")]  # values cleaned/uppercased


def test_no_valid_rows_never_archives(client):
    before = live(client)
    csv = HEADER + "Downtown Cinema 7,Bad,A,nope,nope,EN,2D,PG,\n"
    preview = upload(client, csv).json()
    assert preview["summary"]["archives"] == 0
    commit(client, preview["uploadId"])
    assert live(client) == before


def test_archive_scoped_to_theaters_in_drop(client):
    csv = HEADER + "Downtown Cinema 7,Only One,A,2025-03-20T18:00:00Z,2025-03-20T20:00:00Z,EN,2D,PG,\n"
    preview = upload(client, csv, user=ADMIN_ALL, theater_id=None).json()
    assert preview["summary"]["archives"] == 5  # all live Downtown showtimes
    commit(client, preview["uploadId"], user=ADMIN_ALL)
    assert len(live(client, UPTOWN)) == 3  # untouched


def test_stale_preview_is_superseded(client):
    a = upload(client, HEADER + "Downtown Cinema 7,A,A,2025-03-20T18:00:00Z,2025-03-20T20:00:00Z,EN,2D,PG,\n").json()
    b = upload(client, HEADER + "Downtown Cinema 7,B,A,2025-03-20T18:00:00Z,2025-03-20T20:00:00Z,EN,2D,PG,\n").json()
    assert commit(client, b["uploadId"]).status_code == 200
    assert client.get(f"/uploads/{a['uploadId']}", headers=as_user(ADMIN)).json()["status"] == "superseded"
    assert commit(client, a["uploadId"]).status_code == 409
    assert [s[0] for s in live(client)] == ["B"]


def test_commit_reconciles_against_current_schedule(client):
    preview = upload(client, (ROOT / "sample-data" / "existing.csv").read_bytes()).json()
    assert preview["summary"]["adds"] == 2  # Wonka + Oppenheimer are archived in seed
    client.post(f"/theaters/{DOWNTOWN}/clear-schedule", headers=as_user(ADMIN))
    result = commit(client, preview["uploadId"]).json()
    # Everything was archived after the preview, so the commit re-adds all six.
    assert result["summary"]["adds"] == 6 and result["summary"]["updates"] == 0
    assert len(live(client)) == 6


def test_paged_changes(client):
    rows = [
        f"Downtown Cinema 7,Movie {i},A,2025-04-01T{i % 24:02d}:00:00Z,2025-04-01T{i % 24:02d}:30:00Z,EN,2D,PG,"
        for i in range(24)
    ]
    upload_id = upload(client, HEADER + "\n".join(rows)).json()["uploadId"]
    page = client.get(f"/uploads/{upload_id}/changes?type=add&page=2&page_size=10", headers=as_user(ADMIN)).json()
    assert page["total"] == 24 and len(page["items"]) == 10
    assert page["items"][0]["rowNumber"] == 12


def test_large_upload(client):
    """100k rows across many movies: stage + commit should stay well within a request timeout."""
    start = datetime(2025, 5, 1, tzinfo=timezone.utc)
    lines = []
    for i in range(100_000):
        t = start + timedelta(minutes=15 * i)
        lines.append(
            f"Downtown Cinema 7,Feature {i % 2000},Aud {i % 12},{t.isoformat()},"
            f"{(t + timedelta(hours=2)).isoformat()},EN,2D,PG-13,2025-04-01T00:00:00Z"
        )
    csv = HEADER + "\n".join(lines)

    began = time.perf_counter()
    preview = upload(client, csv).json()
    staged = time.perf_counter() - began
    assert preview["summary"]["adds"] == 100_000
    assert len(preview["samples"]["add"]) == 100  # preview payload stays small

    began = time.perf_counter()
    assert commit(client, preview["uploadId"]).status_code == 200
    committed = time.perf_counter() - began
    print(f"\n100k rows: stage {staged:.1f}s, commit {committed:.1f}s")
    assert staged < 60 and committed < 60

    resp = client.get("/movies?q=feature 1999&sort=start_time&page_size=50", headers=as_user(ADMIN)).json()
    assert resp["total"] == 50
