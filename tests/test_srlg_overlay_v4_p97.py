"""P97-APP-V4-SRLG-OVERLAY-SPANS: under PRI_V4_KPIS the SRLG overlay / conduit panel list resolves
span_id against physical_resource_span_v4_candidate, so SRLG rows on v4 backbone segments (BBS-*)
carry their CDT-BBR-* conduit_id and reach the v4 /topology conduit panel. Flag off = v3 freeze.

Known answer: the real SQL constants run on a SQLite fixture with one SPAN-* SRLG row and one
BBS-* SRLG row. Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import hashlib
import os
import re
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
PKG = os.path.join(APP_SRC, "resilience_scorecard")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

# sha256 of _SRLG_BY_REGION_SQL. Was c24ace6c... (a5db5d3 .. ed72998). Re-pinned by
# P108-APP-SRLG-OVERLAY-LIMIT-TRUNCATION (per-(conduit, srlg) grain, total ORDER BY, LIMIT 5000);
# see tests/test_srlg_overlay_p108.py. Any further change must re-pin here deliberately.
V3_SRLG_SHA256 = "6429a95ed34c6160be30702c907061cf221e2b36648230bbe4515bb7f32d86e6"


# --- static contract ---------------------------------------------------------------

def test_v3_srlg_sql_byte_identical():
    assert hashlib.sha256(cs._SRLG_BY_REGION_SQL.encode()).hexdigest() == V3_SRLG_SHA256
    assert "_v4_candidate" not in cs._SRLG_BY_REGION_SQL


def test_v4_sql_differs_only_in_span_table():
    v4 = cs._SRLG_BY_REGION_V4_SQL
    assert v4.count("JOIN physical_resource_span_v4_candidate prs ON") == 1
    assert "JOIN physical_resource_span prs ON" not in v4
    # Same columns, params, ORDER BY and LIMIT: removing the suffix gives the v3 text back.
    assert v4.replace("physical_resource_span_v4_candidate", "physical_resource_span") == cs._SRLG_BY_REGION_SQL
    assert "FROM shared_risk_group srg" in v4


# --- known answer on SQLite --------------------------------------------------------

def _db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    CREATE TABLE geographic_site (site_id TEXT, site_name TEXT, region TEXT, tier TEXT);
    CREATE TABLE shared_risk_group (srlg_id TEXT, srlg_type TEXT, severity TEXT, span_id TEXT, srlg_name TEXT);
    CREATE TABLE physical_resource_span (span_id TEXT, site_a_id TEXT, site_z_id TEXT, conduit_id TEXT,
                                         length_km REAL, is_active INT);
    CREATE TABLE physical_resource_span_v4_candidate (span_id TEXT, site_a_id TEXT, site_z_id TEXT,
                                         conduit_id TEXT, length_km REAL, is_active INT);
    INSERT INTO geographic_site VALUES ('A','Lakelink Fiber A CO','Central','tier_1'),
                                       ('Z','Lakelink Fiber Z DC','Central','tier_2');
    -- v3: SPAN-1 real segment + BB-7 route row (v4 replaces BB-7 with its BBS-7-* segments).
    INSERT INTO physical_resource_span VALUES ('SPAN-1','A','Z','CDT-1',3.0,1),
                                              ('BB-7','A','Z','CDT-BB-7',900.0,1);
    INSERT INTO physical_resource_span_v4_candidate VALUES ('SPAN-1','A','Z','CDT-1',3.0,1),
                                              ('BBS-7-001','A','Z','CDT-BBR-7',24.9,1),
                                              ('BBS-7-002','A','Z','CDT-BBR-7',24.9,0);
    INSERT INTO shared_risk_group VALUES ('SRLG-1','shared_conduit','high','SPAN-1','metro'),
                                         ('SRLG-BB','shared_conduit','critical','BBS-7-001','bb'),
                                         ('SRLG-OFF','shared_conduit','low','BBS-7-002','inactive');
    """)
    return db


