"""BUG-DW-164 regression tests: /hazards crosswalk tfoot 'Spans' must be a true
COUNT(DISTINCT span_id) over the filter scope, never a sum of per-bucket distinct counts.

Acceptance (from @designer S115, P172):
  * 'All Hazard Types' tfoot Spans == summary distinct_spans_exposed and <= total_spans.
  * A single type matches COUNT(DISTINCT) for that type.
  * A unit test with overlapping spans across bands proves the value is not a sum.
  * Tests fail on 22ed333 (no totals endpoint/SQL; tfoot used rows.reduce on distinct_spans).
"""
import pathlib
import re
import sqlite3

import pytest

from resilience_scorecard.backend.services import catalog_sql, mock_data

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_TSX = _ROOT / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui/components/hazards/"
    "hazard-crosswalk-table.tsx"
)
_ROUTER = _ROOT / "apps/resilience-scorecard/src/resilience_scorecard/backend/router.py"


# ---------- SQL semantics on overlapping spans (sqlite stand-in) -------------


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE hazard_span_intersection (span_id TEXT, hazard_type TEXT, "
        "proximity_band TEXT, is_within_radius BOOLEAN)"
    )
    rows = [
        # S1 sits in 3 buckets, S2 in 2 buckets, S3 in 1; S4 is out of radius only.
        ("S1", "wildfire", "direct_impact", 1),
        ("S1", "wildfire", "buffer_zone", 1),
        ("S1", "flood", "near_field", 1),
        ("S2", "wildfire", "near_field", 1),
        ("S2", "flood", "near_field", 1),
        ("S3", "flood", "buffer_zone", 1),
        ("S4", "flood", "buffer_zone", 0),
    ]
    con.executemany("INSERT INTO hazard_span_intersection VALUES (?,?,?,?)", rows)
    yield con
    con.close()


def _bucket_sum(con, hazard_type=None):
    where = "WHERE is_within_radius = TRUE" + (" AND hazard_type = :h" if hazard_type else "")
    q = (
        "SELECT SUM(d) FROM (SELECT COUNT(DISTINCT span_id) AS d FROM hazard_span_intersection "
        f"{where} GROUP BY hazard_type, proximity_band)"
    )
    return con.execute(q, {"h": hazard_type}).fetchone()[0]


def _service(con):
    svc = object.__new__(catalog_sql.CatalogSqlService)

    def _execute(sql, params=None):
        cur = con.execute(sql, params or {})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    svc._execute = _execute
    return svc


def test_all_types_total_is_distinct_not_sum(db):
    t = _service(db).get_crosswalk_totals()
    assert t["distinct_spans"] == 3  # S1, S2, S3
    assert _bucket_sum(db) == 6  # the old tfoot value: 3x S1 + 2x S2 + 1x S3
    assert t["distinct_spans"] != _bucket_sum(db)
    assert t["intersection_count"] == 6  # COUNT(*) stays additive, S4 excluded


def test_single_type_total_is_distinct_not_sum(db):
    t = _service(db).get_crosswalk_totals(hazard_type="wildfire")
    assert t == {"hazard_type": "wildfire", "intersection_count": 3, "distinct_spans": 2}
    assert _bucket_sum(db, "wildfire") == 3


def test_out_of_radius_excluded(db):
    t = _service(db).get_crosswalk_totals(hazard_type="flood")
    assert t["distinct_spans"] == 3  # S1, S2, S3; S4 is is_within_radius = FALSE
    assert t["intersection_count"] == 3


def test_totals_sql_uses_count_distinct_and_bound_param():
    sql = catalog_sql._CROSSWALK_TOTALS_SQL
    assert "COUNT(DISTINCT span_id)" in sql
    assert "is_within_radius = TRUE" in sql
    assert "GROUP BY" not in sql
    src = pathlib.Path(catalog_sql.__file__).read_text(encoding="utf-8")
    body = src[src.index("def get_crosswalk_totals"):src.index("def get_crosswalk_summary")]
    assert ":hazard_type" in body and "f\"" not in body  # no string interpolation


# ---------- mock data follows the same rule ---------------------------------


def test_mock_all_types_matches_summary_kpi():
    t = mock_data.generate_mock_crosswalk_totals()
    s = mock_data.generate_mock_crosswalk_summary()
    rows = mock_data.generate_mock_crosswalk()
    assert t["distinct_spans"] == s["distinct_spans_exposed"] == 10085
    assert t["distinct_spans"] <= s["total_spans"]
    assert t["intersection_count"] == s["total_intersections"] == sum(r["intersection_count"] for r in rows)
    assert sum(r["distinct_spans"] for r in rows) > s["total_spans"]  # proves summing is wrong


def test_mock_wildfire_true_distinct():
    t = mock_data.generate_mock_crosswalk_totals("wildfire")
    assert t["distinct_spans"] == 7624
    rows = [r for r in mock_data.generate_mock_crosswalk() if r["hazard_type"] == "wildfire"]
    assert sum(r["distinct_spans"] for r in rows) == 7908  # the reported wrong value
    for r in rows:
        assert t["distinct_spans"] >= r["distinct_spans"]


def test_mock_unknown_type_is_zero():
    assert mock_data.generate_mock_crosswalk_totals("nope")["distinct_spans"] == 0


# ---------- route + UI wiring -------------------------------------------------


def test_router_exposes_totals_endpoint():
    src = _ROUTER.read_text(encoding="utf-8")
    assert '"/hazards/crosswalk/totals"' in src
    assert "get_crosswalk_totals" in src and "generate_mock_crosswalk_totals" in src


def test_tsx_does_not_sum_distinct_spans():
    src = _TSX.read_text(encoding="utf-8")
    assert not re.search(r"reduce\([^)]*\)\s*=>\s*s\s*\+\s*r\.distinct_spans", src)
    assert "r.distinct_spans, 0" not in src
    assert "/api/hazards/crosswalk/totals" in src


def test_tsx_em_dash_fallback_with_sr_note():
    src = _TSX.read_text(encoding="utf-8")
    assert '<span aria-hidden="true">\u2014</span>' in src
    assert "not additive" in src


def test_no_lumen_in_changed_files():
    for p in (_TSX, _ROUTER, pathlib.Path(catalog_sql.__file__), pathlib.Path(mock_data.__file__)):
        assert "lumen" not in p.read_text(encoding="utf-8").lower(), p
