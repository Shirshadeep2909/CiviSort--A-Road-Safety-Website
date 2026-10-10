"""BudgetMix: conservative unit rounding and 0/1 knapsack planning."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

UNIT_INR = 1000


def ceil_to_unit(amount: int, unit: int = UNIT_INR) -> int:
    if amount <= 0:
        return 0
    return ((amount + unit - 1) // unit) * unit


def floor_to_unit(amount: int, unit: int = UNIT_INR) -> int:
    return (amount // unit) * unit


def unit_cost(amount: int, unit: int = UNIT_INR) -> int:
    return ceil_to_unit(amount, unit) // unit


def plan_better(
    value: float,
    actual_cost: int,
    ids: Sequence[int],
    other_value: float,
    other_cost: int,
    other_ids: Sequence[int],
) -> bool:
    """True if the first plan wins: more points, then lower actual cost, then smaller IDs."""
    value = round(value, 9)
    other_value = round(other_value, 9)
    left_ids = tuple(sorted(ids))
    right_ids = tuple(sorted(other_ids))
    if value != other_value:
        return value > other_value
    if actual_cost != other_cost:
        return actual_cost < other_cost
    return left_ids < right_ids


def knapsack_select(
    items: Sequence[dict[str, Any]],
    budget_inr: int,
) -> dict[str, Any]:
    """
    Maximise sum of priority points within floor(budget/1000) units.
    Each item cost is rounded up to the next INR 1,000 unit.
    Tie-break: higher points, then lower actual total cost, then sorted report IDs.
    """
    capacity = budget_inr // UNIT_INR
    # Capacity beyond the total of all item units adds nothing; keep the table small.
    capacity_cap = min(capacity, sum(unit_cost(int(i["cost"])) for i in items))
    packed: list[dict[str, Any]] = []
    for item in items:
        packed.append(
            {
                "id": int(item["id"]),
                "points": float(item["points"]),
                "cost": int(item["cost"]),
                "units": unit_cost(int(item["cost"])),
            }
        )
    packed.sort(key=lambda x: x["id"])

    # dp[u] = (points, actual_cost, frozenset ids)
    dp: list[tuple[float, int, frozenset[int]] | None] = [None] * (capacity_cap + 1)
    dp[0] = (0.0, 0, frozenset())

    for item in packed:
        u = item["units"]
        if u <= 0 or u > capacity_cap:
            continue
        nxt = dp[:]
        for used in range(capacity_cap - u, -1, -1):
            cur = dp[used]
            if cur is None:
                continue
            new_used = used + u
            cand = (
                cur[0] + item["points"],
                cur[1] + item["cost"],
                cur[2] | {item["id"]},
            )
            prev = nxt[new_used]
            if prev is None or plan_better(
                cand[0], cand[1], sorted(cand[2]), prev[0], prev[1], sorted(prev[2])
            ):
                nxt[new_used] = cand
        dp = nxt

    best: tuple[float, int, frozenset[int]] = (0.0, 0, frozenset())
    for slot in dp:
        if slot is None:
            continue
        if plan_better(slot[0], slot[1], sorted(slot[2]), best[0], best[1], sorted(best[2])):
            best = slot

    selected_ids = set(best[2])
    selected = [item for item in packed if item["id"] in selected_ids]
    selected.sort(key=lambda x: x["id"])
    actual = sum(i["cost"] for i in selected)
    remaining = budget_inr - actual
    return {
        "selected_ids": [i["id"] for i in selected],
        "selected": selected,
        "total_points": best[0],
        "actual_spend": actual,
        "remaining": remaining,
        "budget": budget_inr,
        "usable_budget_units": capacity * UNIT_INR,
        "unit": UNIT_INR,
    }


def greedy_baseline(
    items: Sequence[dict[str, Any]],
    budget_inr: int,
) -> dict[str, Any]:
    """Descending priority, then stable id. Add if unit cost fits remaining units."""
    remaining_units = budget_inr // UNIT_INR
    ordered = sorted(items, key=lambda x: (-float(x["points"]), int(x["id"])))
    selected: list[dict[str, Any]] = []
    for raw in ordered:
        item = {
            "id": int(raw["id"]),
            "points": float(raw["points"]),
            "cost": int(raw["cost"]),
            "units": unit_cost(int(raw["cost"])),
        }
        if item["units"] <= remaining_units and item["units"] > 0:
            selected.append(item)
            remaining_units -= item["units"]
    selected.sort(key=lambda x: x["id"])
    actual = sum(i["cost"] for i in selected)
    return {
        "selected_ids": [i["id"] for i in selected],
        "selected": selected,
        "total_points": sum(i["points"] for i in selected),
        "actual_spend": actual,
        "remaining": budget_inr - actual,
        "budget": budget_inr,
        "usable_budget_units": (budget_inr // UNIT_INR) * UNIT_INR,
        "unit": UNIT_INR,
    }


def exhaustive_best(
    items: Sequence[dict[str, Any]],
    budget_inr: int,
) -> dict[str, Any]:
    """Reference solver for small instances."""
    capacity = budget_inr // UNIT_INR
    n = len(items)
    best: tuple[float, int, tuple[int, ...]] = (0.0, 0, ())
    packed = [
        {
            "id": int(it["id"]),
            "points": float(it["points"]),
            "cost": int(it["cost"]),
            "units": unit_cost(int(it["cost"])),
        }
        for it in items
    ]
    for mask in range(1 << n):
        ids: list[int] = []
        points = 0.0
        cost = 0
        units = 0
        for i, it in enumerate(packed):
            if mask & (1 << i):
                ids.append(it["id"])
                points += it["points"]
                cost += it["cost"]
                units += it["units"]
        if units > capacity:
            continue
        if plan_better(points, cost, ids, best[0], best[1], best[2]):
            best = (points, cost, tuple(sorted(ids)))
    return {
        "selected_ids": list(best[2]),
        "total_points": best[0],
        "actual_spend": best[1],
    }


def exclusion_reason(
    report: dict[str, Any],
    selected_ids: Iterable[int],
) -> str | None:
    rid = int(report["id"])
    if rid in set(selected_ids):
        return None
    if report.get("duplicate_of_id"):
        return "duplicate"
    if report.get("evidence_status") == "unverified":
        return "unverified"
    if report.get("evidence_status") == "disputed":
        return "disputed"
    if report.get("repair_status") == "closed":
        return "resolved"
    if report.get("repair_status") == "repair_claimed":
        return "repair_in_progress"
    if not report.get("estimated_cost"):
        return "missing_cost"
    if report.get("evidence_status") != "verified":
        return "unverified"
    if not report.get("is_primary", True):
        return "duplicate"
    return "not_selected"
