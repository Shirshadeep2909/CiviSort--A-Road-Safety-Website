from civisort.budget import exhaustive_best, greedy_baseline, knapsack_select
from civisort.reports import planning_eligible


def test_abc_optimisation_example():
    items = [
        {"id": 1, "points": 90, "cost": 60_000},
        {"id": 2, "points": 70, "cost": 40_000},
        {"id": 3, "points": 65, "cost": 30_000},
    ]
    mix = knapsack_select(items, 70_000)
    base = greedy_baseline(items, 70_000)
    assert mix["selected_ids"] == [2, 3]
    assert mix["total_points"] == 135
    assert mix["actual_spend"] == 70_000
    assert base["selected_ids"] == [1]
    assert base["total_points"] == 90


def test_budget_units_round_conservatively():
    items = [{"id": 8, "points": 10, "cost": 1001}]
    mix = knapsack_select(items, 1999)
    assert mix["selected_ids"] == []
    mix2 = knapsack_select(items, 2000)
    assert mix2["selected_ids"] == [8]


def test_small_instances_match_exhaustive():
    items = [
        {"id": 10, "points": 12, "cost": 4000},
        {"id": 11, "points": 11, "cost": 4000},
        {"id": 12, "points": 9, "cost": 3000},
        {"id": 13, "points": 8, "cost": 2000},
        {"id": 14, "points": 7, "cost": 2000},
    ]
    for budget in (0, 2000, 5000, 7000, 11000):
        mix = knapsack_select(items, budget)
        brute = exhaustive_best(items, budget)
        assert mix["selected_ids"] == brute["selected_ids"]
        assert mix["total_points"] == brute["total_points"]
        assert mix["actual_spend"] == brute["actual_spend"]


def test_planning_eligibility_rules():
    base = {
        "is_primary": 1,
        "evidence_status": "verified",
        "repair_status": "verified",
        "estimated_cost": 5000,
    }
    assert planning_eligible(base)
    assert not planning_eligible({**base, "evidence_status": "unverified"})
    assert not planning_eligible({**base, "is_primary": 0})
    assert not planning_eligible({**base, "repair_status": "closed"})
    assert not planning_eligible({**base, "repair_status": "repair_claimed"})
    assert not planning_eligible({**base, "estimated_cost": None})
