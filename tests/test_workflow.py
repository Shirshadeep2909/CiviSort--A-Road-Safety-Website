from __future__ import annotations

import io
import json

from PIL import Image

from civisort import create_app
from civisort.db import get_db
from civisort.seed import seed_if_empty

RV = {"X-CiviSort-Role": "reviewer"}
RES = {"X-CiviSort-Role": "resident"}


def _png(size=(20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 90)).save(buf, format="PNG")
    return buf.getvalue()


def _new(client, lat="22.5190", lng="88.3620", category="pothole"):
    r = client.post("/api/reports", data={"category": category, "description": "Synthetic workflow hazard", "lat": lat, "lng": lng})
    assert r.status_code == 201
    return r.get_json()["id"]


def _planned(client, **kw):
    rid = _new(client, **kw)
    r = client.post(
        f"/api/reports/{rid}/review",
        json={"severity": 3, "exposure": 3, "vulnerability": 0, "estimated_cost": 5000, "evidence_action": "verify"},
        headers=RV,
    )
    assert r.status_code == 200
    assert client.post("/api/plan/save", json={"budget": 50000}, headers=RV).status_code == 201
    assert client.get(f"/api/reports/{rid}").get_json()["repair_status"] == "planned"
    return rid


def test_resident_cannot_review_merge_close_reopen_or_save(client):
    a = _new(client)
    b = _new(client, lat="22.51905")
    for url, body in [
        (f"/api/reports/{a}/review", {"severity": 3}),
        (f"/api/reports/{a}/merge", {"child_id": b}),
        (f"/api/reports/{a}/close", {}),
        (f"/api/reports/{a}/reopen", {"reason": "not good enough"}),
        ("/api/plan/save", {"budget": 1000}),
    ]:
        assert client.post(url, json=body, headers=RES).status_code == 400, url
        assert client.post(url, json=body).status_code == 400, url  # no role header means resident


def test_claim_requires_planned_and_note_or_photo(client):
    rid = _new(client)
    assert client.post(f"/api/reports/{rid}/claim", data={"note": "Fixed everything properly"}).status_code == 400
    client.post(
        f"/api/reports/{rid}/review",
        json={"severity": 2, "exposure": 2, "vulnerability": 0, "estimated_cost": 3000, "evidence_action": "verify"},
        headers=RV,
    )
    assert client.post(f"/api/reports/{rid}/claim", data={"note": "Fixed everything properly"}).status_code == 400
    client.post("/api/plan/save", json={"budget": 10000}, headers=RV)
    assert client.post(f"/api/reports/{rid}/claim", data={"note": "short"}).status_code == 400
    ok = client.post(
        f"/api/reports/{rid}/claim",
        data={"after_photo": (io.BytesIO(_png()), "x.png")},
        content_type="multipart/form-data",
    )
    assert ok.status_code == 200 and ok.get_json()["repair_status"] == "repair_claimed"
    assert ok.get_json()["after_photo_filename"].endswith(".jpg")


