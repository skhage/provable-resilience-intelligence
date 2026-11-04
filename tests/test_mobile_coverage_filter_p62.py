"""P62-APP-MOBILE-COVERAGE-FILTER: mobile topology tree (<768px) applies the Conduits coverage filter
and shows 'Inventory only: no span geometry' under PRI_V4_KPIS (V4-KPI-COPY-SPEC §3).

* Pure helpers (ui/lib/conduit-coverage-filter.ts) run in Node with type stripping (known answers).
* JSX / CSS wiring is checked statically (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
_LIB = os.path.join(UI, "lib", "conduit-coverage-filter.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")
INV_TEXT = "Inventory only: no span geometry"


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = ("import * as m from " + json.dumps("file://" + _LIB) + ";\nlet out;\n" + body + "\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _topology():
    return _read("routes", "topology.tsx")


def _mobile_block():
    src = _topology()
    start = src.index("function MobileTreeView(")
    end = src.index("// Main TopologyPage", start)
    return src[start:end]


def _page_block():
    src = _topology()
    return src[src.index("// Main TopologyPage"):]


# ---------- pure helpers (known answers) ----------

@needs_node
def test_inventory_only_suffix_known_answers():
    out = _node(
        "out = [m.inventoryOnlySuffix({span_coverage_class:'INVENTORY_ONLY'}),"
        " m.inventoryOnlySuffix({span_coverage_class:'REAL_SEGMENTED'}),"
        " m.inventoryOnlySuffix({span_coverage_class:'BB_SEGMENTED'}),"
        " m.inventoryOnlySuffix({span_coverage_class:null}), m.inventoryOnlySuffix({})];"
    )
    assert out == [" (" + INV_TEXT + ")", "", "", "", ""]


@needs_node
def test_loaded_conduits_scopes_to_given_regions():
    out = _node(
        "const d = {A:{conduits:[1,2]}, B:{conduits:[3]}, C: undefined};"
        "out = [m.loadedConduits(d), m.loadedConduits(d, new Set(['B'])),"
        " m.loadedConduits(d, new Set(['Z'])), m.loadedConduits(d, new Set(['C'])), m.loadedConduits({})];"
    )
    assert out == [[1, 2, 3], [3], [], [], []]


@needs_node
def test_mobile_scope_counts_and_visible_known_answer():
    # Two expanded regions + one collapsed. Default selection hides inventory-only unless pinned.
    out = _node(
        "const d = {"
        " East:{conduits:[{conduit_id:'a',span_coverage_class:'REAL_SEGMENTED'},"
        "                {conduit_id:'b',span_coverage_class:'INVENTORY_ONLY'},"
        "                {conduit_id:'c',span_coverage_class:'INVENTORY_ONLY'}]},"
        " West:{conduits:[{conduit_id:'d',span_coverage_class:'BB_SEGMENTED'},"
        "                {conduit_id:'e',span_coverage_class:null}]},"
        " South:{conduits:[{conduit_id:'f',span_coverage_class:'INVENTORY_ONLY'}]}};"
        "const scope = m.loadedConduits(d, new Set(['East','West']));"
        "const pinned = new Set(['c']);"
        "const vis = m.filterConduits(scope, m.DEFAULT_COVERAGE_SELECTION, pinned).map(x=>x.conduit_id);"
        "const all = m.filterConduits(scope, {segmented:true,backbone:true,inventory:true}, null).length;"
        "out = {counts: m.countByChip(scope), vis, status: m.coverageFilterStatus(vis.length, scope.length),"
        " all, gate: m.hasCoverageClasses(m.loadedConduits(d))};"
    )
    assert out["counts"] == {"segmented": 1, "backbone": 1, "inventory": 2}
    assert out["vis"] == ["a", "c", "d", "e"]  # b hidden; c pinned (traced hop); e unknown class kept
    assert out["status"] == "Showing 4 of 5 conduits."
    assert out["all"] == 5
    assert out["gate"] is True


@needs_node
def test_flag_off_rows_never_gate_chips():
    out = _node(
        "const d = {East:{conduits:[{conduit_id:'a',span_coverage_class:null},{conduit_id:'b'}]}};"
        "out = m.hasCoverageClasses(m.loadedConduits(d));"
    )
    assert out is False


# ---------- MobileTreeView wiring ----------

def test_mobile_chips_are_labelled_checkbox_group_gated_on_classes():
    blk = _mobile_block()
    assert "hasCoverageClasses(loadedConduits(regionData))" in blk
    assert "!!onToggleCoverage &&" in blk
    m = re.search(r'<div className="topo-coverage-chips mobile-tree-coverage" role="group" '
                  r'aria-labelledby="mobile-coverage-label">', blk)
    assert m, "mobile chip group missing"
    chips = blk[m.start():blk.index("</div>", m.start())]
    assert 'id="mobile-coverage-label"' in chips and "{COVERAGE_GROUP_LABEL}" in chips
    assert 'role="checkbox"' in chips and "aria-checked={coverageSelection[chip]}" in chips
    assert "chipLabel(chip, coverageCounts[chip])" in chips
    assert 'type="button"' in chips
    # chips render before the tree, after the search
    # (the tree is anchored on its aria-label: a code comment above also mentions role="tree")
    assert blk.index("mobile-tree-search-input") < m.start() < blk.index('aria-label="Network topology tree"')


def test_mobile_status_region_persistent_and_counts_expanded_scope():
    blk = _mobile_block()
    assert "loadedConduits(regionData, expandedRegions)" in blk
    i = blk.index("coverageFilterStatus(coverageVisibleCount, coverageScope.length)")
    pre = blk[blk.rfind("{showCoverage && (", 0, i):i]
    assert 'className="sr-only" role="status" aria-live="polite" aria-atomic="true"' in pre
    assert "filterConduits(coverageScope, coverageSelection, pinnedConduitIds).length" in blk


def test_tree_conduits_filtered_with_pins_only_when_chips_shown():
    blk = _mobile_block()
    fn = blk[blk.index("const conduitsForSite = useCallback("):]
    fn = fn[:fn.index("\n  );") + 5]  # the hook's closing paren, not the inner .filter(...)
    assert "showCoverage ? filterConduits(forSite, coverageSelection, pinnedConduitIds) : forSite" in fn
    assert "[regionData, showCoverage, coverageSelection, pinnedConduitIds]" in fn


def test_inventory_only_conduit_spoken_visible_and_in_modal():
    blk = _mobile_block()
    assert "${conduit.span_count} spans${inventoryOnlySuffix(conduit)}`}" in blk
    m = re.search(r'\{isInventoryOnly\(conduit\) && \(\s*<span className="mobile-tree-inv" aria-hidden="true">'
                  r'\s*\{INVENTORY_ONLY_TEXT\}\s*</span>', blk)
    assert m, "visible inventory-only cue missing"
    m2 = re.search(r"\{isInventoryOnly\(detailConduit\) && \(\s*<>\s*<dt>Coverage</dt>\s*"
                   r"<dd>\{INVENTORY_ONLY_TEXT\}</dd>", blk)
    assert m2, "modal coverage row missing"


def test_page_passes_shared_state_and_desktop_chips_off_on_mobile():
    page = _page_block()
    assert re.search(r"coverage=\{\s*showCoverage && selectedRegion && !isMobile", page)
    assert "{showCoverage && selectedRegion && !isMobile && (" in page
    mt = page[page.index("<MobileTreeView"):]
    mt = mt[:mt.index("/>")]
    for prop in ("coverageSelection={coverageSel}", "onToggleCoverage={handleToggleChip}",
                 "pinnedConduitIds={pinnedConduitIds}"):
        assert prop in mt
    # the desktop graph still receives the filtered list (P36 unchanged)
    assert "conduits={visibleConduits}" in page


def test_mobile_tree_props_declared_optional():
    src = _topology()
    props = src[src.index("interface MobileTreeProps {"):]
    props = props[:props.index("\n}\n")]
    assert "coverageSelection?: CoverageSelection;" in props
    assert "onToggleCoverage?: (chip: CoverageChip) => void;" in props
    assert "pinnedConduitIds?: ReadonlySet<string> | null;" in props


# ---------- CSS ----------

def _rule(css, selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def _rel_lum(hexc):
    rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted((_rel_lum(a), _rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_mobile_chip_css_target_and_colours():
    css = _read("styles", "lakelink-theme.css")
    base = _rule(css, ".mobile-tree-coverage .topo-chip")
    assert "min-height: 44px;" in base
    assert "border: 1px solid var(--lf-dark-teal);" in base and "color: var(--lf-dark-teal);" in base
    sel = _rule(css, '.mobile-tree-coverage .topo-chip[aria-checked="true"]')
    assert "background: var(--lf-dark-teal);" in sel and "color: var(--lf-white);" in sel
    focus = _rule(css, ".mobile-tree-coverage .topo-chip:focus-visible")
    assert "outline: 2px solid var(--lf-dark-teal);" in focus and "box-shadow: 0 0 0 2px var(--lf-white);" in focus
    assert re.search(r"\.mobile-tree-coverage \.topo-chip:focus-visible \{\s*outline-color: CanvasText;", css)
    # desktop chip rule untouched by P62
    desk = _rule(css, ".topo-toolbar .topo-chip")
    assert "min-height" not in desk and "padding: 6px 12px;" in desk


def test_inventory_cue_contrast_with_row_opacity():
    css = _read("styles", "lakelink-theme.css")
    inv = _rule(css, ".mobile-tree-inv")
    assert "color: var(--lf-iron);" in inv and "opacity" not in inv
    # conduit rows carry opacity 0.85: iron #4D4D4D composited on white
    row = re.findall(r"(?m)^\.mobile-tree-row--conduit \{([^}]*)\}", css)
    op = 1.0
    for body in row:
        mo = re.search(r"opacity:\s*([0-9.]+)", body)
        if mo:
            op = float(mo.group(1))
    ch = round(0x4D * op + 0xFF * (1 - op))
    eff = "#" + ("%02X" % ch) * 3
    assert _contrast(eff, "#FFFFFF") >= 4.5, (eff, _contrast(eff, "#FFFFFF"))
    assert any("flex-wrap: wrap;" in b for b in row)


def test_contrast_helper_known_answer():
    assert abs(_contrast("#000000", "#FFFFFF") - 21.0) < 1e-6
    assert abs(_contrast("#006272", "#FFFFFF") - 7.02) < 0.01


def test_branding_no_old_name_in_touched_files():
    for parts in (("lib", "conduit-coverage-filter.ts"), ("routes", "topology.tsx"),
                  ("styles", "lakelink-theme.css")):
        assert "lumen" not in _read(*parts).lower()
