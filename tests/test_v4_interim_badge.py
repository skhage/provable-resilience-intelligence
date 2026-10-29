"""P41-APP-V4-INTERIM-BADGE: report_status API field, Interim badge, (metro/access), §6.4 formatting.

Spec: apps/V4-KPI-COPY-SPEC.md §6.2-6.4. Gated by PRI_V4_KPIS (default false).
Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

APP_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
)
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend import router as r  # noqa: E402
from resilience_scorecard.backend.core import AppConfig  # noqa: E402
from resilience_scorecard.backend.models import ResilienceSummaryOut  # noqa: E402
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

PKG = os.path.join(APP_SRC, "resilience_scorecard")
UI = os.path.join(PKG, "ui")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


class _Cfg:
    def __init__(self, v4, status="auto"):
        self.v4_kpis = v4
        self.bb_srlg_coverage = "auto"
        self.v4_report_status = status


class _Unavailable:
    is_available = False


class _Live:
    """Stub CatalogSqlService returning a fixed report_status row."""
    is_available = True

    def __init__(self, status="INTERIM", fail=False, empty=False):
        self.status, self.fail, self.empty = status, fail, empty

    def _execute(self, sql, row_limit=12000, params=None):
        if "bb_uncovered_spans" in sql:
            return [{"bb_active_spans": 92, "bb_uncovered_spans": 92}]
        if "kpi_delta_attribution_v4_candidate" in sql:
            if self.fail:
                raise RuntimeError("warehouse down")
            return [] if self.empty else [{"report_status": self.status}]
        return []

    def get_summary(self):
        return {
            "total_services": 8000, "avg_resilience_score": 61.55, "critical_count": 848,
            "high_risk_count": 1, "medium_risk_count": 1, "low_risk_count": 1,
            "total_single_point_failures": 0, "total_srlg_groups": 931,
            "total_revenue_at_risk_usd": 48445093.0,
        }

    def get_bb_srlg_coverage(self):
        return cs.CatalogSqlService.get_bb_srlg_coverage(self)

    def get_v4_report_status(self):
        return cs.CatalogSqlService.get_v4_report_status(self)


# --- config + API ---------------------------------------------------------

def test_report_status_override_defaults_auto(monkeypatch):
    monkeypatch.delenv("PRI_V4_REPORT_STATUS", raising=False)
    monkeypatch.delenv("RESILIENCE_SCORECARD_V4_REPORT_STATUS", raising=False)
    assert AppConfig().v4_report_status == "auto"


def test_report_status_override_reads_env(monkeypatch):
    monkeypatch.setenv("PRI_V4_REPORT_STATUS", "FINAL")
    assert AppConfig().v4_report_status == "FINAL"


def test_flag_off_summary_has_no_report_status():
    out = r.get_resilience_summary(_Live(), _Cfg(False))
    assert "report_status" not in out
    assert ResilienceSummaryOut(**out).report_status is None


@pytest.mark.parametrize("status", ["INTERIM", "FINAL"])
def test_flag_on_reads_report_status_from_table(status):
    out = r.get_resilience_summary(_Live(status=status), _Cfg(True))
    assert ResilienceSummaryOut(**out).report_status == status


@pytest.mark.parametrize("stub", [_Live(fail=True), _Live(empty=True), _Live(status=None), _Unavailable()])
def test_unknown_status_is_conservative_interim(stub):
    assert r.get_resilience_summary(stub, _Cfg(True))["report_status"] == "INTERIM"


@pytest.mark.parametrize("override,expected", [("final", "FINAL"), ("INTERIM", "INTERIM")])
def test_env_override_wins(override, expected):
    assert r._resolve_v4_report_status(_Cfg(True, override), _Live(status="INTERIM" if expected == "FINAL" else "FINAL")) == expected


def test_report_status_sql_final_only_when_all_rows_final():
    sql = cs._V4_REPORT_STATUS_SQL
    assert "FROM kpi_delta_attribution_v4_candidate" in sql
    assert "COUNT_IF(UPPER(TRIM(report_status)) = 'FINAL') = COUNT(*) THEN 'FINAL'" in sql
    assert "ELSE 'INTERIM'" in sql


# --- UI source contracts --------------------------------------------------

def test_badge_copy_verbatim_from_spec():
    t = _read("lib", "v4-delta-format.ts")
    assert '"Interim figure, v4 candidate, subject to change"' in t
    assert ("Preliminary v4 figures. Only the hazard-distance fix is included so far. Backbone "
            "segmentation and shared-risk updates are still being scored, so these numbers will change.") in t
    b = _read("components", "ui", "interim-badge.tsx")
    assert 'role="img" aria-label={INTERIM_ARIA}' in b
    assert "<InfoTooltip" in b  # reuses DW-092 hover bridge


def test_header_badge_on_three_cards_only_and_v3_markup_preserved():
    t = _read("components", "dashboard", "scorecard-header.tsx")
    assert "const interim = showInterimBadge(v4Kpis, summary.report_status);" in t
    assert t.count("<InterimBadge />") == 3
    for label in ("Avg Resilience Score", "Critical Risk", "Revenue at Risk"):
        assert f'<div className="kpi-label">{label}</div>' in t  # v3 branch untouched
        assert f"<span>{label}</span>\n" in t
    # flag-off formatting falls back to the v3 expressions
    assert "v4Kpis ? formatScore(summary.avg_resilience_score) : summary.avg_resilience_score.toFixed(1)" in t
    assert "v4Kpis ? formatKpiCount(summary.critical_count) : summary.critical_count" in t
    # never on MRC Protected / the other cards
    seg = t[t.index("<span>Revenue at Risk</span>"):]
    assert "<InterimBadge />" in seg[:120]
    assert '"INTERIM"' not in t  # status is never hard-coded in the component


def test_badge_css_brand_rules():
    css = _read("styles", "lakelink-theme.css")
    blk = css[css.index(".interim-badge {"):]
    blk = blk[: blk.index("}")]
    for rule in ("border: 1px solid #4D4D4D;", "border-left: 3px solid #F26522;", "border-radius: 4px;",
                 "background: #E8E8E8;", "color: #4D4D4D;", "font-size: 12px;", "font-weight: 600;",
                 "text-transform: uppercase;"):
        assert rule in blk, rule
    assert "color: #F26522" not in css[css.index("P41-APP-V4-INTERIM-BADGE"):]
    assert ".v4-delta {\n  color: #4D4D4D;" in css


def test_service_table_srlg_qualifier_gated():
    t = _read("components", "dashboard", "service-table.tsx")
    assert "const bbCoverage = useBbSrlgCoverage();" in t
    assert '{bbCoverage === "partial" && (' in t
    assert '<span aria-hidden="true">{`\\u00A0${METRO_ACCESS}`}</span>' in t
    assert '<span className="sr-only">{` ${METRO_ACCESS_SPOKEN}`}</span>' in t


def test_no_lumen_in_ui_or_backend():
    hits = []
    for sub in ("ui", "backend"):
        for root, _, files in os.walk(os.path.join(PKG, sub)):
            for fn in files:
                if fn.endswith((".ts", ".tsx", ".py", ".css")):
                    p = os.path.join(root, fn)
                    with open(p, encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if "lumen" in line.lower():  # CEO branding mandate: zero occurrences
                                hits.append(f"{p}:{i}")
    assert hits == [], hits


# --- §6.4 formatting, evaluated against the real TS module ----------------

NODE = shutil.which("node")
_LIB = os.path.join(UI, "lib", "v4-delta-format.ts")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _node(expr):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};"
          f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run([NODE, "--input-type=module", "-e", js],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@needs_node
@pytest.mark.parametrize("expr,expected", [
    ("m.formatScore(61.55)", "61.6"),
    ("m.formatScore(56.77)", "56.8"),
    ("m.formatDelta('score', 61.55, 56.77)", "\u22124.8"),
    ("m.formatKpiCount(1087)", "1,087"),
    ("m.formatDelta('count', 848, 1087)", "+239"),
    ("m.formatMoneyPerMonth(48445093)", "$48.4M/mo"),
    ("m.formatMoneyPerMonth(54440037)", "$54.4M/mo"),
    ("m.formatDelta('money', 48445093, 54440037)", "+$6.0M/mo"),
    ("m.formatDelta('percent', 74.19, 74.19)", "no change"),
    ("m.roundHalfUp(-4.75, 1)", -4.8),
    ("m.roundHalfUp(-0.04, 1)", 0),
])
def test_spec_6_4_examples(expr, expected):
    assert _node(expr) == expected


@needs_node
def test_transition_arrow_and_spoken_to():
    t = _node("m.deltaTransition('Average score', 'score', 61.55, 56.77, true)")
    assert t["text"] == "61.6 \u2192 56.8"
    assert t["aria"] == "Average score 61.6 to 56.8, interim"
    assert t["delta"] == "\u22124.8"


@needs_node
def test_show_interim_badge_truth_table():
    got = _node("[m.showInterimBadge(false,'INTERIM'), m.showInterimBadge(true,'INTERIM'), "
                "m.showInterimBadge(true,'FINAL'), m.showInterimBadge(true,null)]")
    assert got == [False, True, False, False]
