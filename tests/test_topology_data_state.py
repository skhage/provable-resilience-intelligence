"""BUG-DW-098: /topology distinguishes live-unavailable from not-found and no-data.

Pure helpers in ui/lib/topology-data-state.ts are evaluated with Node (>= 22.18 strips
TS types). JSX wiring in routes/topology.tsx is checked statically (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _node(body):
    """Run an ES module body with `m` = the real TS module; body must set `out`."""
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- classifyResponse ---------------------------------------------------------

@needs_node
@pytest.mark.parametrize("status,header,expected", [
    (200, "live", "live"),
    (200, None, "live"),                # older backend / no header: v3 render
    (200, "unavailable", "unavailable"),  # path-trace / srlgs outage = 200 + []
    (200, "Unavailable", "unavailable"),
    (503, "unavailable", "unavailable"),  # diversity outage
    (503, None, "unavailable"),
    (500, None, "unavailable"),
    (404, None, "not_found"),            # diversity: service genuinely absent
    (401, None, "auth_expired"),          # BUG-DW-106 item 4
    (403, "unavailable", "auth_expired"),  # auth wins over the outage header
    (400, None, "unavailable"),
])
def test_classify_response(status, header, expected):
    assert _node(f"out = m.classifyResponse({status}, {json.dumps(header)});") == expected


# --- fetchWithState with a mocked fetch -----------------------------------------

def _mock_fetch(status, header, body):
    return (
        "globalThis.fetch = async () => ({ status: %d, headers: { get: (k) => k === 'X-PRI-Data-Source' ? %s : null },"
        " json: async () => (%s) });" % (status, json.dumps(header), json.dumps(body))
    )


@needs_node
def test_fetch_unavailable_header_drops_data():
    out = _node(_mock_fetch(200, "unavailable", []) + "out = await m.fetchWithState('/x');")
    assert out == {"state": "unavailable", "data": None}


@needs_node
def test_fetch_live_returns_data():
    hops = [{"path_type": "working"}]
    out = _node(_mock_fetch(200, "live", hops) + "out = await m.fetchWithState('/x');")
    assert out == {"state": "live", "data": hops}


@needs_node
def test_fetch_503_and_404_differ():
    a = _node(_mock_fetch(503, "unavailable", {"detail": "x"}) + "out = await m.fetchWithState('/x');")
    b = _node(_mock_fetch(404, None, {"detail": "x"}) + "out = await m.fetchWithState('/x');")
    assert a["state"] == "unavailable" and b["state"] == "not_found"
    assert a["data"] is None and b["data"] is None


@needs_node
def test_fetch_network_error_is_unavailable():
    out = _node("globalThis.fetch = async () => { throw new Error('net'); };"
                "out = await m.fetchWithState('/x');")
    assert out == {"state": "unavailable", "data": None}


# --- banner mode + copy -----------------------------------------------------------

@needs_node
@pytest.mark.parametrize("path,div,expected", [
    (None, None, "pending"),
    ("live", None, "pending"),
    ("live", "live", "live"),
    ("unavailable", "live", "unavailable"),
    ("live", "unavailable", "unavailable"),
    ("unavailable", "unavailable", "unavailable"),
    ("live", "not_found", "not_found"),
    ("unavailable", "not_found", "not_found"),
])
def test_trace_banner_mode(path, div, expected):
    assert _node(f"out = m.traceBannerMode({json.dumps(path)}, {json.dumps(div)});") == expected


@needs_node
def test_banner_copy_503_vs_404():
    out = _node("out = [m.traceBannerMessage('unavailable','SVC-00001'),"
                " m.traceBannerMessage('not_found','SVC-99999'),"
                " m.traceBannerMessage('live','SVC-00001'), m.traceBannerMessage('pending','SVC-00001')];")
    assert out == ["Path data is temporarily unavailable.", "Service SVC-99999 not found.", None, None]
    assert "protect" not in out[0].lower() and "protect" not in out[1].lower()


@needs_node
def test_srlg_unavailable_line():
    out = _node("out = [m.showSrlgUnavailable(true,'West','unavailable'), m.showSrlgUnavailable(true,'West','live'),"
                " m.showSrlgUnavailable(false,'West','unavailable'), m.showSrlgUnavailable(true,null,'unavailable'),"
                " m.srlgUnavailableMsg('West')];")
    assert out == [True, False, False, False, "SRLG data unavailable for West."]


# --- JSX wiring (static) -------------------------------------------------------------

def _banner_nonlive_block(src):
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC \u00a72.1: diverse services", start)
    return src[start:end]


def test_nonlive_banner_has_no_badge_no_hop_stats_but_retry_and_clear():
    blk = _banner_nonlive_block(_read("routes", "topology.tsx"))
    assert "diversity-badge" not in blk
    assert "path-trace-stats" not in blk and "protect" not in blk.lower()
    # BUG-DW-105: role="status" moved to a persistent sr-only region outside PathTraceBanner
    # The non-live block now uses aria-busy on the container instead
    # BUG-DW-113 item 2: the Retry gate is the shared showTraceRetry(mode) helper
    assert "path-trace-retry" in blk and "showTraceRetry(mode)" in blk
    assert "Clear trace" in blk


def test_fetches_read_header_not_raw_json():
    src = _read("routes", "topology.tsx")
    assert re.search(r"fetchWithState<PathHop\[\]>\(`/api/topology/path-trace/", src)
    assert re.search(r"fetchWithState<ServiceDiversity>\(`/api/topology/diversity/", src)
    # P108: the map reads the complete SRLG summary; the panel reads the per-conduit list
    assert re.search(r"fetchWithState<SrlgConduitTypeRow\[\]>\(srlgSummaryUrl\(selectedRegion\)\)", src)
    assert re.search(r"fetchWithState<SrlgMember\[\]>\(conduitSrlgsUrl\(conduit\.conduit_id, region\)\)", src)
    # the old header-blind fetches are gone
    assert "fetch(`/api/topology/path-trace/" not in src
    assert "r.ok ? r.json() : null" not in src


def test_live_render_condition_unchanged_and_outage_always_disclosed():
    src = _read("routes", "topology.tsx")
    # BUG-DW-111 item 3: live with 0 hops renders the neutral 'No traced path' banner.
    # BUG-DW-106: every settled mode (incl. auth_expired) renders it; only pending does not.
    assert 'tracedServiceId && traceMode !== "pending" && (' in src
    assert "traceMode={traceMode}" in src  # mobile tree uses the same states
    assert "srlgUnavailableRegion={" in src


def test_outage_styles_neutral_and_targets():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    start = css.index("/* BUG-DW-098")
    blk = css[start:css.index("/* BUG-DW-062: Error banner retry", start)]
    assert "#F26522" not in blk.upper() and "red" not in blk.lower().replace("no orange or red", "")
    assert "min-height: 44px" in blk and "outline: 2px solid #006272" in blk
    assert "CanvasText" in blk


def test_no_customer_real_name():
    for parts in (("lib", "topology-data-state.ts"), ("routes", "topology.tsx")):
        assert "lumen" not in _read(*parts).lower()


# --- BUG-DW-139: overlay shortcuts D/S/H (WCAG 2.1.4) ------------------------------

@needs_node
@pytest.mark.parametrize("key,expected", [
    ("d", "diversity"), ("D", "diversity"), ("s", "srlg"), ("h", "hazard"), ("H", "hazard"),
    ("f", None), ("x", None), ("Escape", None), ("Tab", None), ("constructor", None), ("", None),
])
def test_dw139_shortcut_key_map_in_scope(key, expected):
    out = _node(f"out = m.overlayShortcutFor({{key: {json.dumps(key)}}}, {{tagName: 'BUTTON'}}, true);")
    assert out == expected


@needs_node
@pytest.mark.parametrize("mods", [
    {"ctrlKey": True}, {"metaKey": True}, {"altKey": True},
    {"ctrlKey": True, "metaKey": True},
])
@pytest.mark.parametrize("key", ["d", "s", "h"])
def test_dw139_modifier_held_is_noop(mods, key):
    ev = dict(mods, key=key)
    assert _node(f"out = m.overlayShortcutFor({json.dumps(ev)}, {{tagName: 'svg'}}, true);") is None


@needs_node
def test_dw139_shift_alone_still_toggles():
    # Shift is not a browser-command modifier; Shift+D yields key 'D'
    assert _node("out = m.overlayShortcutFor({key: 'D', shiftKey: true}, {tagName: 'g'}, true);") == "diversity"


@needs_node
@pytest.mark.parametrize("target", [
    {"tagName": "INPUT"}, {"tagName": "input"}, {"tagName": "SELECT"}, {"tagName": "TEXTAREA"},
    {"tagName": "DIV", "isContentEditable": True},
])
def test_dw139_editable_targets_are_noop(target):
    assert _node(f"out = m.overlayShortcutFor({{key: 'd'}}, {json.dumps(target)}, true);") is None
    assert _node(f"out = m.isEditableTarget({json.dumps(target)});") is True


@needs_node
def test_dw139_focus_outside_graph_is_noop():
    assert _node("out = ['d','s','h'].map(k => m.overlayShortcutFor({key: k}, {tagName: 'BODY'}, false));") == [None, None, None]
    assert _node("out = m.isEditableTarget(null);") is False
    assert _node("out = m.isEditableTarget({tagName: 'BUTTON'});") is False


@needs_node
def test_dw139_scope_selector_matches_rendered_containers():
    sel = _node("out = m.SHORTCUT_SCOPE_SELECTOR;")
    classes = [s.strip().lstrip(".") for s in sel.split(",")]
    assert classes == ["topo-toolbar", "topo-canvas-wrap"]
    src = _read("routes", "topology.tsx")
    assert 'className="topo-toolbar" role="toolbar"' in src
    # desktop graph and mobile tree wrappers both carry topo-canvas-wrap
    assert 'className="topo-canvas-wrap"' in src
    assert 'className="topo-canvas-wrap topo-canvas-wrap--mobile"' in src


def _shortcut_handler():
    src = _read("routes", "topology.tsx")
    start = src.index("// Keyboard shortcuts (")
    return src[start:src.index('document.removeEventListener("keydown", handler)', start)]


def test_dw139_handler_wiring():
    h = _shortcut_handler()
    # all three gates go through the pure helper, scoped by the active element
    assert "overlayShortcutFor(e, target, focusInScope)" in h
    assert "document.activeElement" in h and "closest(SHORTCUT_SCOPE_SELECTOR)" in h
    # no ungated per-key toggles left in the page (old switch on d/s/h, empty 'f' case)
    assert not re.search(r'case "[dshf]"', h)
    assert "diversity: !o.diversity" not in h
    # still a single document listener; Escape kept (clears conduit > site > region)
    assert h.count('addEventListener("keydown"') == 1
    esc = h[h.index('=== "escape"'):h.index("document.activeElement")]
    assert "setSelectedConduit(null)" in esc and "setSelectedSite(null)" in esc
    assert "setSelectedRegion(null)" in esc and "return;" in esc


def test_dw139_toolbar_hints_kept():
    src = _read("routes", "topology.tsx")
    for t in ('title="Toggle diversity overlay (D)"', 'title="Toggle SRLG overlay (S)"',
              'title="Toggle hazard overlay (H)"'):
        assert t in src


# --- BUG-DW-140: dead Fit / Zoom in / Zoom out buttons removed -----------------

def _toolbar_src():
    src = _read("routes", "topology.tsx")
    start = src.index("function Toolbar(")
    return src[start:src.index("\n}\n", start)]


def test_dw140_no_noop_handlers_passed_to_toolbar():
    src = _read("routes", "topology.tsx")
    usage = src[src.index("<Toolbar"):]
    usage = usage[:usage.index("/>")]
    assert "() => {}" not in usage
    for p in ("onFit", "onZoomIn", "onZoomOut"):
        assert p not in src, p


def test_dw140_fit_zoom_titles_and_labels_gone():
    src = _read("routes", "topology.tsx")
    for t in ("Fit (F)", "Zoom in (+)", "Zoom out (\u2212)", "Fit graph to viewport",
              'aria-label="Zoom in"', 'aria-label="Zoom out"', "topo-btn-group"):
        assert t not in src, t
    assert not re.search(r'case ["\']f["\']', src)


def test_dw140_toolbar_has_no_unnamed_symbol_buttons():
    tb = _toolbar_src()
    # every remaining toolbar <button> carries a visible text label or aria-label
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", tb, flags=re.S)
    assert buttons, "toolbar buttons not found"
    for b in buttons:
        assert b.strip() not in ("\u229e", "+", "\u2212")
    # leading divider only when the breadcrumb renders before it
    assert '{selectedRegion && <div className="topo-divider" aria-hidden="true" />}' in tb


def test_dw140_dead_css_removed():
    css = _read("styles", "lakelink-theme.css")
    assert ".topo-btn-group" not in css
    assert ".topo-toolbar .topo-divider" in css


# --- BUG-DW-141: /topology route heading (WCAG 1.3.1 / 2.4.6, G141) ------------

@needs_node
def test_dw141_topology_heading_copy():
    out = _node("out = [m.TOPOLOGY_HEADING, m.topologyHeading(null), m.topologyHeading(undefined),"
                " m.topologyHeading(''), m.topologyHeading('Central'), m.topologyHeading(' West ')];")
    assert out == ["Network Topology", "Network Topology", "Network Topology",
                   "Network Topology", "Central Region Topology", "West Region Topology"]


def test_dw141_heading_matches_document_title():
    root = _read("routes", "__root.tsx")
    lib = _read("lib", "topology-data-state.ts")
    m = re.search(r'"/topology":\s*"([^"|]+?)\s*\|', root)
    assert m, "topology document.title not found"
    assert f'TOPOLOGY_HEADING = "{m.group(1)}"' in lib


def _strip_jsx_comments(src):
    return re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)


def test_dw141_exactly_one_h2_outside_dialog():
    src = _strip_jsx_comments(_read("routes", "topology.tsx"))
    h2s = re.findall(r"<h2\b[^>]*>", src)
    outside = [h for h in h2s if "mobile-detail-title" not in h]
    assert outside == ['<h2 className="topo-page-title">'], h2s
    # the mobile detail h2 is unchanged and lives inside the role=dialog modal
    i = src.index('<h2 className="mobile-detail-title">')
    assert 'role="dialog"' in src[src.rindex('className="mobile-detail-modal"', 0, i):i]


def test_dw141_heading_precedes_toolbar_and_is_region_aware():
    src = _strip_jsx_comments(_read("routes", "topology.tsx"))
    i = src.index('<h2 className="topo-page-title">{topologyHeading(selectedRegion)}</h2>')
    j = src.index("<Toolbar\n", i)
    assert src[i:j].count("<") == 2  # only the h2 open/close tags between them


def test_dw141_legend_is_h3_and_css_follows():
    src = _read("routes", "topology.tsx")
    assert "<h3>Legend</h3>" in src
    assert "<h4>Legend</h4>" not in src
    css = _read("styles", "lakelink-theme.css")
    assert re.search(r"(?m)^\.topo-legend h3 \{", css)
    assert not re.search(r"(?m)^\.topo-legend h4 \{", css)
    rule = re.search(r"(?m)^\.topo-page-title \{([^}]*)\}", css)
    assert rule and "font-size: 22px" in rule.group(1) and "var(--lf-dark-teal)" in rule.group(1)


def test_dw141_panels_stay_h3_sections_h4():
    src = _read("routes", "topology.tsx")
    assert len(re.findall(r'<h4 className="panel-section-title">', src)) >= 3
    assert not re.search(r"<h[56]\b", src)


# --- BUG-DW-142: mobile topology names wrap, never truncate (WCAG 1.4.10) ------

_DW142_SELECTORS = (".mobile-tree-label", ".mobile-detail-title", ".mobile-detail-dl dd")


def _dw142_rules(css, selector):
    """Bodies of every rule (any media block) whose selector list includes `selector` exactly."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sels = [s.strip() for s in m.group(1).split(",")]
        if selector in sels:
            out.append(m.group(2))
    return out


