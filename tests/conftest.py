"""Shared fixtures for Provable Resilience Intelligence test suite.

Covers: Haversine geospatial, scoring logic, app models, data quality, branding.
Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import math
import pytest


# ---------------------------------------------------------------------------
# Haversine reference implementation (pure Python, for unit-test validation)
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km using the Haversine formula.

    Mirrors the SQL implementation in resilience_scoring_pipeline Cell 2.
    Earth radius = 6371 km (same constant as pipeline).
    """
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Composite score reference (mirrors gold_resilience_score weights)
# ---------------------------------------------------------------------------

def composite_score(
    path_diversity: float,
    hazard_exposure: float,
    telemetry_health: float,
) -> float:
    """Compute resilience score using 40/30/30 weighting.

    Mirrors the SQL in resilience_scoring_pipeline Cell 4.
    """
    return round(path_diversity * 0.40 + hazard_exposure * 0.30 + telemetry_health * 0.30, 1)


# ---------------------------------------------------------------------------
# Known geographic reference points (for haversine validation)
# ---------------------------------------------------------------------------

@pytest.fixture
def known_distances():
    """Known city-pair great-circle distances for haversine validation."""
    return [
        # (lat1, lon1, lat2, lon2, expected_km, tolerance_km, label)
        (40.7128, -74.0060, 34.0522, -118.2437, 3944, 10, "NYC→LA"),
        (40.7128, -74.0060, 41.8781, -87.6298, 1146, 5, "NYC→Chicago"),
        (51.5074, -0.1278, 48.8566, 2.3522, 344, 3, "London→Paris"),
        (0.0, 0.0, 0.0, 0.0, 0, 0.001, "Same point"),
        (90.0, 0.0, -90.0, 0.0, 20015, 20, "North→South pole"),
    ]


# ---------------------------------------------------------------------------
# Score boundary fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def score_boundary_cases():
    """Edge cases for composite score computation."""
    return [
        # (div, haz, tel, expected)
        (100, 100, 100, 100.0),   # Perfect
        (0, 0, 0, 0.0),           # Worst
        (100, 0, 0, 40.0),        # Only diversity
        (0, 100, 0, 30.0),        # Only hazard
        (0, 0, 100, 30.0),        # Only telemetry
        (50, 50, 50, 50.0),       # Midpoint
    ]


# ---------------------------------------------------------------------------
# SLA tier reference
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_sla_tiers():
    """Valid SLA tier values per data model spec."""
    return {"standard", "premium", "premium_plus"}


# ---------------------------------------------------------------------------
# Branding constants
# ---------------------------------------------------------------------------

@pytest.fixture
def branding_forbidden_terms():
    """Terms that must NOT appear in produced assets (per CEO directive)."""
    return ["Lumen Technologies", "Lumen Enterprise"]


@pytest.fixture
def branding_allowed_references():
    """Contexts where 'Lumen' may appear (meta-docs explaining the rule)."""
    return [
        ".assistant_instructions.md",
        "BRAND-GUIDE.md",
        "UX-DESIGN-SPEC.md",
        "CONTRIBUTING.md",
    ]
