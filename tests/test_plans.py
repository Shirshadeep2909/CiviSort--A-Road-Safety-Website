from __future__ import annotations

import pytest

import civisort.reports as reports
from civisort import create_app
from civisort.db import get_db
from civisort.reports import create_report, merge_reports, review_report, suggest_plan

POINTS = {}


def _mk(lat, cat="pothole", sev=3, cost=10_000, verify=True, lng=88.3620):
    r = create_report(category=cat, description="Synthetic test hazard", lat=lat, lng=lng, photo_filename=None)
    review_report(r["id"], actor_role="reviewer", severity=sev, exposure=3, vulnerability=0,
                  estimated_cost=cost, evidence_action="verify" if verify else None)
    return r["id"]


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield app


def test_isolated_abc_example_via_planner(ctx, monkeypatch):
    a = _mk(22.5170, cost=60_000)
    b = _mk(22.5180, cost=40_000)
    c = _mk(22.5190, cost=30_000)
    pts = {a: 90.0, b: 70.0, c: 65.0}
    real = reports.attach_score

    def fake(report, scenarios, now=None):
        item = real(report, scenarios, now)
        item["score"] = {**item["score"], "total": pts[report["id"]]}
        return item

    monkeypatch.setattr(reports, "attach_score", fake)
    plan = suggest_plan(70_000, {})
    assert plan["budgetmix"]["selected_ids"] == [b, c]
    assert plan["budgetmix"]["total_points"] == 135
    assert plan["baseline"]["selected_ids"] == [a]
    assert plan["budgetmix"]["remaining"] == 0


def test_exclusions_duplicates_and_reasons(ctx):
    p = _mk(22.5175)
    child = _mk(22.51752)
    unver = _mk(22.5195, verify=False)
    nocost = create_report(category="drainage", description="Synthetic no cost", lat=22.5200, lng=88.3630, photo_filename=None)
    review_report(nocost["id"], actor_role="reviewer", severity=2, exposure=2, vulnerability=0, evidence_action="verify")
    merge_reports(child, p, "reviewer")
    plan = suggest_plan(1_000_000, {})
    ids = plan["budgetmix"]["selected_ids"]
    assert p in ids and child not in ids and unver not in ids
    reasons = {e["id"]: e["reason"] for e in plan["excluded"]}
    assert reasons[child] == "duplicate"
    assert reasons[unver] == "unverified"
    assert reasons[nocost["id"]] == "missing_cost"


def test_not_selected_reason_and_rounding(ctx):
    x = _mk(22.5175, sev=5, cost=5_001)
    y = _mk(22.5190, sev=1, cost=5_000, lng=88.3640)
    plan = suggest_plan(6_999, {})  # usable budget 6,000; x costs 6 units, y 5 units
    assert plan["budgetmix"]["usable_budget_units"] == 6_000
    assert plan["budgetmix"]["selected_ids"] == [x]
    assert {e["id"]: e["reason"] for e in plan["excluded"]} == {y: "not_selected"}


def test_budget_validation(ctx):
    with pytest.raises(reports.ReportError):
        suggest_plan(-1, {})
    with pytest.raises(reports.ReportError):
        suggest_plan(10**12, {})


def test_scenario_changes_recommendation(ctx):
    d = _mk(22.5175, cat="drainage", sev=2, cost=10_000)
    s = _mk(22.5190, cat="streetlight", sev=2, cost=10_000, lng=88.3640)
    only_one = lambda sc: suggest_plan(10_000, sc)["budgetmix"]["selected_ids"]
    assert only_one({"rain": True}) == [d]
    assert only_one({"night": True}) == [s]


def test_save_plan_reviewer_only_and_snapshot_frozen(app):
    client = app.test_client()
    with app.app_context():
        rid = _mk(22.5175, cost=8_000)
    body = {"budget": 10_000, "rain": True}
    assert client.post("/api/plan/save", json=body).status_code == 400
    assert client.get("/api/plans").get_json()["plans"] == []
    res = client.post("/api/plan/save", json=body, headers={"X-CiviSort-Role": "reviewer"})
    assert res.status_code == 201
    plan = res.get_json()
    snap = plan["snapshot"]
    assert [i["id"] for i in snap["selected"]] == [rid]
    assert snap["selected"][0]["score"]["conditions_points"] == 15
    assert plan["budget"] == 10_000 and plan["rain"] == 1
    # Change live data and settings; the snapshot must not move.
    client.post(f"/api/reports/{rid}/review", json={"severity": 1, "estimated_cost": 9_000}, headers={"X-CiviSort-Role": "reviewer"})
    later = client.get(f"/api/plans/{plan['id']}").get_json()
    assert later["snapshot"] == snap and later["total_points"] == plan["total_points"]
    # planned report moved to Planned
    assert client.get(f"/api/reports/{rid}").get_json()["repair_status"] == "planned"


def test_saved_plan_persists_across_restart(tmp_path):
    cfg = {"TESTING": True, "DATABASE": str(tmp_path / "p.db"), "UPLOAD_DIR": str(tmp_path / "u")}
    app = create_app(cfg)
    with app.app_context():
        _mk(22.5175, cost=8_000)
    pid = app.test_client().post("/api/plan/save", json={"budget": 10_000}, headers={"X-CiviSort-Role": "reviewer"}).get_json()["id"]
    app2 = create_app(cfg)
    got = app2.test_client().get(f"/api/plans/{pid}").get_json()
    assert got["budget"] == 10_000 and got["snapshot"]["selected"]