def test_claim_rejects_bad_image(client):
    rid = _planned(client)
    r = client.post(
        f"/api/reports/{rid}/claim",
        data={"after_photo": (io.BytesIO(b"not an image"), "x.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert client.get(f"/api/reports/{rid}").get_json()["repair_status"] == "planned"


def test_close_needs_reviewer_and_claim_then_leaves_active_list(client):
    rid = _planned(client)
    assert client.post(f"/api/reports/{rid}/close", headers=RV).status_code == 400  # nothing claimed
    client.post(f"/api/reports/{rid}/claim", data={"note": "Resurfaced and compacted."})
    assert client.post(f"/api/reports/{rid}/close", headers=RES).status_code == 400
    closed = client.post(f"/api/reports/{rid}/close", headers=RV).get_json()
    assert closed["repair_status"] == "closed" and closed["closed_at"]
    active = client.get("/api/reports?repair_status=active").get_json()["reports"]
    assert rid not in {r["id"] for r in active}
    assert rid in {r["id"] for r in client.get("/api/reports?repair_status=closed").get_json()["reports"]}
    plan = client.post("/api/plan/suggest", json={"budget": 100000}).get_json()
    assert rid not in plan["budgetmix"]["selected_ids"]


def test_reopen_needs_reason_and_valid_state(client):
    rid = _planned(client)
    assert client.post(f"/api/reports/{rid}/reopen", json={"reason": "no reason given here"}, headers=RV).status_code == 400
    client.post(f"/api/reports/{rid}/claim", data={"note": "Resurfaced and compacted."})
    assert client.post(f"/api/reports/{rid}/reopen", json={"reason": "short"}, headers=RV).status_code == 400
    r = client.post(f"/api/reports/{rid}/reopen", json={"reason": "Patch crumbled after rain"}, headers=RV).get_json()
    assert r["repair_status"] == "planned" and r["closed_at"] is None
    events = client.get(f"/api/reports/{rid}").get_json()["events"]
    assert any("Patch crumbled after rain" in e["detail"] for e in events)
    assert all(e["created_at"] for e in events)
    client.post(f"/api/reports/{rid}/claim", data={"note": "Re-done with hot mix."})
    client.post(f"/api/reports/{rid}/close", headers=RV)
    again = client.post(f"/api/reports/{rid}/reopen", json={"reason": "Failed inspection again"}, headers=RV).get_json()
    assert again["repair_status"] == "planned"


def test_evidence_separate_from_repair_and_locked_after_planning(client):
    rid = _new(client)
    d = client.post(f"/api/reports/{rid}/review", json={"evidence_action": "dispute"}, headers=RV).get_json()
    assert d["evidence_status"] == "disputed" and d["repair_status"] == "reported"
    v = client.post(
        f"/api/reports/{rid}/review",
        json={"severity": 3, "exposure": 3, "estimated_cost": 4000, "evidence_action": "verify"},
        headers=RV,
    ).get_json()
    assert v["evidence_status"] == "verified" and v["repair_status"] == "verified"
    d2 = client.post(f"/api/reports/{rid}/review", json={"evidence_action": "dispute"}, headers=RV).get_json()
    assert d2["evidence_status"] == "disputed" and d2["repair_status"] == "reported"
    client.post(f"/api/reports/{rid}/review", json={"evidence_action": "verify"}, headers=RV)
    client.post("/api/plan/save", json={"budget": 10000}, headers=RV)
    assert client.post(f"/api/reports/{rid}/review", json={"evidence_action": "dispute"}, headers=RV).status_code == 400


def test_merge_requires_reviewer_keeps_records_and_excludes_child(client):
    a = _new(client)
    b = _new(client, lat="22.51905")
    far = _new(client, lat="22.5205")
    assert client.post(f"/api/reports/{a}/merge", json={"child_id": far}, headers=RV).status_code == 400
    assert client.post(f"/api/reports/{a}/merge", json={"child_id": a}, headers=RV).status_code == 400
    assert client.post(f"/api/reports/{a}/merge", json={"child_id": b}, headers=RV).status_code == 200
    assert client.post(f"/api/reports/{far}/merge", json={"child_id": b}, headers=RV).status_code == 400
    ranked = {r["id"]: r for r in client.get("/api/reports").get_json()["reports"]}
    assert b not in ranked and a in ranked
    assert [d["id"] for d in ranked[a]["linked_duplicates"]] == [b]
    child = client.get(f"/api/reports/{b}").get_json()  # still reachable as history
    assert child["is_primary"] == 0 and child["primary_public_code"]
    parent = client.get(f"/api/reports/{a}").get_json()
    assert [d["id"] for d in parent["linked_duplicates"]] == [b]
    assert child["severity"] is None  # merging never raises severity


def test_seed_plans_labelled_and_consistent(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "s.db"), "UPLOAD_DIR": str(tmp_path / "u")})
    with app.app_context():
        seed_if_empty()
        db = get_db()
        plans = db.execute("SELECT * FROM plans").fetchall()
        assert plans and all(p["is_synthetic"] and "Synthetic" in p["label"] for p in plans)
        covered = set()
        for p in plans:
            for item in json.loads(p["selected_json"])["selected"]:
                covered.add(item["id"])
                status = db.execute("SELECT repair_status FROM reports WHERE id = ?", (item["id"],)).fetchone()[0]
                assert status in ("planned", "repair_claimed", "closed")
        for st in ("repair_claimed", "closed"):
            rid = db.execute("SELECT id FROM reports WHERE repair_status = ?", (st,)).fetchone()[0]
            assert rid in covered
        children = {r[0] for r in db.execute("SELECT id FROM reports WHERE is_primary = 0")}
        assert children
        shown = {r["id"] for r in app.test_client().get("/api/reports?repair_status=all").get_json()["reports"]}
        assert not (shown & children)
