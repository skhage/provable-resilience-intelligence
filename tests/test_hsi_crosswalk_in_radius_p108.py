"""P108-APP-HSI-CROSSWALK-IN-RADIUS (BUG-QA-129 ruling, @data-planner P91).

proximity_band is a distance band that is orthogonal to the hazard radius. Impact and exposure
semantics come ONLY from is_within_radius = TRUE. The /hazards crosswalk used to count every
hazard_span_intersection row (live v3: total 173,323, direct_impact 1,502). In-radius it is
total 83,029 and direct_impact 600.

Known answer: the real SQL constants run on a SQLite fixture with rows both inside and outside
the radius in every band. The expected values are computed independently in Python.
Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import os
import random
import re
import sqlite3
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
if APP not in sys.path:
    sys.path.insert(0, APP)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402
from resilience_scorecard.backend.services import mock_data as md  # noqa: E402

UI = os.path.join(APP, "resilience_scorecard", "ui")
TABLE_TSX = os.path.join(UI, "components", "hazards", "hazard-crosswalk-table.tsx")
MODELS_PY = os.path.join(APP, "resilience_scorecard", "backend", "models.py")

BANDS = ("direct_impact", "near_field", "buffer_zone")
TYPES = ("severe_weather", "earthquake", "flood", "wildfire", "dig_ticket")


def _rows(seed=7, n=600):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        band = rnd.choice(BANDS)
        dist = {"direct_impact": rnd.uniform(0, 1), "near_field": rnd.uniform(1, 5),
                "buffer_zone": rnd.uniform(5, 900)}[band]
        out.append((rnd.choice(TYPES), band, f"SPAN-{rnd.randint(1, 120):05d}", dist,
                    rnd.randint(1, 500), rnd.random() < 0.45))
    return out


def _db(rows, spans=150):
    db = sqlite3.connect(":memory:")
    db.executescript(
        "CREATE TABLE hazard_span_intersection (hazard_type TEXT, proximity_band TEXT, span_id TEXT,"
        " distance_km REAL, affected_service_cnt INT, is_within_radius INT);"
        "CREATE TABLE physical_resource_span (span_id TEXT);"
    )
    db.executemany("INSERT INTO hazard_span_intersection VALUES (?,?,?,?,?,?)",
                   [(t, b, s, d, a, int(w)) for t, b, s, d, a, w in rows])
    db.executemany("INSERT INTO physical_resource_span VALUES (?)", [(f"SPAN-{i:05d}",) for i in range(spans)])
    db.row_factory = sqlite3.Row
    return db


def _run(db, sql, **params):
    return [dict(r) for r in db.execute(sql.replace("TRUE", "1"), params).fetchall()]


def _expected(rows, hazard_type=None):
    keep = [r for r in rows if r[5] and (hazard_type is None or r[0] == hazard_type)]
    agg = {}
    for t, b, s, _d, _a, _w in keep:
        k = agg.setdefault((t, b), [0, set()])
        k[0] += 1
        k[1].add(s)
    return keep, {k: (v[0], len(v[1])) for k, v in agg.items()}


# --- SQL text -----------------------------------------------------------------

def test_crosswalk_sql_constants_filter_in_radius():
    for sql in (cs._CROSSWALK_SQL, cs._CROSSWALK_SUMMARY_SQL):
        assert re.search(r"WHERE\s+is_within_radius\s*=\s*TRUE", sql), sql


class _Capture:
    is_available = True

    def __init__(self, ret=None):
        self.calls = []
        self.ret = ret if ret is not None else []

    def _execute(self, sql, row_limit=12000, params=None):
        self.calls.append((sql, params))
        return self.ret


def test_hazard_type_branch_filters_in_radius_and_binds_param():
    fake = _Capture()
    cs.CatalogSqlService.get_crosswalk(fake, hazard_type="flood")
    sql, params = fake.calls[0]
    assert re.search(r"is_within_radius\s*=\s*TRUE\s+AND\s+hazard_type\s*=\s*:hazard_type", sql)
    assert params == {"hazard_type": "flood"}


# --- SQLite known answer --------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 7, 42])
def test_crosswalk_known_answer_excludes_outside_radius(seed):
    rows = _rows(seed)
    db = _db(rows)
    _, exp = _expected(rows)
    got = {(r["hazard_type"], r["proximity_band"]): (r["intersection_count"], r["distinct_spans"])
           for r in _run(db, cs._CROSSWALK_SQL)}
    assert got == exp
    # Negative check: the unfiltered total is strictly larger on this fixture.
    assert sum(v[0] for v in got.values()) < len(rows)


@pytest.mark.parametrize("htype", TYPES)
def test_crosswalk_hazard_type_branch_known_answer(htype):
    rows = _rows(3)
    db = _db(rows)
    _, exp = _expected(rows, htype)
    fake = _Capture()
    cs.CatalogSqlService.get_crosswalk(fake, hazard_type=htype)
    sql, params = fake.calls[0]
    got = {(r["hazard_type"], r["proximity_band"]): (r["intersection_count"], r["distinct_spans"])
           for r in _run(db, sql, **params)}
    assert got == exp


def test_summary_known_answer_and_band_sum():
    rows = _rows(11)
    db = _db(rows, spans=150)
    keep, _ = _expected(rows)
    r = _run(db, cs._CROSSWALK_SUMMARY_SQL)[0]
    assert r["total_intersections"] == len(keep)
    assert r["distinct_spans_exposed"] == len({k[2] for k in keep})
    assert r["total_spans"] == 150  # denominator is NOT radius-filtered
    for b in BANDS:
        assert r[f"{b}_count"] == sum(1 for k in keep if k[1] == b)
    assert r["direct_impact_count"] + r["near_field_count"] + r["buffer_zone_count"] == r["total_intersections"]


def test_get_crosswalk_summary_service_shape():
    row = {"total_intersections": 83029, "distinct_spans_exposed": 10085, "total_spans": 10092,
           "direct_impact_count": 600, "near_field_count": 3169, "buffer_zone_count": 79260, "hazard_types": 5}
    out = cs.CatalogSqlService.get_crosswalk_summary(_Capture([row]))
    assert out["exposure_pct"] == 99.9
    assert out["direct_impact_count"] == 600 and out["total_intersections"] == 83029


# --- Mock fallback mirrors in-radius live values ----------------------------------

def test_mock_summary_matches_bug_qa_129_expected_values():
    s = md.generate_mock_crosswalk_summary()
    assert s["total_intersections"] == 83029
    assert s["direct_impact_count"] == 600
    assert s["direct_impact_count"] + s["near_field_count"] + s["buffer_zone_count"] == s["total_intersections"]


def test_mock_rows_consistent_with_mock_summary():
    s = md.generate_mock_crosswalk_summary()
    rows = md.generate_mock_crosswalk()
    assert sum(r["intersection_count"] for r in rows) == s["total_intersections"]
    for b in BANDS:
        assert sum(r["intersection_count"] for r in rows if r["proximity_band"] == b) == s[f"{b}_count"]
    assert {r["hazard_type"] for r in rows} == set(TYPES)
    assert len({r["hazard_type"] for r in rows}) == s["hazard_types"]


# --- Copy ------------------------------------------------------------------------

def test_buffer_zone_band_label_is_ge_5_km():
    src = open(TABLE_TSX, encoding="utf-8").read()
    m = re.search(r"buffer_zone:\s*\"([^\"]*)\"", src)
    assert m and m.group(1) == "Buffer Zone (\u22655 km)"
    assert "radius km" not in src


def test_pydantic_descriptions_drop_radius_km_band():
    src = open(MODELS_PY, encoding="utf-8").read()
    assert "5-radius_km" not in src
    assert "buffer_zone (>=5 km)" in src
    assert "is_within_radius = TRUE" in src
