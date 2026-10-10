from civisort.scoring import compute_priority, scenario_applies


def test_worked_example_eighty_points():
    result = compute_priority(
        severity=4,
        exposure=3,
        vulnerability=1,
        category="pothole",
        school_access=True,
        days_unresolved=12,
        rain=True,
        night=False,
        school_hours=False,
    )
    assert result.severity_points == 28
    assert result.exposure_points == 15
    assert result.vulnerability_points == 20
    assert result.conditions_points == 15
    assert result.age_points == 2
    assert result.total == 80


def test_rain_and_night_and_school_do_not_stack():
    applies, names = scenario_applies(
        "pothole", school_access=True, rain=True, night=True, school_hours=True
    )
    assert applies is True
    assert names == ("rain", "school_hours")
    result = compute_priority(
        severity=5,
        exposure=5,
        vulnerability=1,
        category="pothole",
        school_access=True,
        days_unresolved=30,
        rain=True,
        night=True,
        school_hours=True,
    )
    assert result.conditions_points == 15
    assert result.total == 100


def test_night_only_for_streetlights():
    pothole = compute_priority(
        severity=5, exposure=5, vulnerability=0, category="pothole",
        school_access=False, days_unresolved=0, night=True,
    )
    light = compute_priority(
        severity=5, exposure=5, vulnerability=0, category="streetlight",
        school_access=False, days_unresolved=0, night=True,
    )
    assert pothole.conditions_points == 0
    assert light.conditions_points == 15


def test_school_hours_requires_tag():
    tagged = compute_priority(
        severity=1, exposure=1, vulnerability=0, category="crossing",
        school_access=True, days_unresolved=0, school_hours=True,
    )
    untagged = compute_priority(
        severity=1, exposure=1, vulnerability=0, category="crossing",
        school_access=False, days_unresolved=0, school_hours=True,
    )
    assert tagged.conditions_applied is True
    assert untagged.conditions_applied is False
