"""P36-APP-V4-BB-SRLG-DISCLOSURE: bb_srlg_coverage state, crosses_backbone, backbone edges, UI copy.

Spec: apps/V4-KPI-COPY-SPEC.md §2, §6.3, §6.4. Gated by PRI_V4_KPIS (default false).
Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import re
import sys

import pytest

APP_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src")
)
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend import router as r  # noqa: E402
from resilience_scorecard.backend.core import AppConfig  # noqa: E402
from resilience_scorecard.backend.models import (  # noqa: E402
    ResilienceSummaryOut,
    ServiceDiversityOut,
    TopologyConduitOut,
)
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

UI = os.path.join(APP_SRC, "resilience_scorecard", "ui")


class _Cfg:
    def __init__(self, v4, bb="auto"):
        self.v4_kpis = v4
        self.bb_srlg_coverage = bb


class _Unavailable:
    is_available = False


class _Live:
    """Stub CatalogSqlService: summary row + backbone span coverage counts (BUG-QA-083).

    bb_spans = active BB-*/BBS-* spans; uncovered = those with no SRLG row. Defaults mirror
    live v3 (2026-10-29): 92 active backbone spans, all 92 uncovered.
    """
    is_available = True

    def __init__(self, bb_spans=92, uncovered=92, fail_bb=False, null_row=False):
        self.bb_spans = bb_spans
        self.uncovered = uncovered
        self.fail_bb = fail_bb
        self.null_row = null_row
        self.sql = []

    def _execute(self, sql, row_limit=12000, params=None):
        self.sql.append(sql)
        if "bb_uncovered_spans" in sql:
            if self.fail_bb:
                raise RuntimeError("warehouse down")
            if self.null_row:
                return [{"bb_active_spans": None, "bb_uncovered_spans": None}]
            return [{"bb_active_spans": self.bb_spans, "bb_uncovered_spans": self.uncovered}]
        return []

    def get_summary(self):
        return {
            "total_services": 8000, "avg_resilience_score": 61.6, "critical_count": 848,
            "high_risk_count": 1, "medium_risk_count": 1, "low_risk_count": 1,
            "total_single_point_failures": 0, "total_srlg_groups": 809,
            "total_revenue_at_risk_usd": 48.4e6,
        }

    def get_bb_srlg_coverage(self):
        return cs.CatalogSqlService.get_bb_srlg_coverage(self)


# --- config ---------------------------------------------------------------

def test_override_defaults_auto(monkeypatch):
    monkeypatch.delenv("PRI_BB_SRLG_COVERAGE", raising=False)
    monkeypatch.delenv("RESILIENCE_SCORECARD_BB_SRLG_COVERAGE", raising=False)
    assert AppConfig().bb_srlg_coverage == "auto"


def test_override_reads_env(monkeypatch):
    monkeypatch.setenv("PRI_BB_SRLG_COVERAGE", "complete")
    assert AppConfig().bb_srlg_coverage == "complete"


# --- summary state ----------------------------------------------------------

def test_flag_off_summary_has_no_coverage_field():
    out = r.get_resilience_summary(csql=_Live(), config=_Cfg(False))
    assert "bb_srlg_coverage" not in out
    assert ResilienceSummaryOut(**out).bb_srlg_coverage is None


def test_v3_data_reports_partial():
    # Live v3: 92 active BB-* spans, 0 BB SRLG rows -> all 92 uncovered (2026-10-29)
    out = r.get_resilience_summary(csql=_Live(bb_spans=92, uncovered=92), config=_Cfg(True))
    assert out["bb_srlg_coverage"] == "partial"


def test_all_backbone_spans_covered_report_complete():
    out = r.get_resilience_summary(csql=_Live(bb_spans=5325, uncovered=0), config=_Cfg(True))
    assert ResilienceSummaryOut(**out).bb_srlg_coverage == "complete"


# BUG-QA-083: a partial backfill must never report 'complete' (would drop every caveat).
@pytest.mark.parametrize("bb_spans,uncovered", [
    (5325, 5324),   # 1 of 5,325 BBS spans covered (QA example)
    (5325, 1),      # one straggler left uncovered
    (92, 91),
])
def test_partial_backfill_reports_partial(bb_spans, uncovered):
    out = r.get_resilience_summary(csql=_Live(bb_spans=bb_spans, uncovered=uncovered),
                                   config=_Cfg(True))
    assert out["bb_srlg_coverage"] == "partial"


def test_no_backbone_spans_is_not_proof_of_coverage():
    # 0 active BB spans -> nothing proven; stay conservative
    out = r.get_resilience_summary(csql=_Live(bb_spans=0, uncovered=0), config=_Cfg(True))
    assert out["bb_srlg_coverage"] == "partial"


def test_service_method_states():
    svc = cs.CatalogSqlService.get_bb_srlg_coverage
    assert svc(_Live(bb_spans=10, uncovered=0)) == "complete"
    assert svc(_Live(bb_spans=10, uncovered=3)) == "partial"
    assert svc(_Live(bb_spans=0, uncovered=0)) == "partial"
    assert svc(_Live(null_row=True)) is None


@pytest.mark.parametrize("csql", [_Unavailable(), _Live(fail_bb=True), _Live(null_row=True)])
def test_unknown_is_partial_never_complete(csql):
    out = r.get_resilience_summary(csql=csql, config=_Cfg(True))
    assert out["bb_srlg_coverage"] == "partial"


@pytest.mark.parametrize("override,uncovered,expected", [
    ("partial", 0, "partial"),
    ("complete", 92, "complete"),
    ("AUTO", 0, "complete"),
    ("AUTO", 1, "partial"),
    ("bogus", 92, "partial"),
])
def test_env_override(override, uncovered, expected):
    out = r.get_resilience_summary(csql=_Live(bb_spans=92, uncovered=uncovered),
                                   config=_Cfg(True, override))
    assert out["bb_srlg_coverage"] == expected


def test_coverage_sql_counts_backbone_spans_in_app_srlg_table():
    sql = cs._BB_SRLG_COVERAGE_SQL
    assert "FROM shared_risk_group" in sql and "span_id LIKE 'BB%'" in sql
    # BUG-QA-083: anti-join from active backbone spans, not a bare SRLG row count
    assert "FROM physical_resource_span" in sql and "is_active = TRUE" in sql
    assert "LEFT JOIN" in sql and "cov.span_id IS NULL" in sql
    assert "AS bb_active_spans" in sql and "AS bb_uncovered_spans" in sql
    assert "bb_srlg_rows" not in sql


# --- diversity + conduits ---------------------------------------------------

def test_diversity_sql_and_model_carry_crosses_backbone():
    assert "AS crosses_backbone" in cs._SERVICE_DIVERSITY_SQL
    m = ServiceDiversityOut(service_id="S", diversity_status="fully_diverse", working_hops=3,
                            protect_hops=4, working_conduits=2, protect_conduits=2,
                            shared_srlg_count=0, crosses_backbone=True)
    assert m.crosses_backbone is True
    assert ServiceDiversityOut(**(m.model_dump() | {"crosses_backbone": None})).crosses_backbone is None


def test_topology_conduits_identify_backbone_by_span_not_conduit_prefix():
    sql = cs._TOPOLOGY_CONDUITS_SQL
    assert "backbone_span_count" in sql and "span_id LIKE 'BB%'" in sql
    assert "conduit_id LIKE" not in sql
    c = TopologyConduitOut(conduit_id="CDT-MT-1", conduit_type="underground", length_km=1,
                           site_a_id="A", site_z_id="Z", span_count=1)
    assert c.backbone_span_count == 0  # backward compatible default


# --- UI copy / gating -------------------------------------------------------

def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def test_disclosure_copy_verbatim():
    t = _read("lib", "bb-srlg-disclosure.ts")
    for s in (
        "Backbone (BB-*) routes are modeled at long-haul grain. Their shared-risk groups ship in a "
        "later build, so diversity on backbone hops is not yet verified.",
        "Groups of spans that share a physical risk, such as a conduit, bridge or central office.",
        '"Metro/access spans only"', '"Metro, access and backbone"',
        "Coverage: metro/access spans. Backbone not yet included.",
        "Backbone span: shared-risk data not available", '"Backbone unverified"',
        '"(metro/access)"', "\\u00A0",
    ):
        assert s in t, s


def test_header_v3_card_preserved_and_v4_card_gated():
    t = _read("components", "dashboard", "scorecard-header.tsx")
    # v3 freeze markup is untouched in the flag-off branch
    assert '<div className="kpi-label">SRLG Groups</div>' in t
    assert 'aria-label={`SRLG Groups: ${summary.total_srlg_groups}`}' in t
    assert "{v4Kpis ? (" in t and "<SrlgGroupsV4Card" in t
    assert "SRLG Groups: ${n}, metro and access spans only" in t
    assert 'label="About SRLG Groups"' in t


def test_topology_surfaces_are_gated_on_coverage():
    t = _read("routes", "topology.tsx")
    assert 'bbCoverage === "partial" && (\n          <p className="legend-coverage-note">' in t
    assert 'if (bbCoverage === "partial" && isBackboneOnly(c)) return null;' in t
    # BUG-DW-096: caveat precedes the instruction; describedby dropped on caveat edges
    assert "aria-label={conduitEdgeName(" in t
    assert "aria-describedby={conduitEdgeDescribedBy(c.conduit_id, bbPartial)}" in t
    assert "Press Enter for details.${bbPartial" not in t
    assert "showBackboneUnverified(bbCoverage" in t
    assert t.count("bbCoverage={bbCoverage}") == 5  # banner, graph, mobile, legend, edge panel
    assert "const bbCoverage = useBbSrlgCoverage();" in t


def test_hook_returns_null_when_flag_off():
    t = _read("lib", "api.ts")
    body = t[t.index("export function useBbSrlgCoverage"):]
    body = body[: body.index("\n}\n")]
    assert "if (!v4Kpis) return null;" in body
    assert 'bb_srlg_coverage === "complete" ? "complete" : "partial"' in body
    assert '["getResilienceSummary", {}]' in body


# --- BUG-DW-096: panel/map consistency + single caveat announcement --------

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

NODE = shutil.which("node")
_LIB = os.path.join(UI, "lib", "bb-srlg-disclosure.ts")


def _node(expr):
    """Evaluate a JS expression against the real TS module (Node >= 22.18 strips types)."""
    js = (f"import * as m from {json.dumps('file://' + _LIB)};"
          f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run([NODE, "--input-type=module", "-e", js],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")
BB_ONLY = "{span_count: 3, backbone_span_count: 3}"
MIXED = "{span_count: 3, backbone_span_count: 1}"
METRO = "{span_count: 3, backbone_span_count: 0}"
CAVEAT = "Backbone span: shared-risk data not available"


@needs_node
@pytest.mark.parametrize("cov,edge,expected", [
    ("'partial'", BB_ONLY, "caveat-only"),
    ("'partial'", MIXED, "qualified"),
    ("'partial'", METRO, "list"),
    ("'complete'", BB_ONLY, "list"),
    ("null", BB_ONLY, "list"),  # flag off: v3
    ("null", MIXED, "list"),
])
def test_panel_srlg_mode(cov, edge, expected):
    assert _node(f"m.panelSrlgMode({cov}, {edge})") == expected


def test_panel_hides_srlg_list_for_backbone_only_and_qualifies_mixed():
    t = _read("routes", "topology.tsx")
    assert "const srlgMode = panelSrlgMode(bbCoverage, conduit);" in t
    assert '{srlgGroups.length > 0 && srlgMode !== "caveat-only" && (' in t
    assert '{srlgMode === "qualified" && (' in t
    assert '<span aria-hidden="true">{`\\u00A0${METRO_ACCESS}`}</span>' in t
    assert '<span className="sr-only">{` ${METRO_ACCESS_SPOKEN}`}</span>' in t
    # caveat paragraph still rendered for any backbone conduit while partial
    assert 'bbCoverage === "partial" && hasBackboneSpans(conduit) && (' in t


@needs_node
def test_edge_name_caveat_before_instruction_with_period():
    name = _node("m.conduitEdgeName('Conduit C1: aerial, 2 km, 3 spans', true)")
    assert name == f"Conduit C1: aerial, 2 km, 3 spans. {CAVEAT}. Press Enter for details."


@needs_node
def test_edge_name_flag_off_is_v3_string():
    base = "Conduit C1: aerial, 2 km, 3 spans (SRLG: Shared conduit - high)"
    assert _node(f"m.conduitEdgeName({json.dumps(base)}, false)") == f"{base}. Press Enter for details."


@needs_node
def test_caveat_announced_exactly_once():
    """Computed name + description: the <title> (which repeats the caveat) is not referenced."""
    got = _node("[m.conduitEdgeName('Conduit C1', true), m.conduitEdgeDescribedBy('C1', true) ?? null,"
                " m.conduitEdgeDescribedBy('C1', false)]")
    name, described_partial, described_v3 = got
    title_text = f"C1: aerial · 2 km · 3 spans · {CAVEAT}"  # mirrors <title> markup
    description = title_text if described_partial else ""
    assert (name + " " + description).count(CAVEAT) == 1
    assert described_v3 == "conduit-desc-C1"  # flag off / no backbone: unchanged


BANNED_BB = re.compile(r"no shared risk|0 SRLGs", re.IGNORECASE)


def test_never_claims_no_shared_risk():
    hits = []
    for root, _d, files in os.walk(UI):
        for name in files:
            if name.endswith((".ts", ".tsx")):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if BANNED_BB.search(line) and "Never" not in line:
                            hits.append(f"{name}:{i}")
    assert hits == []


def test_no_customer_real_name_in_new_files():
    for parts in (("lib", "bb-srlg-disclosure.ts"), ("routes", "topology.tsx"),
                  ("components", "dashboard", "scorecard-header.tsx")):
        assert "lumen" not in _read(*parts).lower()
