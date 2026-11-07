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
