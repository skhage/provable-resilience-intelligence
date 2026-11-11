"""BUG-DW-166 regression tests: crosswalk tfoot Spans honesty.

(1) Loading state must not render the 'unavailable' text; 'unavailable' only on error.
(2) Live-mode totals failure must not return mock values (503 -> em dash path).
Mock totals only when the whole app is in mock mode.
These tests fail on 30ceb9e.
"""
import pathlib
import re

import pytest
from fastapi import HTTPException

from resilience_scorecard.backend import router
from resilience_scorecard.backend.services import mock_data

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_TSX = _ROOT / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui/components/hazards/"
    "hazard-crosswalk-table.tsx"
)
_ROUTER = pathlib.Path(router.__file__)


class _Live:
    is_available = True

    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def get_crosswalk_totals(self, hazard_type=None):
        if self.exc:
            raise self.exc
        return self.result


class _Mock:
    is_available = False


# ---------- backend: no mock/live mix ----------------------------------------


def test_live_failure_raises_503_not_mock():
    with pytest.raises(HTTPException) as e:
        router.get_hazard_crosswalk_totals(csql=_Live(exc=RuntimeError("warehouse down")), hazard_type=None)
    assert e.value.status_code == 503


def test_live_none_raises_503_not_mock():
    with pytest.raises(HTTPException) as e:
        router.get_hazard_crosswalk_totals(csql=_Live(result=None), hazard_type="wildfire")
    assert e.value.status_code == 503


def test_live_success_returns_live_values():
    live = {"hazard_type": "flood", "intersection_count": 11, "distinct_spans": 7}
    assert router.get_hazard_crosswalk_totals(csql=_Live(result=live), hazard_type="flood") == live


def test_mock_mode_still_serves_mock():
    got = router.get_hazard_crosswalk_totals(csql=_Mock(), hazard_type="wildfire")
    assert got == mock_data.generate_mock_crosswalk_totals("wildfire")


def test_router_totals_body_has_no_mock_after_live_branch():
    src = _ROUTER.read_text(encoding="utf-8")
    body = src[src.index("def get_hazard_crosswalk_totals"):]
    body = body[: body.index("@router.")]
    # The mock call appears exactly once, in the not-available branch.
    assert body.count("generate_mock_crosswalk_totals(") == 1
    assert "status_code=503" in body


# ---------- UI: loading vs unavailable ---------------------------------------


def _tfoot_cell(src):
    i = src.index("BUG-DW-166: three honest states")
    return src[i: src.index("</td>", i)]


def test_tsx_reads_error_and_fetching_flags():
    src = _TSX.read_text(encoding="utf-8")
    assert "isError: totalsError" in src and "isFetching: totalsFetching" in src


def test_tsx_loading_branch_has_no_unavailable_text():
    cell = _tfoot_cell(_TSX.read_text(encoding="utf-8"))
    loading = cell[cell.index("Skeleton") - 200:]
    loading = loading[loading.index(") : ("):]
    assert "Loading distinct span total" in loading
    assert "unavailable" not in loading.lower()


def test_tsx_unavailable_only_when_error_or_settled():
    cell = _tfoot_cell(_TSX.read_text(encoding="utf-8"))
    m = re.search(r"\)\s*:\s*totalsError \|\| !totalsFetching \? \(", cell)
    assert m, "unavailable branch must be gated on error / settled"
    after = cell[m.end():]
    assert after.index("unavailable") < after.index("Loading distinct span total")


def test_tsx_cell_aria_busy_while_fetching():
    assert 'aria-busy={totalsFetching}' in _tfoot_cell(_TSX.read_text(encoding="utf-8"))


def test_no_lumen_in_changed_files():
    for p in (_TSX, _ROUTER):
        assert "lumen" not in p.read_text(encoding="utf-8").lower(), p
