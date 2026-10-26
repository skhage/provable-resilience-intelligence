"""BUG-QA-077: every user-supplied value in catalog_sql.py is bound as a statement parameter.

Quote-doubling is bypassable in Databricks SQL (backslash escapes), so no call site may
inline user input into statement text.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import re
import sys
from types import SimpleNamespace

import pytest

APP_SRC = os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(APP_SRC))

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

PAYLOAD = "\\' OR 1=1 --"  # the QA repro: backslash + quote
SVC = cs.CatalogSqlService


class _Capture:
    is_available = True

    def __init__(self):
        self.calls = []

    def _execute(self, sql, row_limit=12000, params=None):
        self.calls.append((sql, params))
        return []


# (method, kwargs, parameter name)
CALL_SITES = [
    (SVC.get_topology_sites, {"region": PAYLOAD}, "region"),
    (SVC.get_topology_conduits, {"region": PAYLOAD}, "region"),
    (SVC.list_conduit_coverage, {"coverage_class": None, "region": PAYLOAD}, "region"),
    (SVC.get_service_path_trace, {"service_id": PAYLOAD}, "service_id"),
    (SVC.get_service_diversity, {"service_id": PAYLOAD}, "service_id"),
    (SVC.get_srlgs_by_region, {"region": PAYLOAD}, "region"),
    (SVC.get_service_score, {"service_id": PAYLOAD}, "service_id"),
    (SVC.get_crosswalk, {"hazard_type": PAYLOAD}, "hazard_type"),
]


@pytest.mark.parametrize("method,kwargs,pname", CALL_SITES, ids=[c[0].__name__ for c in CALL_SITES])
def test_payload_is_bound_not_inlined(method, kwargs, pname):
    fake = _Capture()
    method(fake, **kwargs)
    assert len(fake.calls) == 1
    sql, params = fake.calls[0]
    assert params is not None and params.get(pname) == PAYLOAD
    assert PAYLOAD not in sql
    assert "OR 1=1" not in sql
    assert f":{pname}" in sql
    # No leftover template placeholders.
    assert not re.search(r"\{(region|service_id|hazard_type|where)\}", sql)


def test_no_quote_doubling_escapes_remain():
    path = os.path.join(APP_SRC, "resilience_scorecard", "backend", "services", "catalog_sql.py")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "replace(\"'\", \"''\")" not in text
    assert "chr(39) * 2" not in text
    for name in ("region", "service_id", "hazard_type"):
        assert f"'{{{name}}}'" not in text


def test_execute_forwards_parameters_to_sdk():
    captured = {}

    class _Stmt:
        def execute_statement(self, **kw):
            captured.update(kw)
            return SimpleNamespace(status=SimpleNamespace(state=None, error="x"))

    svc = SVC.__new__(SVC)
    svc._w = SimpleNamespace(statement_execution=_Stmt())
    svc._config = SimpleNamespace(warehouse_id="wh", catalog="c", schema_name="s")
    svc._execute("SELECT :region", params={"region": PAYLOAD})
    items = captured["parameters"]
    assert [(p.name, p.value) for p in items] == [("region", PAYLOAD)]
    assert captured["statement"] == "SELECT :region"


def test_execute_without_params_sends_none():
    captured = {}

    class _Stmt:
        def execute_statement(self, **kw):
            captured.update(kw)
            return SimpleNamespace(status=SimpleNamespace(state=None, error="x"))

    svc = SVC.__new__(SVC)
    svc._w = SimpleNamespace(statement_execution=_Stmt())
    svc._config = SimpleNamespace(warehouse_id="wh", catalog="c", schema_name="s")
    svc._execute("SELECT 1")
    assert captured["parameters"] is None