def _dw142_decls(body):
    return {k.strip(): v.strip() for k, v in
            (d.split(":", 1) for d in body.split(";") if ":" in d)}


@pytest.mark.parametrize("selector", _DW142_SELECTORS)
def test_dw142_no_truncation_anywhere(selector):
    rules = _dw142_rules(_read("styles", "lakelink-theme.css"), selector)
    assert rules, selector
    for body in rules:
        d = _dw142_decls(body)
        assert d.get("text-overflow") is None, (selector, body)
        assert d.get("white-space") != "nowrap", (selector, body)
        assert d.get("overflow") != "hidden", (selector, body)


@pytest.mark.parametrize("selector", _DW142_SELECTORS)
def test_dw142_base_rule_wraps(selector):
    css = _read("styles", "lakelink-theme.css")
    m = re.search(r"(?m)^" + re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    d = _dw142_decls(m.group(1))
    assert d.get("overflow-wrap") == "anywhere"
    assert d.get("min-width") == "0"
    if selector != ".mobile-detail-dl dd":
        assert d.get("white-space") == "normal"
        assert d.get("flex") == "1"  # shrinkable beside the meta / 44px close button


def test_dw142_full_brand_name_rendered():
    src = _read("routes", "topology.tsx")
    # Dialog heading renders the full site_name; no brand stripping (CEO branding mandate).
    assert re.search(r'<h2 className="mobile-detail-title">\s*\{detailSite\s*\?\s*detailSite\.site_name', src)
    assert not re.search(r"site_name\s*\.\s*(replace|slice|substring)\(", src)
    assert "lumen" not in src.lower()


# --- BUG-DW-146: WCAG 2.4.7 site-node focus indicator (global ring not suppressed) ---

def test_dw146_site_node_group_outline_not_suppressed():
    css = _read("styles", "lakelink-theme.css")
    rules = _dw142_rules(css, ".topo-site-node:focus-visible")
    for body in rules:
        d = _dw142_decls(body)
        assert d.get("outline") not in ("none", "0"), body
        assert d.get("outline-style") != "none", body


def test_dw146_global_tabindex_ring_applies_to_site_node():
    css = _read("styles", "lakelink-theme.css")
    rules = _dw142_rules(css, "[tabindex]:focus-visible")
    assert rules
    d = _dw142_decls(rules[0])
    assert d.get("outline") == "2px solid var(--lf-dark-teal)"
    assert d.get("outline-offset") == "2px"
    src = _read("routes", "topology.tsx")
    m = re.search(r'className=\{`topo-site-node[^`]*`\}\s*tabIndex=\{0\}', src)
    assert m, "site node group must carry tabIndex so the global ring matches"


def test_dw146_circle_stroke_cue_and_forced_colors_kept():
    css = _read("styles", "lakelink-theme.css")
    rules = [_dw142_decls(b) for b in _dw142_rules(css, ".topo-site-node:focus-visible circle")]
    assert any(r.get("stroke") == "var(--lf-dark-teal)" and r.get("stroke-width") == "3" for r in rules)
    assert any(r.get("stroke") == "Highlight" and r.get("stroke-width") == "4" for r in rules)


# --- BUG-DW-153: WCAG 1.4.3/2.4.7 dimmed off-path site nodes keep full-strength label + ring ---

def _dw153_site_group(src):
    m = re.search(r'className=\{`topo-site-node[^`]*`\}(.*?)\n\s*>\n', src, re.S)
    assert m, "site node group not found"
    return m.group(1)


def _dw153_hex_lum(h):
    h = h.lstrip("#")
    def ch(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _dw153_contrast(a, b):
    la, lb = sorted((_dw153_hex_lum(a), _dw153_hex_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_dw153_site_node_group_has_no_opacity():
    attrs = _dw153_site_group(_read("routes", "topology.tsx"))
    assert "opacity" not in attrs, attrs


def test_dw153_no_group_level_opacity_rule_for_site_nodes():
    css = _read("styles", "lakelink-theme.css")
    for sel in (".topo-dimmed", ".topo-site-node.topo-dimmed", ".topo-site-node"):
        for body in _dw142_rules(css, sel):
            op = _dw142_decls(body).get("opacity")
            assert op is None or float(op) >= 1, (sel, body)


def test_dw153_dimming_moves_to_shape_and_restores_on_focus_hover():
    css = _read("styles", "lakelink-theme.css")
    for shape in ("circle", "polygon"):
        dim = [_dw142_decls(b) for b in _dw142_rules(css, f".topo-site-node.topo-dimmed {shape}")]
        assert any(d.get("opacity") == "0.25" for d in dim), shape
        for st in ("focus-visible", "hover"):
            full = [_dw142_decls(b) for b in _dw142_rules(css, f".topo-site-node.topo-dimmed:{st} {shape}")]
            assert any(d.get("opacity") == "1" for d in full), (shape, st)


def test_dw153_dimmed_label_fill_is_iron():
    src = _read("routes", "topology.tsx")
    assert "fill={dimmed ? BRAND.iron : BRAND.darkTeal}" in src


def test_dw153_iron_on_white_contrast_known_answer():
    assert round(_dw153_contrast("#4D4D4D", "#FFFFFF"), 2) == 8.45
    assert _dw153_contrast("#4D4D4D", "#E8E8E8") >= 4.5


def test_dw153_off_path_srlg_badges_not_rendered_during_trace():
    src = _read("routes", "topology.tsx")
    layer = src[src.index('className="srlg-badge-layer"'):]
    layer = layer[:layer.index("</g>\n      )}")]
    assert "if (hasPathTrace && !pathConduitIds.has(c.conduit_id)) return null;" in layer
    assert "opacity={dimmed" not in layer
    badge = re.search(r'<g key=\{`srlg-badge-[^>]*>', layer).group(0)
    assert "opacity" not in badge


def test_dw153_on_path_aria_suffix_kept_and_brand_clean():
    src = _read("routes", "topology.tsx")
    assert '". On traced service path"' in src
    assert "lumen" not in src.lower()
    assert "lumen" not in _read("styles", "lakelink-theme.css").lower()


# --- BUG-DW-152: .mobile-tree-loading must not use opacity (WCAG 1.4.3) -------------

_DW152_CHAIN = (".mobile-tree-loading", ".mobile-tree-group", ".mobile-tree-list",
                ".mobile-tree-container")


def _dw152_blend(fg, bg, alpha):
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(alpha * x + (1 - alpha) * y):02X}" for x, y in zip(f, b))


def test_dw152_contrast_known_answers():
    # Designer's measured failing value: iron at 0.6 on white = #949494 = 3.03:1.
    assert _dw152_blend("#4D4D4D", "#FFFFFF", 0.6) == "#949494"
    assert round(_dw153_contrast("#949494", "#FFFFFF"), 2) == 3.03


@pytest.mark.parametrize("selector", _DW152_CHAIN)
def test_dw152_no_opacity_on_loading_or_ancestors(selector):
    css = _read("styles", "lakelink-theme.css")
    for body in _dw142_rules(css, selector):
        assert "opacity" not in _dw142_decls(body), (selector, body)


def test_dw152_loading_is_iron_italic_and_passes_on_real_surfaces():
    rules = _dw142_rules(_read("styles", "lakelink-theme.css"), ".mobile-tree-loading")
    assert len(rules) == 1
    d = _dw142_decls(rules[0])
    assert d.get("color") == "var(--lf-iron)"
    assert d.get("font-style") == "italic"
    # No container background: text sits on white or the platinum body.
    for surface in ("#FFFFFF", "#E8E8E8"):
        assert _dw153_contrast("#4D4D4D", surface) >= 4.5, surface


def test_dw152_markup_unchanged():
    src = _read("routes", "topology.tsx")
    assert '<li className="mobile-tree-loading" aria-live="polite">' in src


# --- BUG-DW-151: .topo-page-title font-size matches .section-header h2 at all widths ---

def _dw151_blocks(css):
    """Yield (media_prelude_or_None, selector_list, body) for every rule, one media level deep."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        prelude = css[i:j].strip()
        depth, k = 1, j + 1
        while depth and k < n:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        inner = css[j + 1:k - 1]
        if prelude.startswith("@media"):
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", inner):
                yield prelude, [s.strip() for s in m.group(1).split(",")], m.group(2)
        elif not prelude.startswith("@"):
            yield None, [s.strip() for s in prelude.split(",")], inner
        i = k


def _dw151_font_size(css, selector, width):
    """Last-wins font-size for `selector` at viewport `width` (base + max-width media only)."""
    val = None
    for media, sels, body in _dw151_blocks(css):
        if selector not in sels:
            continue
        if media is not None:
            m = re.fullmatch(r"@media\s*\(max-width:\s*(\d+)px\)", media)
            if not m or width > int(m.group(1)):
                continue
        fs = _dw142_decls(body).get("font-size")
        if fs:
            val = fs
    return val


def test_dw151_resolver_known_answer():
    css = ".a{font-size:10px}@media (max-width: 767px){.a,.b{font-size:5px}}.b{font-size:7px}"
    assert _dw151_font_size(css, ".a", 1200) == "10px"
    assert _dw151_font_size(css, ".a", 400) == "5px"
    assert _dw151_font_size(css, ".b", 400) == "7px"  # later base rule wins


@pytest.mark.parametrize("width,expected", [(1280, "22px"), (1023, "22px"), (767, "18px"), (375, "18px")])
def test_dw151_topology_heading_matches_section_header(width, expected):
    css = _read("styles", "lakelink-theme.css")
    assert _dw151_font_size(css, ".section-header h2", width) == expected
    assert _dw151_font_size(css, ".topo-page-title", width) == expected


def test_dw151_heading_colour_and_markup_unchanged():
    css = _read("styles", "lakelink-theme.css")
    base = [b for m, s, b in _dw151_blocks(css) if m is None and ".topo-page-title" in s]
    assert any(_dw142_decls(b).get("color") == "var(--lf-dark-teal)" for b in base)
    assert 'className="topo-page-title"' in _read("routes", "topology.tsx")


# --- BUG-DW-148: legend svg aria-hidden + dead hazard-pulse prop ---------------

_DW148_SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.S)


def _dw148_legend_blocks(src):
    """Every `.topo-legend` JSX block from its opening div to the end of that return."""
    out = []
    for m in re.finditer(r'<div className="topo-legend"', src):
        end = src.find("\n  );\n", m.start())
        assert end > m.start()
        out.append(src[m.start():end])
    return out


def test_dw148_svg_scanner_known_answer():
    sample = '<svg width="14" height="14">x</svg><svg\n  width="2" aria-hidden="true">y</svg>'
    tags = _DW148_SVG_OPEN.findall(sample)
    assert len(tags) == 2
    assert [('aria-hidden="true"' in t) for t in tags] == [False, True]


def test_dw148_every_legend_svg_is_decorative():
    blocks = _dw148_legend_blocks(_read("routes", "topology.tsx"))
    assert blocks, "legend block not found"
    tags = [t for b in blocks for t in _DW148_SVG_OPEN.findall(b)]
    assert len(tags) >= 9
    missing = [t for t in tags if 'aria-hidden="true"' not in t]
    assert missing == [], missing


def test_dw148_node_swatches_not_focusable():
    blocks = "".join(_dw148_legend_blocks(_read("routes", "topology.tsx")))
    for label in ("Backbone Site (tier_1)", "Regional Site (tier_2)"):
        i = blocks.index(label)
        tag = _DW148_SVG_OPEN.findall(blocks[:i])[-1]
        assert 'aria-hidden="true"' in tag and 'focusable="false"' in tag, tag


def test_dw148_no_animated_hazard_cell_in_action_queue():
    src = _read("components", "actions", "action-queue-table.tsx")
    assert re.search(r"\banimated\b", src) is None
    assert "<HazardTypeCell type={a.hazard_type!} />" in src
    # no .severity-critical wrapper added just to turn the pulse on
    assert "severity-critical" not in src


def test_dw148_no_animated_hazard_cell_anywhere_in_ui():
    for root, _dirs, files in os.walk(UI):
        for fn in files:
            if fn.endswith(".tsx") and fn != "hazard-type-cell.tsx":
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    assert re.search(r"<HazardTypeCell[^>]*\banimated\b", f.read()) is None, fn


# --- BUG-DW-155: mobile tree search placeholder must not use opacity (WCAG 1.4.3) ---

def _dw155_placeholder_rules(css):
    """(selector_list, body) for every rule in any media block that targets ::placeholder."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
            if "placeholder" in m.group(1)]


def test_dw155_contrast_known_answers():
    # Designer's failing value: iron @ 0.6 on white = #949494 = 3.03:1; solid iron = 8.45:1.
    assert _dw152_blend("#4D4D4D", "#FFFFFF", 0.6) == "#949494"
    assert round(_dw153_contrast("#949494", "#FFFFFF"), 2) == 3.03
    assert round(_dw153_contrast("#4D4D4D", "#FFFFFF"), 2) == 8.45


def test_dw155_no_opacity_on_any_placeholder_rule():
    rules = _dw155_placeholder_rules(_read("styles", "lakelink-theme.css"))
    assert rules, "expected at least the mobile tree search placeholder rule"
    for sel, body in rules:
        assert "opacity" not in _dw142_decls(body), (sel, body)


def test_dw155_placeholder_is_solid_iron_italic():
    rules = _dw142_rules(_read("styles", "lakelink-theme.css"),
                         ".mobile-tree-search-input::placeholder")
    assert len(rules) == 1
    d = _dw142_decls(rules[0])
    assert d.get("color") == "var(--lf-iron)"
    assert d.get("font-style") == "italic"
    assert "platinum-shade" not in rules[0]


def test_dw155_input_surface_and_ios_zoom_guard_unchanged():
    # Base rule only; a reduced-motion block also targets the selector (transition: none).
    rules = [r for r in _dw142_rules(_read("styles", "lakelink-theme.css"),
                                     ".mobile-tree-search-input")
             if "font-size" in _dw142_decls(r)]
    assert len(rules) == 1
    d = _dw142_decls(rules[0])
    assert d.get("font-size") == "16px"
    assert d.get("background") == "var(--lf-white)"


def test_dw155_brand_clean():
    assert "lumen" not in _read("styles", "lakelink-theme.css").lower()


# --- BUG-DW-156: orphaned .hazard-icon / hazard-pulse motion path removed (WCAG 2.2.2) ---

def _dw156_ui_files(exts):
    for root, _dirs, files in os.walk(UI):
        for fn in files:
            if fn.endswith(exts):
                p = os.path.join(root, fn)
                with open(p, encoding="utf-8") as f:
                    yield os.path.relpath(p, UI), f.read()


def _dw156_css_nocomments():
    return re.sub(r"/\*.*?\*/", "", _read("styles", "lakelink-theme.css"), flags=re.S)


def test_dw156_no_hazard_pulse_anywhere_in_ui():
    hits = [p for p, s in _dw156_ui_files((".css", ".ts", ".tsx")) if "hazard-pulse" in s]
    assert hits == [], hits


def test_dw156_no_hazard_icon_selector_in_css():
    assert re.search(r"\.hazard-icon\b", _dw156_css_nocomments()) is None


def test_dw156_no_tsx_emits_hazard_icon_class():
    hits = [p for p, s in _dw156_ui_files((".tsx",)) if "hazard-icon" in s]
    assert hits == [], hits


def test_dw156_hazard_type_cell_has_no_animated_prop():
    src = _read("components", "hazards", "hazard-type-cell.tsx")
    assert re.search(r"\banimated\b", src) is None
    # BUG-DW-162 added an optional fallbackIcon prop; the DW-156 guard is only that `animated` is gone.
    sig = re.search(r"export function HazardTypeCell\(\{([^}]*)\}: HazardTypeCellProps\)", src)
    assert sig, "HazardTypeCell signature not found"
    params = {p.strip() for p in sig.group(1).split(",")}
    assert {"type", "iconSize"} <= params and "animated" not in params
    assert "iconSize?: number;" in src


def test_dw156_other_reduced_motion_overrides_unchanged():
    css = _dw156_css_nocomments()
    assert ".skeleton-loading { animation: none; background-color: var(--lf-white); }" in css
    assert re.search(r"\.srlg-highlight,\s*\.srlg-critical \{ animation: none; \}", css)
    assert "@keyframes skeleton-pulse" in css and "@keyframes srlg-pulse" in css
    # global reduced-motion catch-all survives the hazard-icon override removal
    assert "animation-iteration-count: 1 !important;" in css


def test_dw156_css_braces_balanced():
    css = _dw156_css_nocomments()
    assert css.count("{") == css.count("}")
