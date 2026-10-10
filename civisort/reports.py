"""Report operations, validation, scoring attachment, and workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from civisort.budget import exclusion_reason, greedy_baseline, knapsack_select
from civisort.db import get_db, utcnow
from civisort.neighbourhood import BOUNDS
from civisort.geo import DUPLICATE_RADIUS_M, haversine_m, is_possible_duplicate
from civisort.scoring import VALID_CATEGORIES, VALID_VULNERABILITY, compute_priority

MAX_BUDGET_INR = 1_000_000_000
EVIDENCE_STATUSES = ("unverified", "verified", "disputed")
REPAIR_STATUSES = ("reported", "verified", "planned", "repair_claimed", "closed")

ALLOWED_TRANSITIONS = {
    ("reported", "verified"),
    ("verified", "reported"),  # evidence disputed before planning
    ("verified", "planned"),
    ("planned", "repair_claimed"),
    ("repair_claimed", "closed"),
    # Reopen: a disputed claim or a closed repair returns to Planned (still unresolved).
    ("repair_claimed", "planned"),
    ("closed", "planned"),
}


class ReportError(ValueError):
    pass


def _row(row) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_unresolved(created_at: str, closed_at: str | None, now: datetime | None = None) -> float:
    start = parse_iso(created_at)
    end = parse_iso(closed_at) if closed_at else (now or datetime.now(timezone.utc))
    return max((end - start).total_seconds() / 86400.0, 0.0)


def validate_coords(lat, lng) -> tuple[float, float]:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError) as exc:
        raise ReportError("Coordinates must be numbers.") from exc
    if not -90 <= lat_f <= 90 or not -180 <= lng_f <= 180:
        raise ReportError("Coordinates are out of range.")
    pad = 0.0005
    if not (BOUNDS["min_lat"] - pad <= lat_f <= BOUNDS["max_lat"] + pad
            and BOUNDS["min_lng"] - pad <= lng_f <= BOUNDS["max_lng"] + pad):
        raise ReportError("Location must be inside the Ashoka Ward demonstration area.")
    return lat_f, lng_f


def validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise ReportError("Choose a supported hazard category.")
    return category


def add_event(report_id: int, event_type: str, actor_role: str, detail: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO events (report_id, event_type, actor_role, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (report_id, event_type, actor_role, detail, utcnow()),
    )


def create_report(
    *,
    category: str,
    description: str,
    lat,
    lng,
    photo_filename: str | None,
    school_access: bool = False,
    is_synthetic: bool = False,
    actor_role: str = "resident",
    created_at: str | None = None,
) -> dict[str, Any]:
    category = validate_category(category)
    lat_f, lng_f = validate_coords(lat, lng)
    desc = (description or "").strip()
    if len(desc) < 8:
        raise ReportError("Please describe the hazard in at least 8 characters.")
    if len(desc) > 2000:
        raise ReportError("Descriptions must be 2000 characters or fewer.")
    ts = created_at or utcnow()
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO reports (
            public_code, category, description, lat, lng, photo_filename,
            evidence_status, repair_status, school_access, is_primary,
            is_synthetic, created_at, updated_at
        ) VALUES ('pending', ?, ?, ?, ?, ?, 'unverified', 'reported', ?, 1, ?, ?, ?)
        """,
        (category, desc, lat_f, lng_f, photo_filename, 1 if school_access else 0, 1 if is_synthetic else 0, ts, ts),
    )
    rid = cur.lastrowid
    code = f"R-{rid:03d}"
    db.execute("UPDATE reports SET public_code = ? WHERE id = ?", (code, rid))
    add_event(rid, "reported", actor_role, "Hazard reported. Evidence is unverified.")
    db.commit()
    return get_report(rid)


def get_report(report_id: int) -> dict[str, Any] | None:
    db = get_db()
    return _row(db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone())


def list_reports() -> list[dict[str, Any]]:
    db = get_db()
    return [dict(r) for r in db.execute("SELECT * FROM reports ORDER BY id").fetchall()]


def list_events(report_id: int) -> list[dict[str, Any]]:
    db = get_db()
    return [
        dict(r)
        for r in db.execute(
            "SELECT * FROM events WHERE report_id = ? ORDER BY id", (report_id,)
        ).fetchall()
    ]


