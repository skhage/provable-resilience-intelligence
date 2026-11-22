"""Shared fixtures for Provable Resilience Intelligence test suite.

Covers: Haversine geospatial, scoring logic, app models, data quality, branding.
Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import math
from decimal import ROUND_HALF_UP, Decimal

import pytest


def sql_round(x: float, ndigits: int = 2) -> float:
    """Spark SQL ROUND on a DOUBLE: HALF_UP on the shortest decimal repr of the double.

    Python's round() uses the exact binary value, so round(34.605, 2) == 34.6 while
    Spark gives 34.61. Callers compute in float (as Spark does for DOUBLE columns) and
    round with this helper; verified 8,000/8,000 vs resilience_score_snapshot.
    """
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-ndigits), rounding=ROUND_HALF_UP))


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
# Composite score reference (mirrors gold_resilience_score V2, BUG-QA-183)
# ---------------------------------------------------------------------------

# SLA boost per tier, as in pipeline Cell 4:
#   CASE s.sla_tier WHEN 'premium_plus' THEN 5.0 WHEN 'premium' THEN 2.0 ELSE 0.0 END
SLA_BOOST = {"premium_plus": 5.0, "premium": 2.0, "standard": 0.0}
SCORE_CAP = 100.0


def composite_score(
    path_diversity: float,
    hazard_exposure: float,
    telemetry_health: float,
    sla_tier: str = "standard",
) -> float:
    """Compute the V2 resilience score: 40/30/30 weighting + SLA boost, capped at 100.

    Mirrors the SQL in resilience_scoring_pipeline Cell 4:
      LEAST(100.0, ROUND(ROUND(0.4*path + 0.3*hazard + 0.3*telemetry, 2) + sla_boost, 2))
    sla_boost = +5 premium_plus, +2 premium, 0 standard (NULL/unknown tier -> standard,
    matching COALESCE(si.sla_tier, 'standard')).
    """
    boost = SLA_BOOST.get(sla_tier or "standard", 0.0)
    base = sql_round(0.4 * path_diversity + 0.3 * hazard_exposure + 0.3 * telemetry_health, 2)
    return min(SCORE_CAP, sql_round(base + boost, 2))


def revenue_at_risk(mrc_usd: float, overall_score: float) -> float:
    """ROUND(mrc_usd * (1 - overall_score / 100.0), 2), using the boosted overall_score."""
    return sql_round(mrc_usd * (1 - overall_score / 100.0), 2)


# ---------------------------------------------------------------------------
# Snapshot fixture: real rows from resilience_score_snapshot (BUG-QA-183)
# ---------------------------------------------------------------------------
# Captured 2026-11-21 by @ml-engineer from
# cdm_tmforum.provable_resilience_intelligence.resilience_score_snapshot JOIN service_inventory
# (sla_tier, mrc_usd). 2 rows per tier x band (cap = boost pushed past 100; low = score < 40;
# mid = other). Full-table check at capture time: boosted formula matched 8,000/8,000 rows,
# plain 40/30/30 matched 2,743 (standard tier only); RaR matched 8,000/8,000.
# Columns: service_id, sla_tier, mrc_usd, path, hazard, telemetry, active_hazards, overall, rar
SNAPSHOT_SAMPLE = [
    ("SVC-00218", "premium", 23563.0, 100.0, 100.00, 99.69, 0, 100.00, 0.00),
    ("SVC-01514", "premium", 2107.0, 100.0, 100.00, 99.89, 0, 100.00, 0.00),
    ("SVC-00016", "premium", 2121.0, 91.3, 0.22, 1.95, 177, 39.17, 1290.20),
    ("SVC-00031", "premium", 3615.0, 65.5, 1.27, 6.90, 126, 30.65, 2507.00),
    ("SVC-00007", "premium", 8571.0, 100.0, 8.84, 90.64, 70, 71.84, 2413.59),
    ("SVC-00008", "premium", 2045.0, 100.0, 2.54, 78.71, 106, 66.38, 687.53),
    ("SVC-00239", "premium_plus", 1945.0, 100.0, 96.59, 98.99, 1, 100.00, 0.00),
    ("SVC-00347", "premium_plus", 9018.0, 100.0, 93.30, 94.51, 2, 100.00, 0.00),
    ("SVC-00003", "premium_plus", 13315.0, 70.4, 1.00, 17.09, 133, 38.59, 8176.74),
    ("SVC-00013", "premium_plus", 13884.0, 84.6, 0.04, 2.51, 224, 39.61, 8384.55),
    ("SVC-00001", "premium_plus", 4407.0, 100.0, 5.63, 33.40, 83, 56.71, 1907.79),
    ("SVC-00005", "premium_plus", 3824.0, 100.0, 2.54, 90.64, 106, 72.95, 1034.39),
    ("SVC-00018", "standard", 3211.0, 76.9, 1.36, 12.76, 124, 35.00, 2087.15),
    ("SVC-00039", "standard", 3655.0, 81.8, 9.47, 11.66, 68, 39.06, 2227.36),
    ("SVC-00002", "standard", 27071.0, 100.0, 7.69, 47.91, 74, 56.68, 11727.16),
    ("SVC-00004", "standard", 19963.0, 75.0, 15.93, 27.47, 53, 43.02, 11374.92),
]


@pytest.fixture
def snapshot_sample():
    """Real resilience_score_snapshot rows (see SNAPSHOT_SAMPLE)."""
    return SNAPSHOT_SAMPLE


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
