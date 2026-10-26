"""P36-APP-V4-MRC-PROTECTED-KPI: PRI_V4_KPIS flag, MRC Protected endpoint, SQL source, banned copy.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import re
import sys

import pytest
from fastapi import HTTPException

APP_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
)
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend import router as r  # noqa: E402
from resilience_scorecard.backend.core import AppConfig  # noqa: E402
from resilience_scorecard.backend.models import MrcProtectedOut  # noqa: E402
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

PKG = os.path.join(APP_SRC, "resilience_scorecard")
LIVE_ROW = {  # live values from mv_mrc_protected_v4_candidate, 2026-10-26
    "mrc_protected_usd": 72767771.0,
    "services_protected": 4625,
    "mrc_share": 0.5784008078242245,
    "total_mrc_usd": 125808557.0,
    "total_services": 8000,
}


class _Cfg:
    def __init__(self, v4):
        self.v4_kpis = v4


class _Unavailable:
    is_available = False


class _Rows:
    is_available = True

    def __init__(self, rows):
        self.rows = rows
        self.sql = None

    def _execute(self, sql, row_limit=12000):
        self.sql = sql
        return self.rows

    def get_mrc_protected(self):
        return cs.CatalogSqlService.get_mrc_protected(self)


# --- flag ---------------------------------------------------------------

def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PRI_V4_KPIS", raising=False)
    monkeypatch.delenv("RESILIENCE_SCORECARD_V4_KPIS", raising=False)
    assert AppConfig().v4_kpis is False


@pytest.mark.parametrize("name", ["PRI_V4_KPIS", "RESILIENCE_SCORECARD_V4_KPIS"])
def test_flag_reads_env(monkeypatch, name):
    monkeypatch.setenv(name, "true")
    assert AppConfig().v4_kpis is True


def test_app_yaml_ships_flag_off():
    with open(os.path.join(APP_SRC, os.pardir, "app.yaml"), encoding="utf-8") as f:
        text = f.read()
    assert re.search(r'name: PRI_V4_KPIS\s+value: "false"', text)


def test_feature_flags_endpoint():
    assert r.get_feature_flags(config=_Cfg(False)) == {"v4_kpis": False}
    assert r.get_feature_flags(config=_Cfg(True)) == {"v4_kpis": True}


# --- endpoint -----------------------------------------------------------

def test_endpoint_404_when_flag_off():
    with pytest.raises(HTTPException) as exc:
        r.get_mrc_protected(config=_Cfg(False), csql=_Rows([LIVE_ROW]))
    assert exc.value.status_code == 404


def test_endpoint_503_without_warehouse_no_mock():
    with pytest.raises(HTTPException) as exc:
        r.get_mrc_protected(config=_Cfg(True), csql=_Unavailable())
    assert exc.value.status_code == 503


@pytest.mark.parametrize("row", [
    LIVE_ROW | {"mrc_protected_usd": None},
    LIVE_ROW | {"mrc_protected_usd": 0.0},
    LIVE_ROW | {"services_protected": 0},
])
def test_null_or_zero_hides_card(row):
    with pytest.raises(HTTPException) as exc:
        r.get_mrc_protected(config=_Cfg(True), csql=_Rows([row]))
    assert exc.value.status_code == 503


def test_empty_result_hides_card():
    with pytest.raises(HTTPException):
        r.get_mrc_protected(config=_Cfg(True), csql=_Rows([]))


def test_live_values_validate():
    out = MrcProtectedOut(**r.get_mrc_protected(config=_Cfg(True), csql=_Rows([LIVE_ROW])))
    assert out.services_protected == 4625
    assert f"${out.mrc_protected_usd / 1e6:.1f}M" == "$72.8M"
    assert f"{out.mrc_share * 100:.1f}%" == "57.8%"
    assert out.source == "mv_mrc_protected_v4_candidate"


def test_sql_uses_dedup_metric_view_not_action_sum():
    fake = _Rows([LIVE_ROW])
    fake.get_mrc_protected()
    assert "FROM mv_mrc_protected_v4_candidate" in fake.sql
    assert "MEASURE(`MRC Protected USD`)" in fake.sql
    assert "proactive_action" not in fake.sql  # no per-action fan-out ($76.45M bug)


def test_route_registered_before_action_id_route():
    paths = [getattr(rt, "path", "") for rt in r.router.routes]
    assert paths.index("/api/actions/mrc-protected") < paths.index("/api/actions/{action_id}")


# --- copy / brand -------------------------------------------------------

BANNED = re.compile(r"revenue (protected|at risk avoided|saved)", re.IGNORECASE)


def _source_files():
    for sub in ("ui", "backend"):
        for root, _dirs, files in os.walk(os.path.join(PKG, sub)):
            for name in files:
                if name.endswith((".ts", ".tsx", ".py", ".css", ".html", ".md")):
                    yield os.path.join(root, name)


def test_no_banned_strings_in_ui_or_backend():
    hits = []
    for path in _source_files():
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if BANNED.search(line):
                    hits.append(f"{path}:{i}")
    assert hits == []


def test_card_copy_and_brand():
    path = os.path.join(PKG, "ui", "components", "actions", "action-queue-table.tsx")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "MRC Protected" in text
    assert 'label="About MRC Protected"' in text
    assert "per month across" in text and "with at least one completed action" in text
    assert "Each service is counted once." in text
    assert "{v4Kpis && <MrcProtectedCard />}" in text
    assert "lumen" not in text.lower()
