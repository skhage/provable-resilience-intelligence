"""Lakelink Fiber - governed resilience risk levels (P363, V4-KPI-COPY-SPEC §8.4).

Fallback copy of the GOVERNED_RISK_LEVEL rows in
cdm_tmforum.provable_resilience_intelligence.risk_band_vocabulary. The live API reads the
cuts from that table (catalog_sql._RISK_LEVEL_CUTS_SQL); these constants are used only by
mock data and when the vocabulary query is unavailable. Order is worst to best.
"""

from __future__ import annotations

import math

GOVERNED_RISK_CUTS: tuple[dict, ...] = (
    {"level": "critical", "score_min_inclusive": 0.0, "score_max_exclusive": 40.0},
    {"level": "at_risk", "score_min_inclusive": 40.0, "score_max_exclusive": 60.0},
    {"level": "moderate", "score_min_inclusive": 60.0, "score_max_exclusive": 80.0},
    {"level": "healthy", "score_min_inclusive": 80.0, "score_max_exclusive": 100.01},
)


def governed_risk_level(score: float | None) -> str:
    """Governed level for a 0-100 overall score. None/NaN is treated as critical."""
    if score is None or not math.isfinite(score):
        return "critical"
    for band in reversed(GOVERNED_RISK_CUTS):
        if score >= band["score_min_inclusive"]:
            return band["level"]
    return "critical"
