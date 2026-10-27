"""BUG-QA-086: /services/{id}/diversity must answer 503 + 'unavailable' on a live SQL failure.

Before the fix, _execute() returned None for a FAILED statement, get_service_diversity()
returned None for both failure and not-found, and the router raised 404 with no
X-PRI-Data-Source header. These tests drive a real StatementState through the real
CatalogSqlService._execute (only the SDK client is faked).

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import sys
from types import SimpleNamespace

import pytest

APP_SRC = os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(APP_SRC))

from databricks.sdk.service.sql import ColumnInfoTypeName, StatementState  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402

from resilience_scorecard.backend import router as rt  # noqa: E402
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

_COLS = [
    ("service_id", ColumnInfoTypeName.STRING),
    ("working_hops", ColumnInfoTypeName.LONG),
    ("protect_hops", ColumnInfoTypeName.LONG),
    ("working_conduits", ColumnInfoTypeName.LONG),
    ("protect_conduits", ColumnInfoTypeName.LONG),
    ("shared_conduit_count", ColumnInfoTypeName.LONG),
    ("shared_srlg_count", ColumnInfoTypeName.LONG),
    ("sold_as_diverse", ColumnInfoTypeName.BOOLEAN),
    ("path_diversity_score", ColumnInfoTypeName.DOUBLE),
    ("crosses_backbone", ColumnInfoTypeName.LONG),
]


def _resp(state, data_array=None):
    return SimpleNamespace(
        status=SimpleNamespace(state=state, error=SimpleNamespace(message="boom")),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(columns=[SimpleNamespace(name=n, type_name=t) for n, t in _COLS])
        ),
        result=SimpleNamespace(data_array=data_array),
    )


class _Stmt:
    def __init__(self, outcome):
        self._outcome = outcome

    def execute_statement(self, **_kw):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _service(outcome):
    """A CatalogSqlService wired to a fake SDK client; skips the live __init__ probe."""
    svc = object.__new__(cs.CatalogSqlService)
    svc._config = SimpleNamespace(warehouse_id="wh", catalog="c", schema_name="s")
    svc._w = SimpleNamespace(statement_execution=_Stmt(outcome))
    svc._available = True
    return svc


@pytest.mark.parametrize(
    "outcome",
    [_resp(StatementState.FAILED), _resp(StatementState.CANCELED), RuntimeError("network down")],
    ids=["failed", "canceled", "sdk_exception"],
)
def test_service_raises_on_live_failure(outcome):
    with pytest.raises(cs.CatalogQueryError):
        _service(outcome).get_service_diversity("SVC-00013")


@pytest.mark.parametrize(
    "outcome",
    [_resp(StatementState.FAILED), RuntimeError("network down")],
    ids=["failed", "sdk_exception"],
)
def test_router_returns_503_unavailable_on_live_failure(outcome):
    response = Response()
    with pytest.raises(HTTPException) as exc:
        rt.get_service_diversity("SVC-00013", _service(outcome), response)
    assert exc.value.status_code == 503
    assert exc.value.headers == {rt.DATA_SOURCE_HEADER: "unavailable"}


def test_router_returns_404_only_on_empty_success():
    response = Response()
    with pytest.raises(HTTPException) as exc:
        rt.get_service_diversity("SVC-99999", _service(_resp(StatementState.SUCCEEDED, [])), response)
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail
    assert not exc.value.headers


def test_router_returns_live_row_with_header():
    row = ["SVC-00013", "4", "3", "4", "3", "1", "0", "true", "84.6", "0"]
    response = Response()
    out = rt.get_service_diversity("SVC-00013", _service(_resp(StatementState.SUCCEEDED, [row])), response)
    assert response.headers[rt.DATA_SOURCE_HEADER] == "live"
    assert out["service_id"] == "SVC-00013"
    assert out["diversity_status"] == "partially_diverse"  # shared conduit
    assert out["shared_conduit_count"] == 1
    assert out["sold_as_diverse"] is True


def test_router_returns_503_when_service_unavailable():
    svc = _service(_resp(StatementState.SUCCEEDED, []))
    svc._available = False
    with pytest.raises(HTTPException) as exc:
        rt.get_service_diversity("SVC-00013", svc, Response())
    assert exc.value.status_code == 503