def possible_duplicates_for(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for other in list_reports():
        if other["id"] == report["id"]:
            continue
        if not is_possible_duplicate(
            report["lat"],
            report["lng"],
            other["lat"],
            other["lng"],
            report["category"],
            other["category"],
        ):
            continue
        dist = haversine_m(report["lat"], report["lng"], other["lat"], other["lng"])
        item = dict(other)
        item["distance_m"] = round(dist, 1)
        out.append(item)
    return out


def merge_reports(child_id: int, primary_id: int, actor_role: str) -> dict[str, Any]:
    if actor_role != "reviewer":
        raise ReportError("Only the reviewer demo role can confirm a merge.")
    child = get_report(child_id)
    primary = get_report(primary_id)
    if not child or not primary:
        raise ReportError("Both reports must exist.")
    if child_id == primary_id:
        raise ReportError("A report cannot be merged into itself.")
    if not is_possible_duplicate(
        child["lat"], child["lng"], primary["lat"], primary["lng"], child["category"], primary["category"]
    ):
        raise ReportError("Reports must be the same category and within 50 metres.")
    if not primary["is_primary"]:
        raise ReportError("The chosen primary is itself a linked duplicate.")
    if not child["is_primary"]:
        raise ReportError("That report is already linked to a primary report.")
    db = get_db()
    now = utcnow()
    db.execute(
        "UPDATE reports SET is_primary = 0, primary_report_id = ?, updated_at = ? WHERE id = ?",
        (primary_id, now, child_id),
    )
    # Any duplicates already linked to the child follow it to the new primary.
    db.execute("UPDATE reports SET primary_report_id = ?, updated_at = ? WHERE primary_report_id = ?",
               (primary_id, now, child_id))
    add_event(child_id, "merged", actor_role, f"Linked as duplicate of {primary['public_code']}. Original evidence kept.")
    add_event(primary_id, "merge_received", actor_role, f"Linked duplicate {child['public_code']}. Severity was not increased.")
    db.commit()
    return get_report(child_id)


def _require_reviewer(actor_role: str) -> None:
    if actor_role != "reviewer":
        raise ReportError("Switch to Reviewer demo mode to perform this action.")


def review_report(
    report_id: int,
    *,
    actor_role: str,
    severity: int | None = None,
    exposure: int | None = None,
    vulnerability: float | None = None,
    school_access: bool | None = None,
    estimated_cost: int | None = None,
    evidence_action: str | None = None,
) -> dict[str, Any]:
    _require_reviewer(actor_role)
    report = get_report(report_id)
    if not report:
        raise ReportError("Report not found.")

    updates: dict[str, Any] = {}
    if severity is not None:
        if severity not in (1, 2, 3, 4, 5):
            raise ReportError("Severity must be an integer from 1 to 5.")
        updates["severity"] = severity
    if exposure is not None:
        if exposure not in (1, 2, 3, 4, 5):
            raise ReportError("Exposure must be an integer from 1 to 5.")
        updates["exposure"] = exposure
    if vulnerability is not None:
        if float(vulnerability) not in VALID_VULNERABILITY:
            raise ReportError("Vulnerable-user context must be 0, 0.5 or 1.")
        updates["vulnerability"] = float(vulnerability)
    if school_access is not None:
        updates["school_access"] = 1 if school_access else 0
    if estimated_cost is not None:
        if int(estimated_cost) <= 0:
            raise ReportError("Estimated repair cost must be a positive amount in INR.")
        updates["estimated_cost"] = int(estimated_cost)

    notes = []
    if evidence_action in ("verify", "dispute"):
        if not report["is_primary"]:
            raise ReportError("This report is a linked duplicate. Review its primary report.")
        if report["repair_status"] not in ("reported", "verified"):
            raise ReportError("Evidence can only change before a repair is planned. Reopen the repair first.")
    if evidence_action == "verify":
        updates["evidence_status"] = "verified"
        if report["repair_status"] == "reported":
            _apply_transition(report, "verified")
            updates["repair_status"] = "verified"
        notes.append("Evidence verified.")
    elif evidence_action == "dispute":
        updates["evidence_status"] = "disputed"
        if report["repair_status"] == "verified":
            _apply_transition(report, "reported")
            updates["repair_status"] = "reported"
        notes.append("Evidence disputed. The report stays visible for follow-up.")
    elif evidence_action not in (None, ""):
        raise ReportError("Unknown evidence action.")
    changed = [k for k in ("severity", "exposure", "vulnerability", "school_access", "estimated_cost")
               if k in updates and updates[k] != report[k]]
    if changed:
        notes.append("Assessment changed: " + ", ".join(changed) + ".")

    if not updates:
        raise ReportError("No review fields were provided.")

    updates["updated_at"] = utcnow()
    assignments = ", ".join(f"{k} = ?" for k in updates)
    db = get_db()
    db.execute(
        f"UPDATE reports SET {assignments} WHERE id = ?",
        (*updates.values(), report_id),
    )
    add_event(report_id, "reviewed", actor_role, " ".join(notes) if notes else "Reviewer fields updated.")
    db.commit()
    return get_report(report_id)


def _apply_transition(report: dict[str, Any], new_status: str) -> None:
    current = report["repair_status"]
    if (current, new_status) not in ALLOWED_TRANSITIONS:
        raise ReportError(f"Cannot change repair status from {current} to {new_status}.")


def set_repair_status(report_id: int, new_status: str, actor_role: str, detail: str) -> dict[str, Any]:
    report = get_report(report_id)
    if not report:
        raise ReportError("Report not found.")
    _apply_transition(report, new_status)
    db = get_db()
    closed_at = utcnow() if new_status == "closed" else None
    if new_status != "closed":
        db.execute(
            "UPDATE reports SET repair_status = ?, closed_at = NULL, updated_at = ? WHERE id = ?",
            (new_status, utcnow(), report_id),
        )
    else:
        db.execute(
            "UPDATE reports SET repair_status = ?, closed_at = ?, updated_at = ? WHERE id = ?",
            (new_status, closed_at, utcnow(), report_id),
        )
    add_event(report_id, new_status, actor_role, detail)
    db.commit()
    return get_report(report_id)


def claim_repair(report_id: int, actor_role: str, note: str, after_filename: str | None) -> dict[str, Any]:
    report = get_report(report_id)
    if not report:
        raise ReportError("Report not found.")
    if report["repair_status"] != "planned":
        raise ReportError("A repair can be claimed only after it is included in a saved plan.")
    note = (note or "").strip()
    if not after_filename and len(note) < 8:
        raise ReportError("Add an after-photo or a completion note of at least 8 characters.")
    detail = "Repair claimed."
    db = get_db()
    if after_filename:
        db.execute(
            "UPDATE reports SET after_photo_filename = ?, updated_at = ? WHERE id = ?",
            (after_filename, utcnow(), report_id),
        )
        detail += " After-photo attached."
    if note:
        detail += f" Note: {note}"
    db.commit()
    return set_repair_status(report_id, "repair_claimed", actor_role, detail)


def close_repair(report_id: int, actor_role: str) -> dict[str, Any]:
    _require_reviewer(actor_role)
    report = get_report(report_id)
    if not report:
        raise ReportError("Report not found.")
    if report["repair_status"] != "repair_claimed":
        raise ReportError("Close a repair only after a completion claim.")
    return set_repair_status(report_id, "closed", actor_role, "Reviewer confirmed closure. Left the active repair queue.")


def reopen_repair(report_id: int, actor_role: str, reason: str) -> dict[str, Any]:
    _require_reviewer(actor_role)
    reason = (reason or "").strip()
    if len(reason) < 8:
        raise ReportError("Record a reason of at least 8 characters to reopen.")
    report = get_report(report_id)
    if not report:
        raise ReportError("Report not found.")
    if report["repair_status"] not in ("repair_claimed", "closed"):
        raise ReportError("Only a claimed or closed repair can be reopened.")
    return set_repair_status(report_id, "planned", actor_role, f"Reopened and returned to Planned: {reason}")


def attach_score(report: dict[str, Any], scenarios: dict[str, bool], now=None) -> dict[str, Any]:
    days = days_unresolved(report["created_at"], report["closed_at"], now)
    breakdown = compute_priority(
        severity=report["severity"],
        exposure=report["exposure"],
        vulnerability=report["vulnerability"],
        category=report["category"],
        school_access=bool(report["school_access"]),
        days_unresolved=days,
        rain=scenarios.get("rain", False),
        night=scenarios.get("night", False),
        school_hours=scenarios.get("school_hours", False),
    )
    item = dict(report)
    item["days_unresolved"] = days
    item["duplicate_of_id"] = report["primary_report_id"] if not report["is_primary"] else None
    item["score"] = breakdown.as_dict()
    item["inspect_flag"] = (
        report["evidence_status"] == "unverified"
        and report["is_primary"]
        and breakdown.total >= 70
    )
    return item


def ranked_reports(scenarios: dict[str, bool], filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Active ranked hazards: primary reports only. Duplicate children are nested as linked history."""
    filters = filters or {}
    everything = [attach_score(r, scenarios) for r in list_reports()]
    children: dict[int, list[dict[str, Any]]] = {}
    for item in everything:
        if not item["is_primary"] and item["primary_report_id"]:
            children.setdefault(item["primary_report_id"], []).append(item)
    ranked = []
    for item in everything:
        if not item["is_primary"]:
            continue
        if filters.get("category") and item["category"] != filters["category"]:
            continue
        if filters.get("evidence_status") and item["evidence_status"] != filters["evidence_status"]:
            continue
        repair = filters.get("repair_status")
        if repair == "active" and item["repair_status"] == "closed":
            continue
        if repair and repair not in ("active", "all") and item["repair_status"] != repair:
            continue
        item["linked_duplicates"] = [
            {k: c[k] for k in ("id", "public_code", "category", "evidence_status", "photo_filename", "created_at")}
            for c in sorted(children.get(item["id"], []), key=lambda c: c["id"])
        ]
        ranked.append(item)
    ranked.sort(key=lambda r: (-r["score"]["total"], r["id"]))
    return ranked


def planning_eligible(report: dict[str, Any]) -> bool:
    return (
        bool(report["is_primary"])
        and report["evidence_status"] == "verified"
        and report["repair_status"] in ("verified", "planned")
        and report["estimated_cost"] is not None
        and int(report["estimated_cost"]) > 0
    )


def suggest_plan(budget: int, scenarios: dict[str, bool], restrict_ids: set[int] | None = None) -> dict[str, Any]:
    if budget < 0 or budget > MAX_BUDGET_INR:
        raise ReportError(f"Budget must be between 0 and INR {MAX_BUDGET_INR:,}.")
    scored = [attach_score(r, scenarios) for r in list_reports()]
    eligible = [r for r in scored if planning_eligible(r) and (restrict_ids is None or r['id'] in restrict_ids)]
    items = [{"id": r["id"], "points": r["score"]["total"], "cost": int(r["estimated_cost"])} for r in eligible]
    mix = knapsack_select(items, budget)
    base = greedy_baseline(items, budget)
    by_id = {r["id"]: r for r in scored}
    def hydrate(result):
        selected = []
        for sid in result["selected_ids"]:
            r = by_id[sid]
            selected.append(
                {
                    "id": r["id"],
                    "public_code": r["public_code"],
                    "category": r["category"],
                    "points": r["score"]["total"],
                    "cost": r["estimated_cost"],
                    "score": r["score"],
                }
            )
        out = dict(result)
        out["selected"] = selected
        return out

    mix_h = hydrate(mix)
    base_h = hydrate(base)
    excluded = []
    for r in scored:
        reason = exclusion_reason(
            {
                **r,
                "duplicate_of_id": r["duplicate_of_id"],
                "estimated_cost": r["estimated_cost"],
            },
            mix["selected_ids"],
        )
        if reason:
            excluded.append(
                {
                    "id": r["id"],
                    "public_code": r["public_code"],
                    "reason": reason,
                    "is_primary": r["is_primary"],
                    "evidence_status": r["evidence_status"],
                    "repair_status": r["repair_status"],
                }
            )
    return {
        "rounding": (
            f"Costs round up to the next INR {mix['unit']:,} unit. "
            f"The usable budget rounds down to INR {mix['usable_budget_units']:,}."
        ),
        "budgetmix": mix_h,
        "baseline": base_h,
        "eligible_count": len(eligible),
        "excluded": excluded,
        "scenarios": scenarios,
        "note": "A suggested bundle is not a committed plan until a reviewer saves it.",
    }


def save_plan(
    budget: int,
    scenarios: dict[str, bool],
    actor_role: str,
    *,
    label: str | None = None,
    is_synthetic: bool = False,
    restrict_ids: set[int] | None = None,
) -> dict[str, Any]:
    _require_reviewer(actor_role)
    suggestion = suggest_plan(budget, scenarios, restrict_ids)
    payload = json.dumps(
        {
            "selected": suggestion["budgetmix"]["selected"],
            "baseline": suggestion["baseline"],
            "rounding": suggestion["rounding"],
            "excluded": suggestion["excluded"],
            "budget": budget,
            "scenarios": scenarios,
            "eligible_count": suggestion["eligible_count"],
        }
    )
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO plans (budget, rain, night, school_hours, selected_json, total_points, actual_spend, remaining, created_at, label, is_synthetic)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            budget,
            1 if scenarios.get("rain") else 0,
            1 if scenarios.get("night") else 0,
            1 if scenarios.get("school_hours") else 0,
            payload,
            suggestion["budgetmix"]["total_points"],
            suggestion["budgetmix"]["actual_spend"],
            suggestion["budgetmix"]["remaining"],
            utcnow(),
            label,
            1 if is_synthetic else 0,
        ),
    )
    plan_id = cur.lastrowid
    for item in suggestion["budgetmix"]["selected"]:
        report = get_report(item["id"])
        if report and report["repair_status"] == "verified":
            _apply_transition(report, "planned")
            db.execute(
                "UPDATE reports SET repair_status = ?, updated_at = ? WHERE id = ?",
                ("planned", utcnow(), item["id"]),
            )
            add_event(item["id"], "planned", actor_role, f"Included in saved plan #{plan_id}.")
    db.commit()
    return get_plan(plan_id)


def get_plan(plan_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = _row(db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone())
    if not row:
        return None
    row["snapshot"] = json.loads(row["selected_json"])
    return row


def list_plans() -> list[dict[str, Any]]:
    db = get_db()
    plans = []
    for row in db.execute("SELECT * FROM plans ORDER BY id DESC").fetchall():
        item = dict(row)
        item["snapshot"] = json.loads(item["selected_json"])
        plans.append(item)
    return plans
