from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from civisort import create_app
from civisort.db import get_db, init_schema
from civisort.geo import haversine_m
from civisort.reports import (
    ReportError,
    claim_repair,
    close_repair,
    create_report,
    merge_reports,
    ranked_reports,
    reopen_repair,
    review_report,
    set_repair_status,
    suggest_plan,
)


def jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (40, 30), (20, 40, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def test_duplicate_exclusion(app):
    with app.app_context():
        a = create_report(
            category="pothole",
            description="First pin on Lane 4 for duplicate testing.",
            lat=22.5180,
            lng=88.3620,
            photo_filename=None,
        )
        b = create_report(
            category="pothole",
            description="Second pin within fifty metres of the first.",
            lat=22.51815,
            lng=88.3621,
            photo_filename=None,
        )
        assert haversine_m(a["lat"], a["lng"], b["lat"], b["lng"]) < 50
        merge_reports(b["id"], a["id"], "reviewer")
        ranked = ranked_reports({"rain": False, "night": False, "school_hours": False})
        assert a["id"] in {r["id"] for r in ranked}
        assert b["id"] not in {r["id"] for r in ranked}
        parent = next(r for r in ranked if r["id"] == a["id"])
        assert [d["id"] for d in parent["linked_duplicates"]] == [b["id"]]
        review_report(a["id"], actor_role="reviewer", severity=3, exposure=3, vulnerability=0, estimated_cost=9000, evidence_action="verify")
        plan = suggest_plan(50_000, {"rain": False, "night": False, "school_hours": False})
        assert b["id"] not in plan["budgetmix"]["selected_ids"]
        child_excluded = [e for e in plan["excluded"] if e["id"] == b["id"]]
        assert child_excluded and child_excluded[0]["reason"] == "duplicate"


def test_status_transitions(app):
    with app.app_context():
        r = create_report(
            category="streetlight",
            description="Lamp out for workflow testing of receipt states.",
            lat=22.519,
            lng=88.363,
            photo_filename=None,
        )
        with pytest.raises(ReportError):
            close_repair(r["id"], "reviewer")
        review_report(r["id"], actor_role="reviewer", severity=2, exposure=2, vulnerability=0, estimated_cost=4000, evidence_action="verify")
        set_repair_status(r["id"], "planned", "reviewer", "Saved in test plan.")
        claim_repair(r["id"], "resident", "Replaced the bulb and cleaned the bowl.", None)
        closed = close_repair(r["id"], "reviewer")
        assert closed["repair_status"] == "closed"
        with pytest.raises(ReportError):
            claim_repair(r["id"], "resident", "Too late.", None)
        reopened = reopen_repair(r["id"], "reviewer", "Light failed again after two nights.")
        assert reopened["repair_status"] == "planned"
        assert reopened["closed_at"] is None


def test_invalid_inputs_rejected(client):
    bad = client.post(
        "/api/reports",
        data={"category": "alien", "description": "too short", "lat": "999", "lng": "0"},
    )
    assert bad.status_code == 400
    photo = client.post(
        "/api/reports",
        data={
            "category": "pothole",
            "description": "A real description of a hole.",
            "lat": "22.518",
            "lng": "88.362",
            "photo": (BytesIO(b"not-an-image"), "x.exe"),
        },
        content_type="multipart/form-data",
    )
    assert photo.status_code == 400
    review = client.post(
        "/api/reports/1/review",
        json={"severity": 9},
        headers={"X-CiviSort-Role": "reviewer"},
    )
    assert review.status_code == 400


def test_persistence_across_app_objects(tmp_path):
    db = str(tmp_path / "keep.sqlite3")
    uploads = str(tmp_path / "up")
    app1 = create_app({"TESTING": True, "DATABASE": db, "UPLOAD_DIR": uploads})
    with app1.app_context():
        init_schema(get_db())
        created = create_report(
            category="drainage",
            description="Blocked drain that must survive a restart.",
            lat=22.52,
            lng=88.36,
            photo_filename=None,
        )
        rid = created["id"]
    app2 = create_app({"TESTING": True, "DATABASE": db, "UPLOAD_DIR": uploads})
    with app2.app_context():
        row = get_db().execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        assert row["description"].startswith("Blocked drain")


def test_resident_cannot_verify(app):
    with app.app_context():
        r = create_report(
            category="crossing",
            description="Ramp blocked by a fallen bollard during tests.",
            lat=22.517,
            lng=88.361,
            photo_filename=None,
        )
        with pytest.raises(ReportError):
            review_report(r["id"], actor_role="resident", evidence_action="verify")
