from __future__ import annotations

from civisort import create_app
from civisort.db import get_db
from civisort.seed import seed_if_empty


def _make(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "c.db"), "UPLOAD_DIR": str(tmp_path / "u")})


def test_seed_on_fresh_database_before_any_request(tmp_path):
    app = _make(tmp_path)
    with app.app_context():
        seed_if_empty()
        assert get_db().execute("SELECT COUNT(*) FROM reports").fetchone()[0] >= 18


def test_restart_persists_and_does_not_reseed(tmp_path):
    app = _make(tmp_path)
    with app.app_context():
        seed_if_empty()
    app.test_client().post("/api/reports", data={"category": "pothole", "description": "Deep pothole near the market", "lat": "22.5190", "lng": "88.3620"})
    app2 = _make(tmp_path)
    with app2.app_context():
        seed_if_empty()
        n = get_db().execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    shown = len(app2.test_client().get("/api/reports").get_json()["reports"])
    assert n == shown + 1  # one seeded duplicate child is linked history, not ranked
    assert n >= 20


def test_location_outside_ward_rejected(client):
    r = client.post("/api/reports", data={"category": "pothole", "description": "Far away pothole here", "lat": "12.97", "lng": "77.59"})
    assert r.status_code == 400


def test_oversize_upload_and_unknown_api_return_json_errors(client):
    import io
    big = io.BytesIO(b"0" * (7 * 1024 * 1024))
    r = client.post("/api/reports", data={"category": "pothole", "description": "Oversize photo test", "lat": "22.519", "lng": "88.362", "photo": (big, "a.jpg")}, content_type="multipart/form-data")
    assert r.status_code == 413 and "error" in r.get_json()
    assert client.get("/api/nope").status_code == 404


def test_favicon_served_and_linked(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200 and r.mimetype == "image/svg+xml"
    page = client.get("/").get_data(as_text=True)
    assert 'rel="icon"' in page and "img/favicon.svg" in page
    assert client.get("/static/img/favicon.svg").status_code == 200
