"""P35-APP-CONDUIT-COVERAGE-BADGE: conduit coverage models, mock fallback, router filter, SQL guard.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import sys

import pytest
from fastapi import HTTPException

APP_SRC = os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(APP_SRC))

from resilience_scorecard.backend import router as r  # noqa: E402
from resilience_scorecard.backend.models import (  # noqa: E402
    ConduitCoverageOut,
    ConduitCoverageSummaryOut,
    SpanCoverageClass,
)
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402
from resilience_scorecard.backend.services.mock_data import (  # noqa: E402
    generate_mock_conduit_coverage,
    generate_mock_conduit_coverage_summary,
)


class _Unavailable:
    is_available = False


class _Capture:
    """Fake CatalogSql that records SQL instead of executing it."""
    is_available = True

    def __init__(self):
        self.sql = None

    def _execute(self, sql, row_limit=12000):
        self.sql = sql
        return []


LIVE_CLASSES = {"REAL_SEGMENTED", "BB_SEGMENTED", "INVENTORY_ONLY"}  # conduit_v4 v29 (B2)


def test_enum_covers_live_classes_plus_legacy():
    assert {e.value for e in SpanCoverageClass} == LIVE_CLASSES | {"BB_ONLY"}


def test_mock_rows_validate_against_model():
    rows = generate_mock_conduit_coverage()
    assert rows
    for row in rows:
        ConduitCoverageOut(**row)
    assert {row["span_coverage_class"] for row in rows} == LIVE_CLASSES


def test_unknown_class_does_not_fail_validation():
    """A new DE class must not 500 the API (which would silently fall back to mock)."""
    row = generate_mock_conduit_coverage()[0] | {"span_coverage_class": "FUTURE_CLASS"}
    assert ConduitCoverageOut(**row).span_coverage_class == "FUTURE_CLASS"


def test_mock_summary_matches_live_distribution():
    s = ConduitCoverageSummaryOut(**generate_mock_conduit_coverage_summary())
    counts = {c.span_coverage_class: c.conduit_count for c in s.classes}
    assert counts == {"REAL_SEGMENTED": 55, "BB_SEGMENTED": 92, "INVENTORY_ONLY": 1914}
    assert s.total_conduits == 2061


def test_summary_orders_known_classes_and_keeps_unknown():
    class _Rows(_Capture):
        def _execute(self, sql, row_limit=12000):
            return [
                {"span_coverage_class": "INVENTORY_ONLY", "conduit_count": 3, "length_km": 1, "segmented_km": 0},
                {"span_coverage_class": "ZZ_NEW", "conduit_count": 1, "length_km": 1, "segmented_km": 0},
                {"span_coverage_class": "REAL_SEGMENTED", "conduit_count": 2, "length_km": 1, "segmented_km": 1},
            ]
    s = cs.CatalogSqlService.get_conduit_coverage_summary(_Rows())
    assert [c["span_coverage_class"] for c in s["classes"]] == ["REAL_SEGMENTED", "INVENTORY_ONLY", "ZZ_NEW"]
    assert s["total_conduits"] == 6


def test_router_defaults_to_real_segmented():
    rows = r.list_conduit_coverage(csql=_Unavailable(), coverage_class="REAL_SEGMENTED", region=None)
    assert rows and all(x["span_coverage_class"] == "REAL_SEGMENTED" for x in rows)


def test_router_all_returns_every_class():
    rows = r.list_conduit_coverage(csql=_Unavailable(), coverage_class="all", region=None)
    assert {x["span_coverage_class"] for x in rows} == LIVE_CLASSES


def test_router_rejects_unknown_class():
    with pytest.raises(HTTPException) as exc:
        r.list_conduit_coverage(csql=_Unavailable(), coverage_class="x' OR 1=1 --", region=None)
    assert exc.value.status_code == 422


def test_sql_reads_v4_shadow_and_escapes_region():
    fake = _Capture()
    cs.CatalogSqlService.list_conduit_coverage(fake, coverage_class="BB_SEGMENTED", region="We'st")
    assert "physical_resource_conduit_v4_candidate" in fake.sql
    assert "span_coverage_class = 'BB_SEGMENTED'" in fake.sql
    assert "sa.region = 'We''st'" in fake.sql
    assert "{where}" not in fake.sql


def test_sql_service_rejects_unknown_class():
    with pytest.raises(ValueError):
        cs.CatalogSqlService.list_conduit_coverage(_Capture(), coverage_class="DROP")


def test_branding_in_new_route():
    path = os.path.join(
        APP_SRC, "resilience_scorecard", "ui", "routes", "conduits.tsx",
    )
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "lumen" not in text.lower()
    assert "Lakelink Fiber" in text
