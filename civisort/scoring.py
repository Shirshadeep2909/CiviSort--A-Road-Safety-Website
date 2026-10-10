"""Explainable priority scoring. Weights are prototype planning assumptions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

WEIGHT_SEVERITY = 35.0
WEIGHT_EXPOSURE = 25.0
WEIGHT_VULNERABILITY = 20.0
WEIGHT_CONDITIONS = 15.0
WEIGHT_AGE = 5.0

RAIN_CATEGORIES = frozenset({"pothole", "drainage"})
NIGHT_CATEGORIES = frozenset({"streetlight"})

VALID_CATEGORIES = ("pothole", "drainage", "streetlight", "crossing")
VALID_VULNERABILITY = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    severity_points: float
    exposure_points: float
    vulnerability_points: float
    conditions_points: float
    age_points: float
    severity_input: float | None
    exposure_input: float | None
    vulnerability_input: float | None
    conditions_applied: bool
    applicable_scenarios: tuple[str, ...]
    days_unresolved: float
    age_ratio: float
    caveat: str = (
        "Weights are prototype planning assumptions. Scores are not measured accident risk."
    )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_display"] = f"{self.total:.1f}"
        data["severity_display"] = f"{self.severity_points:.1f}"
        data["exposure_display"] = f"{self.exposure_points:.1f}"
        data["vulnerability_display"] = f"{self.vulnerability_points:.1f}"
        data["conditions_display"] = f"{self.conditions_points:.1f}"
        data["age_display"] = f"{self.age_points:.1f}"
        return data


def scenario_applies(
    category: str,
    school_access: bool,
    rain: bool,
    night: bool,
    school_hours: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Return whether C=1 and which named scenarios apply. Multiple matches do not stack."""
    applicable: list[str] = []
    if rain and category in RAIN_CATEGORIES:
        applicable.append("rain")
    if night and category in NIGHT_CATEGORIES:
        applicable.append("night")
    if school_hours and school_access:
        applicable.append("school_hours")
    return (len(applicable) > 0, tuple(applicable))


def compute_priority(
    *,
    severity: float | None,
    exposure: float | None,
    vulnerability: float | None,
    category: str,
    school_access: bool,
    days_unresolved: float,
    rain: bool = False,
    night: bool = False,
    school_hours: bool = False,
) -> ScoreBreakdown:
    """
    Priority = 35S + 25E + 20V + 15C + 5A
    S = severity/5, E = exposure/5, V in {0, 0.5, 1},
    C = 1 if any active scenario applies else 0,
    A = min(days unresolved / 30, 1).
    Missing reviewer inputs contribute 0.
    """
    s_in = float(severity) if severity is not None else 0.0
    e_in = float(exposure) if exposure is not None else 0.0
    v_in = float(vulnerability) if vulnerability is not None else 0.0

    s = s_in / 5.0
    e = e_in / 5.0
    v = v_in
    applies, names = scenario_applies(category, school_access, rain, night, school_hours)
    c = 1.0 if applies else 0.0
    age_ratio = min(max(float(days_unresolved), 0.0) / 30.0, 1.0)

    severity_points = WEIGHT_SEVERITY * s
    exposure_points = WEIGHT_EXPOSURE * e
    vulnerability_points = WEIGHT_VULNERABILITY * v
    conditions_points = WEIGHT_CONDITIONS * c
    age_points = WEIGHT_AGE * age_ratio
    total = (
        severity_points
        + exposure_points
        + vulnerability_points
        + conditions_points
        + age_points
    )
    return ScoreBreakdown(
        total=total,
        severity_points=severity_points,
        exposure_points=exposure_points,
        vulnerability_points=vulnerability_points,
        conditions_points=conditions_points,
        age_points=age_points,
        severity_input=severity,
        exposure_input=exposure,
        vulnerability_input=vulnerability,
        conditions_applied=applies,
        applicable_scenarios=names,
        days_unresolved=float(days_unresolved),
        age_ratio=age_ratio,
    )
