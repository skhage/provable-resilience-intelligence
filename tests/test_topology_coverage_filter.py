"""P36-APP-V4-CONDUIT-COVERAGE-FILTER: /topology 'Conduits' coverage chips (V4-KPI-COPY-SPEC §3).

* Pure helpers in ui/lib/conduit-coverage-filter.ts are evaluated with Node (type stripping).
* JSX/CSS wiring is checked statically (no npm on serverless).
* Backend: flag off keeps the v3 query and call signature; flag on reads the v4 shadow tables.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
UI = os.path.join(APP_SRC, "resilience_scorecard", "ui")
_LIB = os.path.join(UI, "lib", "conduit-coverage-filter.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# Live Central region (v4 topology SQL, 2026-10-30): 16 REAL / 16 BB_SEGMENTED / 128 INVENTORY.
_CENTRAL = ([{"conduit_id": f"R{i}", "span_coverage_class": "REAL_SEGMENTED"} for i in range(16)]
            + [{"conduit_id": f"B{i}", "span_coverage_class": "BB_SEGMENTED"} for i in range(16)]
            + [{"conduit_id": f"I{i}", "span_coverage_class": "INVENTORY_ONLY"} for i in range(128)])


# --- pure helpers ----------------------------------------------------------------

@needs_node
@pytest.mark.parametrize("cls,chip", [
    ("REAL_SEGMENTED", "segmented"), ("BB_SEGMENTED", "backbone"), ("BB_ONLY", "backbone"),
    ("INVENTORY_ONLY", "inventory"), (None, None), ("NEW_CLASS", None), ("toString", None),
])
def test_chip_for_class(cls, chip):
    assert _node(f"out = m.chipForClass({json.dumps(cls)});") == chip


@needs_node
def test_default_is_geometry_only_and_counts_known_answer():
    out = _node(f"const c = {json.dumps(_CENTRAL)};"
                "out = [m.DEFAULT_COVERAGE_SELECTION, m.countByChip(c),"
                " m.filterConduits(c, m.DEFAULT_COVERAGE_SELECTION).length,"
                " m.coverageFilterStatus(m.filterConduits(c, m.DEFAULT_COVERAGE_SELECTION).length, c.length)];")
    sel, counts, n, status = out
    assert sel == {"segmented": True, "backbone": True, "inventory": False}
    assert counts == {"segmented": 16, "backbone": 16, "inventory": 128}
    assert n == 32  # 16 + 16, inventory hidden by default
    assert status == "Showing 32 of 160 conduits."


@needs_node
def test_chip_labels_use_thousands_separator():
    out = _node("out = [m.chipLabel('segmented', 55), m.chipLabel('backbone', 92),"
                " m.chipLabel('inventory', 1824), m.COVERAGE_GROUP_LABEL];")
    assert out == ["Segmented (55)", "Backbone only (92)", "Inventory only (1,824)", "Conduits"]


@needs_node
def test_pinned_and_unknown_never_hidden():
    out = _node("const none = {segmented:false, backbone:false, inventory:false};"
                "const rows = [{conduit_id:'I1', span_coverage_class:'INVENTORY_ONLY'},"
                " {conduit_id:'X', span_coverage_class:null}, {conduit_id:'R1', span_coverage_class:'REAL_SEGMENTED'}];"
                "out = m.filterConduits(rows, none, new Set(['I1'])).map(r => r.conduit_id);")
    assert out == ["I1", "X"]


@needs_node
def test_flag_off_rows_are_not_filtered():
    # v3 API rows carry span_coverage_class null -> no chips, nothing hidden
    out = _node("const rows = [{conduit_id:'A', span_coverage_class:null}, {conduit_id:'B'}];"
                "out = [m.hasCoverageClasses(rows), m.filterConduits(rows, m.DEFAULT_COVERAGE_SELECTION).length];")
    assert out == [False, 2]


@needs_node
def test_toggle_is_immutable_and_spec_constants():
    out = _node("const s = m.DEFAULT_COVERAGE_SELECTION; const t = m.toggleChip(s, 'inventory');"
                "out = [s.inventory, t.inventory, t.segmented, m.INVENTORY_ONLY_DASH, m.INVENTORY_ONLY_TEXT,"
                " m.coverageFilterStatus(1, 1), m.coverageFilterStatus(1200, 1500)];")
    assert out == [False, True, True, "2,4", "Inventory only: no span geometry",
                   "Showing 1 of 1 conduit.", "Showing 1,200 of 1,500 conduits."]


# --- JSX / CSS wiring (static) ---------------------------------------------------

def test_chips_are_role_checkbox_in_labelled_group():
    src = _read("routes", "topology.tsx")
    block = src[src.index('className="topo-coverage-chips"'):]
    block = block[:block.index("</div>")]
    assert 'role="group"' in block and 'aria-labelledby="topo-coverage-label"' in block
    assert 'role="checkbox"' in block and "aria-checked={coverage.selection[chip]}" in block
    assert 'type="button"' in block
    # non-colour selected cue is aria-hidden (name stays "Segmented (16)")
    assert re.search(r'className="topo-chip-check" aria-hidden="true"', block)


def test_chips_gated_on_api_classes_and_graph_gets_filtered_list():
    src = _read("routes", "topology.tsx")
    assert "const showCoverage = hasCoverageClasses(conduits);" in src
    assert re.search(r"coverage=\{\s*showCoverage && selectedRegion", src)
    assert re.search(r"<SiteGraph\s+sites=\{sites\}\s+conduits=\{visibleConduits\}", src)
    # path hops + selected conduit are pinned
    assert "for (const h of pathHops) if (h.conduit_id) ids.add(h.conduit_id);" in src
    # persistent result count lives outside the graph
    assert "coverageFilterStatus(visibleConduits.length, conduits.length)" in src


def test_inventory_edge_dotted_iron_with_text():
    src = _read("routes", "topology.tsx")
    assert "if (!dashArray) dashArray = INVENTORY_ONLY_DASH;" in src
    assert "edgeColor = BRAND.iron;" in src
    assert '{invOnly ? ` \u00b7 ${INVENTORY_ONLY_TEXT}` : ""}' in src  # <title> hover text
    assert '${invOnly ? ` (${INVENTORY_ONLY_TEXT})` : ""}' in src     # aria-label
    assert "showInventoryOnly={showCoverage && coverageSel.inventory}" in src


def test_chip_css_selected_teal_fill_white_text_beats_hover():
    css = _read("styles", "lakelink-theme.css")
    sel = re.search(r'\.topo-toolbar \.topo-chip\[aria-checked="true"\] \{([^}]*)\}', css).group(1)
    assert "background: var(--lf-dark-teal)" in sel and "color: var(--lf-white)" in sel
    base = re.search(r"(?m)^\.topo-toolbar \.topo-chip \{([^}]*)\}", css).group(1)
    assert "border: 1px solid var(--lf-dark-teal)" in base and "color: var(--lf-dark-teal)" in base
    # (0,3,0) selected rule must outrank the (0,2,1) `.topo-toolbar button:hover` rule
    assert ".topo-toolbar button:hover" in css
    assert re.search(r'forced-colors: active\)[^@]*\.topo-chip\[aria-checked="true"\][^}]*Highlight', css)


# --- backend ---------------------------------------------------------------------

if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)


def _backend():
    from resilience_scorecard.backend import router as rt
    from resilience_scorecard.backend.services import catalog_sql as cs
    return rt, cs


def test_v3_sql_untouched_and_v4_sql_reads_shadow_tables():
    _, cs = _backend()
    v3, v4 = cs._TOPOLOGY_CONDUITS_SQL, cs._TOPOLOGY_CONDUITS_V4_SQL
    assert "_v4_candidate" not in v3 and "span_coverage_class" not in v3
    assert "FROM physical_resource_conduit_v4_candidate c" in v4
    assert "FROM physical_resource_span_v4_candidate" in v4
    assert "c.span_coverage_class" in v4
    # identical filters / parameter binding (no inlined region)
    for clause in ("(sa.region = :region OR sz.region = :region)", "sa.tier IN ('tier_1', 'tier_2')",
                   "sz.tier IN ('tier_1', 'tier_2')", "WHERE c.is_active = TRUE"):
        assert clause in v3 and clause in v4


class _FakeCsql:
    is_available = True

    def __init__(self):
        self.calls = []

    def get_topology_conduits(self, region, **kw):
        self.calls.append((region, kw))
        return [{"conduit_id": "C1"}]


@pytest.mark.parametrize("flag,expected_kw", [(False, {}), (True, {"v4": True})])
def test_router_passes_flag(flag, expected_kw):
    rt, _ = _backend()
    fake = _FakeCsql()
    out = rt.list_topology_conduits(fake, SimpleNamespace(v4_kpis=flag), region="Central")
    assert out == [{"conduit_id": "C1"}]
    assert fake.calls == [("Central", expected_kw)]


def test_service_selects_sql_by_flag():
    _, cs = _backend()
    svc = object.__new__(cs.CatalogSqlService)
    seen = []
    svc._execute = lambda sql, row_limit=None, params=None: (seen.append((sql, params)) or [
        {"span_count": "3", "backbone_span_count": None, "length_km": "1.5", "span_coverage_class": "BB_SEGMENTED"}])
    rows = svc.get_topology_conduits("East", v4=True)
    svc.get_topology_conduits("East")
    assert seen[0] == (cs._TOPOLOGY_CONDUITS_V4_SQL, {"region": "East"})
    assert seen[1] == (cs._TOPOLOGY_CONDUITS_SQL, {"region": "East"})
    assert rows[0]["span_count"] == 3 and rows[0]["backbone_span_count"] == 0
    assert rows[0]["span_coverage_class"] == "BB_SEGMENTED"
