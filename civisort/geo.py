"""Haversine distance helpers for duplicate detection."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6371000.0
DUPLICATE_RADIUS_M = 50.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_possible_duplicate(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    category1: str,
    category2: str,
    radius_m: float = DUPLICATE_RADIUS_M,
) -> bool:
    if category1 != category2:
        return False
    return haversine_m(lat1, lon1, lat2, lon2) <= radius_m
