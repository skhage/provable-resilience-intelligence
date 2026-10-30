"""BUG-QA-080: live-schema contract for every SQL constant in catalog_sql.py.

Schema drift (srg.description, sp.hop_index, si.path_diversity_status) made three topology
queries fail live and degrade silently. This suite:
  * offline: guards against the known drifted columns, unit-tests classify_diversity(), and
    checks the router reports X-PRI-Data-Source instead of failing silently;
  * live (opt-in): runs EXPLAIN on every *_SQL constant against the warehouse. Set
    PRI_CONTRACT_WAREHOUSE_ID (and Databricks auth) to enable.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import re
import sys

import pytest

APP_SRC = os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(APP_SRC))

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

SQL_CONSTANTS = {n: v for n, v in vars(cs).items() if n.startswith("_") and n.endswith("_SQL") and isinstance(v, str)}
CATALOG = os.environ.get("PRI_CATALOG", "cdm_tmforum")
SCHEMA = os.environ.get("PRI_SCHEMA", "provable_resilience_intelligence")
WAREHOUSE = os.environ.get("PRI_CONTRACT_WAREHOUSE_ID")

DRIFTED = [
    (r"\bsrg\.description\b", "shared_risk_group has no description (use srlg_name)"),
    (r"\bsp\.hop_index\b", "service_path column is hop_sequence"),
    (r"\bsi\.path_diversity_status\b", "service_inventory has no path_diversity_status"),
    (r"\bprs\.strand_count\b", "physical_resource_span column is fiber_count"),
]


def test_sql_constants_discovered():
    assert len(SQL_CONSTANTS) >= 20
    for name in ("_SERVICE_PATH_TRACE_SQL", "_SERVICE_DIVERSITY_SQL", "_SRLG_BY_REGION_SQL"):
        assert name in SQL_CONSTANTS


@pytest.mark.parametrize("pattern,why", DRIFTED)
def test_no_drifted_columns(pattern, why):
    bad = [n for n, sql in SQL_CONSTANTS.items() if re.search(pattern, sql)]
    assert not bad, f"{why}: {bad}"


@pytest.mark.parametrize(
    "args,expected",
    [
        ((0, 0, 0, 0), "unknown"),
        ((0, 0, 0, 6), "single_path"),
        ((5, 0, 0, 6), "fully_diverse"),
        ((5, 1, 0, 6), "partially_diverse"),
        ((5, 0, 2, 6), "partially_diverse"),
    ],
)
def test_classify_diversity(args, expected):
    assert cs.classify_diversity(*args) == expected


class _Rows:
    is_available = True

    def __init__(self, rows):
        self.rows = rows

    def _execute(self, sql, row_limit=12000, params=None):
        return self.rows


def test_get_service_diversity_derives_status():
    fake = _Rows([{
        "service_id": "SVC-1", "sold_as_diverse": "false", "working_hops": "6", "protect_hops": "0",
        "working_conduits": "6", "protect_conduits": "0", "shared_conduit_count": "0",
        "shared_srlg_count": "0", "crosses_backbone": "1", "path_diversity_score": "100.0",
    }])
    out = cs.CatalogSqlService.get_service_diversity(fake, "SVC-1")
    assert out["diversity_status"] == "single_path"
    assert out["sold_as_diverse"] is False
    assert out["path_diversity_score"] == 100.0
    assert out["crosses_backbone"] is True


def test_router_flags_unavailable_instead_of_silent():
    pytest.importorskip("fastapi")
    from fastapi import HTTPException, Response

    from resilience_scorecard.backend import router as r

    class _Down:
        is_available = True

        def get_service_path_trace(self, _):
            return None

        def get_srlgs_by_region(self, _):
            raise RuntimeError("UNRESOLVED_COLUMN")

        def get_service_diversity(self, _):
            raise RuntimeError("UNRESOLVED_COLUMN")

    resp = Response()
    # BUG-QA-094: path trace now takes config (v4 flag); flag off = v3 call shape.
    from types import SimpleNamespace
    assert r.get_service_path_trace("SVC-1", _Down(), resp, SimpleNamespace(v4_kpis=False)) == []
    assert resp.headers[r.DATA_SOURCE_HEADER] == "unavailable"
    resp = Response()
    assert r.list_topology_srlgs(_Down(), resp, region="West") == []
    assert resp.headers[r.DATA_SOURCE_HEADER] == "unavailable"
    with pytest.raises(HTTPException) as exc:
        r.get_service_diversity("SVC-1", _Down(), Response())
    assert exc.value.status_code == 503


@pytest.mark.skipif(not WAREHOUSE, reason="set PRI_CONTRACT_WAREHOUSE_ID to run the live contract")
@pytest.mark.parametrize("name", sorted(SQL_CONSTANTS))
def test_live_explain(name):
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementParameterListItem, StatementState

    # Some constants carry a {where} template filled at call time; plan the base query.
    sql = re.sub(r"\{\w+\}", "", SQL_CONSTANTS[name])
    names = sorted(set(re.findall(r"(?<!:):([A-Za-z_]\w*)", sql)))
    params = [StatementParameterListItem(name=n, value="x", type="STRING") for n in names] or None
    resp = WorkspaceClient().statement_execution.execute_statement(
        warehouse_id=WAREHOUSE, statement="EXPLAIN " + sql, catalog=CATALOG, schema=SCHEMA,
        wait_timeout="50s", parameters=params,
    )
    assert resp.status.state == StatementState.SUCCEEDED, resp.status.error
    plan = " ".join(str(c) for row in (resp.result.data_array or []) for c in row)
    assert "AnalysisException" not in plan and "UNRESOLVED" not in plan.upper(), f"{name}: {plan[:500]}"