def _run(sql, region="Central"):
    db = _db()
    db.row_factory = sqlite3.Row
    sql = sql.replace("TRUE", "1")
    return [dict(r) for r in db.execute(sql, {"region": region}).fetchall()]


def test_v3_sql_never_sees_bbs_srlg():
    rows = _run(cs._SRLG_BY_REGION_SQL)
    assert [r["srlg_id"] for r in rows] == ["SRLG-1"]


def test_v4_sql_resolves_bbs_srlg_to_bbr_conduit():
    rows = _run(cs._SRLG_BY_REGION_V4_SQL)
    ids = [r["srlg_id"] for r in rows]
    assert ids == ["SRLG-BB", "SRLG-1"]  # critical first; inactive BBS-7-002 excluded
    bb = rows[0]
    assert bb["conduit_id"] == "CDT-BBR-7" and bb["span_id"] == "BBS-7-001"
    assert bb["span_length_km"] == 24.9 and bb["description"] == "bb"


def test_non_backbone_rows_identical_across_flag():
    v3 = [r for r in _run(cs._SRLG_BY_REGION_SQL) if r["span_id"].startswith("SPAN-")]
    v4 = [r for r in _run(cs._SRLG_BY_REGION_V4_SQL) if r["span_id"].startswith("SPAN-")]
    assert v3 == v4 and len(v3) == 1


def test_region_param_bound_not_inlined():
    assert _run(cs._SRLG_BY_REGION_V4_SQL, region="West") == []
    assert ":region" in cs._SRLG_BY_REGION_V4_SQL


# --- service + router wiring -------------------------------------------------------

class _Capture:
    def __init__(self):
        self.sql = None

    def __call__(self, sql, row_limit=None, params=None):
        self.sql, self.params, self.row_limit = sql, params, row_limit
        return [{"span_length_km": "24.9"}]


def _svc():
    svc = object.__new__(cs.CatalogSqlService)
    svc._execute = _Capture()
    return svc


def test_service_default_is_v3():
    svc = _svc()
    rows = svc.get_srlgs_by_region("Central")
    assert svc._execute.sql is cs._SRLG_BY_REGION_SQL
    assert svc._execute.params == {"region": "Central"} and svc._execute.row_limit == cs.SRLG_REGION_ROW_CAP
    assert rows[0]["span_length_km"] == 24.9


def test_service_v4_uses_v4_sql():
    svc = _svc()
    svc.get_srlgs_by_region("Central", v4=True)
    assert svc._execute.sql is cs._SRLG_BY_REGION_V4_SQL
    assert svc._execute.params == {"region": "Central"}


class _Fake:
    is_available = True

    def __init__(self):
        self.calls = []

    def get_srlgs_by_region(self, region, **kw):
        self.calls.append((region, kw))
        return []


@pytest.mark.parametrize("flag,expected_kw", [(False, {}), (True, {"v4": True})])
def test_router_passes_flag(flag, expected_kw):
    pytest.importorskip("fastapi")
    from fastapi import Response

    from resilience_scorecard.backend import router as r

    fake, resp = _Fake(), Response()
    assert r.list_topology_srlgs(fake, resp, SimpleNamespace(v4_kpis=flag), region="Central") == []
    assert fake.calls == [("Central", expected_kw)]  # flag off keeps the exact v3 call shape
    assert resp.headers[r.DATA_SOURCE_HEADER] == "live"


def test_router_signature_matches_path_trace_pattern():
    import inspect

    pytest.importorskip("fastapi")
    from resilience_scorecard.backend import router as r

    assert list(inspect.signature(r.list_topology_srlgs).parameters) == ["csql", "response", "config", "region"]


def test_no_brand_leak():
    for p in (os.path.join(PKG, "backend", "services", "catalog_sql.py"),
              os.path.join(PKG, "backend", "router.py"), __file__):
        txt = open(p).read()
        assert not re.search("lu" + "men", txt, re.I), p
