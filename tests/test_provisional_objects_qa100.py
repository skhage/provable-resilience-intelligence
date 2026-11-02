"""BUG-QA-100: the app's PROVISIONAL object list must stay in sync with ops/v4_cutover_runbook PARTIAL_KEEP_V3.

DEC-42: every KEEP_V3 object must carry the PROVISIONAL label in UI copy. DEC-44 adds the FK consumers.
DEFERRED_V4_1 objects are v4-only, so nothing is kept and no label applies.
"""
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "apps" / "resilience-scorecard" / "src"
sys.path.insert(0, str(ROOT / "ops"))
sys.path.insert(0, str(APP_SRC))

import v4_cutover_runbook as rb  # noqa: E402
from resilience_scorecard.backend import provisional_objects as po  # noqa: E402

PROVISIONAL_TS = APP_SRC / "resilience_scorecard" / "ui" / "lib" / "provisional-disclosure.ts"


# ---------------------------------------------------------------- sync with runbook

def test_candidates_mirror_runbook_partial_keep_v3_exactly():
    assert tuple(po.PARTIAL_KEEP_V3_CANDIDATES) == tuple(rb.PARTIAL_KEEP_V3)


def test_default_equals_keep_v3_minus_deferred():
    expected = set(rb.PARTIAL_KEEP_V3) - set(po.DEFERRED_V4_1_OBJECTS)
    assert set(po.DEFAULT_PROVISIONAL_OBJECTS) == expected
    assert len(po.DEFAULT_PROVISIONAL_OBJECTS) == len(set(po.DEFAULT_PROVISIONAL_OBJECTS)) == 10


def test_deferred_subset_of_candidates():
    assert po.DEFERRED_V4_1_OBJECTS <= set(rb.PARTIAL_KEEP_V3)


def test_qa100_specific_items():
    d = set(po.DEFAULT_PROVISIONAL_OBJECTS)
    for must in ("revenue_at_risk", "diversity_coverage", "optical_anomaly_detection", "span_risk_inference_log"):
        assert must in d, must
    assert "span_hazard_features" not in d


@pytest.mark.parametrize("name", sorted(po.DEFERRED_V4_1_OBJECTS))
def test_deferred_matches_runbook_verdict_for_v4_only_object(name):
    # The runbook's own pure verdict for an object with no live object and not in v3 is DEFERRED_V4_1.
    item = next(i for i in rb.RUNBOOK if i.live == name)
    assert rb.partial_keep_verdict(item, {"live_type": None, "v3_status": "NOT_IN_V3"}) == rb.PARTIAL_DEFERRED_VERDICT


def test_router_default_is_derived_not_hardcoded():
    src = (APP_SRC / "resilience_scorecard" / "backend" / "router.py").read_text()
    assert "_DEFAULT_PROVISIONAL_OBJECTS = list(DEFAULT_PROVISIONAL_OBJECTS)" in src
    assert 'hasattr(csql, "get_provisional_objects")' not in src  # dead branch removed


def test_catalog_sql_implements_get_provisional_objects():
    src = (APP_SRC / "resilience_scorecard" / "backend" / "services" / "catalog_sql.py").read_text()
    assert "def get_provisional_objects(self)" in src
    assert "_PROVISIONAL_OBJECTS_SQL = PROVISIONAL_OBJECTS_SQL" in src  # discovered by live EXPLAIN contract


# ---------------------------------------------------------------- SQL known answer (SQLite)

def _sqlite_sql():
    sql = po.PROVISIONAL_OBJECTS_SQL
    return sql.replace("information_schema.tables", "ist").replace("current_schema()", "'pri'")


def test_sql_known_answer_sqlite():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE demo_freeze_manifest (manifest_version TEXT, object_name TEXT)")
    db.execute("CREATE TABLE ist (table_schema TEXT, table_name TEXT)")
    v3 = [o for o in po.PARTIAL_KEEP_V3_CANDIDATES if o not in po.DEFERRED_V4_1_OBJECTS]
    rows = [("PRI-DEMO-FREEZE-v3", o) for o in v3]
    rows += [("PRI-DEMO-FREEZE-v3", o) for o in v3[:2]]           # duplicate manifest rows -> deduped
    rows += [("PRI-DEMO-FREEZE-v4-DRAFT", "span_hazard_features")]  # other manifest version ignored
    rows += [("PRI-DEMO-FREEZE-v3", "geographic_site")]            # non-candidate ignored
    db.executemany("INSERT INTO demo_freeze_manifest VALUES (?, ?)", rows)
    live = [o for o in v3 if o != "proactive_action"] + ["geographic_site"]  # proactive_action dropped live
    db.executemany("INSERT INTO ist VALUES ('pri', ?)", [(o,) for o in live])
    db.execute("INSERT INTO ist VALUES ('other_schema', 'proactive_action')")  # wrong schema ignored
    got = [r[0] for r in db.execute(_sqlite_sql()).fetchall()]
    assert got == sorted(set(v3) - {"proactive_action"})


