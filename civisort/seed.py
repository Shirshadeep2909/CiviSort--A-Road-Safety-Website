"""Synthetic demonstration records. Never run automatically except on an empty database."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

from civisort.db import get_db, utcnow
from civisort.images import write_demo_jpeg
from civisort.reports import (
    add_event,
    claim_repair,
    close_repair,
    create_report,
    merge_reports,
    review_report,
    save_plan,
    set_repair_status,
)


def _past(days: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.replace(microsecond=0).isoformat()


def _photo(name: str, color: tuple[int, int, int]) -> str:
    folder = Path(current_app.config["UPLOAD_DIR"])
    filename = f"demo-{name}.jpg"
    write_demo_jpeg(folder / filename, color, name)
    return filename


def _stamp_created(report_id: int, created_at: str) -> None:
    db = get_db()
    db.execute("UPDATE reports SET created_at = ? WHERE id = ?", (created_at, report_id))
    db.execute("UPDATE events SET created_at = ? WHERE report_id = ? AND event_type = 'reported'", (created_at, report_id))
    db.commit()


def seed_all() -> None:
    """Insert ~20 labelled synthetic reports covering scoring, duplicates, budget and receipts."""
    p_before = _photo("before-pothole", (92, 74, 62))
    p_drain = _photo("before-drain", (54, 78, 88))
    p_light = _photo("before-light", (36, 42, 48))
    p_cross = _photo("before-cross", (120, 96, 64))
    p_after = _photo("after-repair", (86, 118, 96))

    def make(**kwargs):
        created = kwargs.pop("created_days", 5)
        report = create_report(actor_role="resident", is_synthetic=True, **kwargs)
        _stamp_created(report["id"], _past(created))
        return report["id"]

    a = make(
        category="pothole",
        description="Deep carriageway break on Ashoka Main near the market entrance. Synthetic demonstration record.",
        lat=22.51895,
        lng=88.36210,
        photo_filename=p_before,
        created_days=40,
    )
    b = make(
        category="streetlight",
        description="Column dark along the bazaar stretch; pedestrians use the unlit crossing. Synthetic demonstration record.",
        lat=22.51940,
        lng=88.36310,
        photo_filename=p_light,
        created_days=40,
    )
    c = make(
        category="crossing",
        description="Dropped kerb missing at Ward Office crossing, leftover debris in the path. Synthetic demonstration record.",
        lat=22.51820,
        lng=88.36140,
        photo_filename=p_cross,
        created_days=40,
    )
    urgent = make(
        category="pothole",
        description="Wide collapse beside the bus stop with standing water after every shower. Synthetic demonstration record.",
        lat=22.51910,
        lng=88.36280,
        photo_filename=p_before,
        created_days=21,
    )
    dup_a = make(
        category="pothole",
        description="Same broken patch reported from the south side of Lane 4. Synthetic demonstration record.",
        lat=22.51740,
        lng=88.36190,
        photo_filename=p_before,
        created_days=8,
    )
    dup_b = make(
        category="pothole",
        description="Pothole on Lane 4, about a house away from the first pin. Synthetic demonstration record.",
        lat=22.51755,
        lng=88.36205,
        photo_filename=p_before,
        created_days=6,
    )
    closed = make(
        category="streetlight",
        description="Lamp replaced after a previous outage on School Road. Synthetic demonstration record.",
        lat=22.52010,
        lng=88.36390,
        photo_filename=p_light,
        created_days=45,
    )
    drain = make(
        category="drainage",
        description="Blocked gully flooding the cycle track whenever it rains. Synthetic demonstration record.",
        lat=22.51850,
        lng=88.36340,
        photo_filename=p_drain,
        school_access=True,
        created_days=10,
    )
    school_x = make(
        category="crossing",
        description="Faded markings at the school gate; families wait in the carriageway. Synthetic demonstration record.",
        lat=22.51970,
        lng=88.36170,
        photo_filename=p_cross,
        school_access=True,
        created_days=14,
    )
    raw = make(
        category="pothole",
        description="Resident photo of a new edge break, not yet reviewed. Synthetic demonstration record.",
        lat=22.51790,
        lng=88.36370,
        photo_filename=None,
        created_days=2,
    )
    disputed = make(
        category="drainage",
        description="Reported overflow; site visit found a temporary construction pump. Synthetic demonstration record.",
        lat=22.51720,
        lng=88.36080,
        photo_filename=p_drain,
        created_days=12,
    )
    night_light = make(
        category="streetlight",
        description="Two consecutive lamps out on the canal path. Synthetic demonstration record.",
        lat=22.51800,
        lng=88.36090,
        photo_filename=p_light,
        created_days=18,
    )
    cheap = make(
        category="pothole",
        description="Shallow edge break that can be patched with a small crew. Synthetic demonstration record.",
        lat=22.52020,
        lng=88.36120,
        photo_filename=p_before,
        created_days=9,
    )
    access = make(
        category="crossing",
        description="Bollard lying across the wheelchair ramp. Synthetic demonstration record.",
        lat=22.51900,
        lng=88.36050,
        photo_filename=p_cross,
        created_days=4,
    )
    expensive = make(
        category="drainage",
        description="Collapsed chamber that needs excavation and a new grill. Synthetic demonstration record.",
        lat=22.52040,
        lng=88.36270,
        photo_filename=p_drain,
        created_days=28,
    )
    no_cost = make(
        category="streetlight",
        description="Flickering lamp, verified but awaiting a cost estimate. Synthetic demonstration record.",
        lat=22.51760,
        lng=88.36320,
        photo_filename=p_light,
        created_days=11,
    )
    merged_parent = make(
        category="drainage",
        description="Standing water at the lane junction, first report. Synthetic demonstration record.",
        lat=22.51870,
        lng=88.36110,
        photo_filename=p_drain,
        created_days=16,
    )
    merged_child = make(
        category="drainage",
        description="Second pin for the same flooded junction. Synthetic demonstration record.",
        lat=22.51878,
        lng=88.36118,
        photo_filename=p_drain,
        created_days=15,
    )
    school_pothole = make(
        category="pothole",
        description="Break on the walking route used at school closing time. Synthetic demonstration record.",
        lat=22.51955,
        lng=88.36240,
        photo_filename=p_before,
        school_access=True,
        created_days=7,
    )
    claimed = make(
        category="crossing",
        description="Temporary timber over a gap; a crew has claimed the permanent fix. Synthetic demonstration record.",
        lat=22.51710,
        lng=88.36260,
        photo_filename=p_cross,
        created_days=20,
    )

    reviewer = "reviewer"
    review_report(a, actor_role=reviewer, severity=5, exposure=3, vulnerability=1, estimated_cost=60000, evidence_action="verify")
    review_report(b, actor_role=reviewer, severity=5, exposure=2, vulnerability=1, estimated_cost=40000, evidence_action="verify")
    review_report(c, actor_role=reviewer, severity=5, exposure=5, vulnerability=0, estimated_cost=30000, evidence_action="verify")
    # Urgent but still unverified — scores exist so inspection highlighting works.
    review_report(urgent, actor_role=reviewer, severity=5, exposure=5, vulnerability=1, school_access=False)
    review_report(drain, actor_role=reviewer, severity=4, exposure=4, vulnerability=0.5, estimated_cost=25000, evidence_action="verify", school_access=True)
    review_report(school_x, actor_role=reviewer, severity=4, exposure=3, vulnerability=1, estimated_cost=18000, evidence_action="verify", school_access=True)
    review_report(disputed, actor_role=reviewer, severity=2, exposure=2, vulnerability=0, estimated_cost=15000, evidence_action="dispute")
    review_report(night_light, actor_role=reviewer, severity=3, exposure=5, vulnerability=0, estimated_cost=12000, evidence_action="verify")
    review_report(cheap, actor_role=reviewer, severity=2, exposure=2, vulnerability=0, estimated_cost=8000, evidence_action="verify")
    review_report(expensive, actor_role=reviewer, severity=5, exposure=4, vulnerability=1, estimated_cost=90000, evidence_action="verify")
    review_report(no_cost, actor_role=reviewer, severity=3, exposure=3, vulnerability=0, evidence_action="verify")
    review_report(merged_parent, actor_role=reviewer, severity=3, exposure=4, vulnerability=0.5, estimated_cost=22000, evidence_action="verify")
    review_report(merged_child, actor_role=reviewer, severity=3, exposure=3, vulnerability=0.5)
    merge_reports(merged_child, merged_parent, reviewer)
    review_report(school_pothole, actor_role=reviewer, severity=3, exposure=4, vulnerability=1, estimated_cost=16000, evidence_action="verify", school_access=True)
    review_report(claimed, actor_role=reviewer, severity=4, exposure=3, vulnerability=0.5, estimated_cost=14000, evidence_action="verify")
    review_report(closed, actor_role=reviewer, severity=3, exposure=4, vulnerability=0, estimated_cost=11000, evidence_action="verify")

    # Closed receipt with a full path.
    # Earlier demonstration plan: a real snapshot covering the closed and claimed examples,
    # so their Planned status is backed by a saved plan.
    save_plan(
        25000, {"rain": False, "night": False, "school_hours": False}, reviewer,
        label="Synthetic demonstration plan (earlier round)", is_synthetic=True,
        restrict_ids={closed, claimed},
    )
    db = get_db()
    db.execute("UPDATE reports SET after_photo_filename = ? WHERE id = ?", (p_after, closed))
    db.commit()
    set_repair_status(closed, "repair_claimed", reviewer, "Crew submitted an after-photo of the replaced lamp.")
    close_repair(closed, reviewer)
    add_event(closed, "note", reviewer, "Closed record kept for Repair Receipt history. Synthetic demonstration data.")

    # Claimed but not yet closed, so the receipt workflow can be finished in the demo.
    claim_repair(claimed, "resident", "Surface restored; waiting for reviewer confirmation.", p_after)

    save_plan(
        70000, {"rain": True, "night": False, "school_hours": False}, reviewer,
        label="Synthetic demonstration plan (current round, rain scenario)", is_synthetic=True,
    )

    db = get_db()
    n = db.execute("SELECT COUNT(*) AS c FROM reports").fetchone()[0]
    db.execute(
        "INSERT INTO events (report_id, event_type, actor_role, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (a, "seed", "system", f"Seeded {n} synthetic demonstration reports in Ashoka Ward.", utcnow()),
    )
    db.commit()


def reset_database() -> None:
    db = get_db()
    db.executescript(
        """
        DELETE FROM events;
        DELETE FROM plans;
        DELETE FROM reports;
        """
    )
    db.commit()
    upload = Path(current_app.config["UPLOAD_DIR"])
    if upload.exists():
        for child in upload.iterdir():
            if child.is_file():
                child.unlink()


def seed_if_empty() -> None:
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM reports").fetchone()[0]
    if count == 0:
        seed_all()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed or reset CiviSort demonstration data.")
    parser.add_argument("--reset", action="store_true", help="Wipe reports, events, plans and demo photos, then reseed.")
    args = parser.parse_args(argv)
    from civisort import create_app

    app = create_app()
    with app.app_context():
        if args.reset:
            reset_database()
            seed_all()
            print("Demonstration data reset.")
        else:
            seed_if_empty()
            print("Demonstration data ready.")


if __name__ == "__main__":
    main()