# ---------------------------------------------------------------- service + router behaviour

def _service(rows):
    from resilience_scorecard.backend.services.catalog_sql import CatalogSqlService
    svc = object.__new__(CatalogSqlService)
    svc._execute = lambda sql, row_limit=12000, params=None: rows
    return svc


def test_service_returns_names_and_none_on_failure():
    assert _service([{"object_name": "revenue_at_risk"}, {"object_name": None}]).get_provisional_objects() == ["revenue_at_risk"]
    assert _service(None).get_provisional_objects() is None
    assert _service([]).get_provisional_objects() == []


def _manifest(mode, csql):
    from resilience_scorecard.backend.router import get_cutover_manifest
    return get_cutover_manifest(SimpleNamespace(cutover_mode=mode), csql)


class _Csql:
    def __init__(self, available=True, result=None, exc=None):
        self.is_available, self._r, self._e = available, result, exc

    def get_provisional_objects(self):
        if self._e:
            raise self._e
        return self._r


def test_router_partial_uses_live_list():
    out = _manifest("partial", _Csql(result=["revenue_at_risk", "resilience_score_snapshot"]))
    assert out.cutover_mode == "PARTIAL" and out.provisional_objects == ["revenue_at_risk", "resilience_score_snapshot"]


@pytest.mark.parametrize("csql", [_Csql(available=False), _Csql(result=None), _Csql(result=[]),
                                  _Csql(exc=RuntimeError("boom")), SimpleNamespace()])
def test_router_partial_falls_back_to_default(csql):
    out = _manifest("PARTIAL", csql)
    assert set(out.provisional_objects) == set(po.DEFAULT_PROVISIONAL_OBJECTS)


@pytest.mark.parametrize("mode", ["none", "", None])
def test_router_no_cutover_mode_has_no_provisional(mode):
    assert _manifest(mode, _Csql(result=["revenue_at_risk"])).provisional_objects == []


@pytest.mark.parametrize("mode", ["FULL", "full"])
def test_router_full_lists_only_dec45_fk_consumers(mode):
    """P73 / DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES (id 45): FULL mode labels only the 2 kept FK consumers."""
    out = _manifest(mode, _Csql(result=["revenue_at_risk"]))
    assert out.cutover_mode == "FULL"
    assert out.provisional_objects == ["optical_anomaly_detection", "span_risk_inference_log"]


def test_full_mode_provisional_mirrors_runbook():
    assert tuple(po.FULL_MODE_PROVISIONAL_OBJECTS) == tuple(rb.FULL_MODE_PROVISIONAL)
    assert set(po.FULL_MODE_PROVISIONAL_OBJECTS) <= set(po.DEFAULT_PROVISIONAL_OBJECTS)


# ---------------------------------------------------------------- UI surface mapping

def _node_is_provisional(surface, objs):
    text = PROVISIONAL_TS.read_text()
    m = re.search(r"const SURFACE_SOURCES[^=]*=\s*(\{.*?\n\});", text, re.S)
    body = re.sub(r"^\s*//.*$", "", m.group(1), flags=re.M)
    js = (f"const S={body};const s=S[{json.dumps(surface)}]||[];const o={json.dumps(objs)};"
          "console.log(JSON.stringify(s.some(x=>o.includes(x))));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.parametrize("obj,expected", [
    ("resilience_score_snapshot", True),
    # BUG-DW-124: no header card reads these MVs (they stay in the backend list for Genie/DEC-42).
    ("revenue_at_risk", False),
    ("diversity_coverage", False),
])
def test_header_provisional_for_headline_kpi_sources(obj, expected):
    assert _node_is_provisional("scorecard_header", [obj]) is expected


def test_ui_sources_are_all_keep_v3_candidates():
    text = PROVISIONAL_TS.read_text()
    block = re.search(r"const SURFACE_SOURCES[^=]*=\s*\{(.*?)\n\};", text, re.S).group(1)
    names = set(re.findall(r'"([a-z0-9_]+)"', block))
    assert names <= set(po.DEFAULT_PROVISIONAL_OBJECTS), names - set(po.DEFAULT_PROVISIONAL_OBJECTS)


# ---------------------------------------------------------------- live (opt-in)

@pytest.mark.skipif(not os.environ.get("PRI_CONTRACT_WAREHOUSE_ID"), reason="live warehouse not configured")
def test_live_default_matches_uc():
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    r = w.statement_execution.execute_statement(
        warehouse_id=os.environ["PRI_CONTRACT_WAREHOUSE_ID"], statement=po.PROVISIONAL_OBJECTS_SQL,
        catalog="cdm_tmforum", schema="provable_resilience_intelligence", wait_timeout="50s")
    got = {row[0] for row in (r.result.data_array or [])}
    assert got == set(po.DEFAULT_PROVISIONAL_OBJECTS)
