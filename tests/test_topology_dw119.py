"""BUG-DW-119: hazard focus callout holds the 12px floor + no stale callout after overlay toggle.

(1) The callout is an HTML overlay in .topo-canvas-wrap (wrap CSS px), not SVG text in the
    1200x600 viewBox, so its font never scales with the canvas width.
(2) Overlay off -> on without refocus renders no callout (effect clears the id, and the
    render-time guard ignores an id that is not document.activeElement).
(3) No literal 'Inter' in the callout CSS: var(--font-primary).
Pure helpers run with Node (>= 22 strips TS types); JSX/CSS are checked statically.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(__file__)
UI = os.path.abspath(os.path.join(
    HERE, os.pardir, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui"))
TOPOLOGY = os.path.join(UI, "routes", "topology.tsx")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")
_LIB = os.path.join(UI, "lib", "hazard-callout.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")
VB_W, VB_H = 1200, 600
WRAP_MIN_H = 500  # .topo-canvas-wrap min-height and the SVG minHeight


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_{name}_for_dw119", os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DW115 = _load("test_topology_dw115")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _hazard(**kw):
    h = dict(hazard_id="HZ-0001", hazard_type="severe_weather", name="Derecho Line",
             severity="high", direct_impact_spans=3, near_impact_spans=12)
    h.update(kw)
    return h


def _meet(w, h):
    """Independent xMidYMid-meet model (python) for the svg box w x h."""
    s = min(w / VB_W, h / VB_H)
    return {"scale": s, "ox": (w - VB_W * s) / 2, "oy": (h - VB_H * s) / 2}


# --- (1) 12px floor -------------------------------------------------------------------------

@needs_node
@pytest.mark.parametrize("wrap_w", [736, 960, 1200, 1600])
def test_overlay_font_is_12px_at_any_canvas_width(wrap_w):
    wrap_h = max(WRAP_MIN_H, wrap_w / 2)
    out = _node(f"const map = m.meetViewBoxMap({wrap_w}, {wrap_h}, {VB_W}, {VB_H});\n"
                f"out = m.hazardCalloutOverlay({json.dumps(_hazard())}, map, {wrap_w}, {wrap_h}, {VB_W}, {VB_H});")
    assert out["fontPx"] == 12
    assert out["height"] == 12 + 2 * 8  # box metrics are CSS px too, never scaled


def test_old_svg_scaled_text_was_below_floor_known_answer():
    # Documents the defect: 12 viewBox units on a 736px-wide canvas.
    assert round(12 * _meet(736, WRAP_MIN_H)["scale"], 1) == 7.4


def test_callout_is_html_after_svg_not_svg_text():
    t = _read(TOPOLOGY)
    assert t.count('className="hazard-focus-callout"') == 1
    i = t.index('className="hazard-focus-callout"')
    assert t.rindex("<div", 0, i) > t.rindex("</svg>", 0, i)  # a div, after the svg closes
    for gone in ("hazard-focus-callout-box", "hazard-focus-callout-text", "hazardCalloutBox("):
        assert gone not in t, gone
    block = t[t.rindex("{focusedHazard && calloutFrame && (", 0, i):t.index("</>", i)]
    assert "style={{ left: box.x, top: box.y, width: box.width, height: box.height, fontSize: box.fontPx }}" in block


def test_css_font_is_absolute_12px_and_overlay_positioned():
    css = _read(CSS)
    m = re.search(r"(?m)^\.hazard-focus-callout\s*\{([^}]*)\}", css)
    body = m.group(1)
    assert "position: absolute" in body and "font-size: 12px" in body
    assert "font-family: var(--font-primary)" in body
    assert "'Inter'" not in body  # (3) no literal font
    wrap = re.search(r"(?m)^\.topo-canvas-wrap\s*\{([^}]*)\}", css).group(1)
    assert "position: relative" in wrap  # containing block of the overlay


@needs_node
def test_meet_map_matches_independent_model():
    sizes = [(736, 500), (960, 500), (1200, 600), (1600, 800), (1000, 900)]
    out = _node(f"out = {json.dumps(sizes)}.map(([w, h]) => m.meetViewBoxMap(w, h, {VB_W}, {VB_H}));")
    for (w, h), got in zip(sizes, out):
        exp = _meet(w, h)
        for k in exp:
            assert got[k] == pytest.approx(exp[k]), (w, h, k)
    # 736x500 letterboxes vertically: percentage-of-wrap placement would be 66px off.
    assert out[0]["oy"] == pytest.approx(66.0)


@needs_node
def test_view_box_to_wrap_known_answer():
    out = _node("out = m.viewBoxToWrap({a: 0.5, e: 340, f: 216}, {left: 240, top: 150}, 1, 1);")
    assert out == {"scale": 0.5, "ox": 99, "oy": 65}


@needs_node
def test_identity_map_reproduces_dw117_geometry():
    hz = [_hazard(hazard_id=i) for i in ("HZ-0001", "WF-2026-CA-117", "FL-9", "DIG-811-000042")]
    out = _node(
        f"const hz = {json.dumps(hz)};\nconst id = {{scale: 1, ox: 0, oy: 0}};\n"
        f"out = hz.map((h) => {{ const p = m.hazardMarkerPos(h.hazard_id, {VB_W}, {VB_H});"
        f" const a = m.hazardCalloutBox(p.x, p.y, m.hazardRingRadius(h), m.hazardCalloutText(h), {VB_W}, {VB_H});"
        f" const b = m.hazardCalloutOverlay(h, id, {VB_W}, {VB_H}, {VB_W}, {VB_H});"
        " delete b.fontPx; return [a, b]; });")
    for a, b in out:
        assert a == b


RING_EXTENT, GAP, STROKE_HALF, LABEL_BOTTOM, MARGIN = 4, 4, 1.5, 33, 4


@needs_node
@pytest.mark.parametrize("wrap_w,wrap_h", [(736, 500), (960, 500), (1200, 600), (1600, 800)])
def test_overlay_clear_of_scaled_marker_and_inside_wrap(wrap_w, wrap_h):
    ids = [f"HZ-{i:04d}" for i in range(0, 400, 7)] + ["WF-2026-CA-117", "x" * 120]
    hz = [_hazard(hazard_id=i, direct_impact_spans=(n % 2) * 3) for n, i in enumerate(ids)]
    out = _node(
        f"const map = m.meetViewBoxMap({wrap_w}, {wrap_h}, {VB_W}, {VB_H});\n"
        f"out = {json.dumps(hz)}.map((h) => [m.hazardMarkerPos(h.hazard_id, {VB_W}, {VB_H}),"
        f" m.hazardRingRadius(h), m.hazardCalloutOverlay(h, map, {wrap_w}, {wrap_h}, {VB_W}, {VB_H})]);")
    mp = _meet(wrap_w, wrap_h)
    s = mp["scale"]
    for pos, r, b in out:
        cy = mp["oy"] + pos["y"] * s
        top = cy - (r + STROKE_HALF) * s - RING_EXTENT
        bottom = cy + max(r + STROKE_HALF, LABEL_BOTTOM) * s + RING_EXTENT
        assert b["x"] >= MARGIN and b["y"] >= MARGIN
        assert b["x"] + b["width"] <= wrap_w - MARGIN and b["y"] + b["height"] <= wrap_h - MARGIN
        assert b["y"] + b["height"] <= top or b["y"] >= bottom, (pos, r, b)


@needs_node
def test_overlay_box_clamped_to_narrow_wrap():
    b = _node(f"const map = m.meetViewBoxMap(736, 500, {VB_W}, {VB_H});\n"
              f"out = m.hazardCalloutOverlay({json.dumps(_hazard(name='N' * 300))}, map, 736, 500, {VB_W}, {VB_H});")
    assert b["text"].endswith("\u2026")
    assert 4 <= b["x"] and b["x"] + b["width"] <= 736 - 4


# --- (2) stale focus ------------------------------------------------------------------------

@needs_node
def test_focused_hazard_ignores_id_that_is_not_active_element():
    hz = [_hazard(hazard_id="A"), _hazard(hazard_id="B")]
    out = _node(f"const hz = {json.dumps(hz)};\nout = ["
                "m.focusedHazardFor(hz, 'A', true, 'A')?.hazard_id ?? null,"
                "m.focusedHazardFor(hz, 'A', true, null),"   # focus on <body> after toggle
                "m.focusedHazardFor(hz, 'A', true, 'B'),"
                "m.focusedHazardFor(hz, 'A', true)?.hazard_id ?? null,"  # guard omitted: DW-117 behaviour
                "m.focusedHazardFor(hz, 'A', false, 'A')];")
    assert out == ["A", None, None, "A", None]


@needs_node
def test_active_hazard_id_of():
    out = _node("const el = (v) => ({activeElement: {getAttribute: (n) => n === 'data-hazard-id' ? v : 'x'}});\n"
                "out = [m.activeHazardIdOf(el('A')), m.activeHazardIdOf(el(null)),"
                " m.activeHazardIdOf({activeElement: null}), m.activeHazardIdOf({activeElement: {}}),"
                " m.activeHazardIdOf(null)];")
    assert out == ["A", None, None, None, None]


@needs_node
def test_overlay_off_then_on_without_refocus_renders_no_callout():
    """Simulate: focus A, press 'h' (markers unmount, no blur), press 'h' again (hazards refetched)."""
    hz = [_hazard(hazard_id="A")]
    out = _node(
        f"const hz = {json.dumps(hz)};\n"
        "let focusedId = 'A'; let active = 'A'; const r = [];\n"
        "r.push(m.focusedHazardFor(hz, focusedId, true, active)?.hazard_id ?? null);\n"
        "active = null;  /* marker removed, focus falls to <body>, no onBlur */\n"
        "r.push(m.focusedHazardFor([], focusedId, false, active));\n"
        "/* re-enable without the effect clearing the id: the render guard alone suppresses it */\n"
        "r.push(m.focusedHazardFor(hz, focusedId, true, active));\n"
        "/* with the effect (overlay off -> setFocusedHazardId(null)) */\n"
        "focusedId = null; r.push(m.focusedHazardFor(hz, focusedId, true, active));\n"
        "out = r;")
    assert out == ["A", None, None, None]


def test_jsx_wires_guard_and_clear_effect():
    t = _read(TOPOLOGY)
    assert re.search(r"focusedHazardFor\(\s*hazards,\s*focusedHazardId,\s*overlays\.hazard,\s*"
                     r"activeHazardIdOf\(typeof document !== \"undefined\" \? document : null\),\s*\)", t)
    assert re.search(r"useEffect\(\(\) => \{\s*if \(!overlays\.hazard\) setFocusedHazardId\(null\);\s*\}, "
                     r"\[overlays\.hazard\]\);", t)
    tag = t[t.index('className="hazard-overlay-marker"'):t.index("{/* Proximity ring */}")]
    assert "data-hazard-id={h.hazard_id}" in tag  # what activeHazardIdOf reads


def test_jsx_measures_with_ctm_and_resize():
    t = _read(TOPOLOGY)
    assert "ref={svgRef}" in t and "svg.getScreenCTM()" in t
    assert "viewBoxToWrap(ctm, wr, wrap.clientLeft, wrap.clientTop)" in t
    assert "new ResizeObserver(measure)" in t and "ro?.disconnect()" in t
    assert 'window.removeEventListener("resize", measure)' in t


# --- (c) DW-115 invariants, aria-label byte-identical; (d) branding -------------------------

def test_dw115_scanner_clean_and_aria_label_identical():
    t = _read(TOPOLOGY)
    block = t[t.index("overlays.hazard && hazards.map("):t.index("BUG-DW-056: sr-only hazard summary")]
    assert block.count(DW115.HAZARD_ARIA_LABEL) == 1
    for p in glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True):
        assert DW115.focusable_with_child_title(_read(p)) == [], p


def test_no_legacy_brand_name_in_ui():
    hits = [p for p in glob.glob(os.path.join(UI, "**", "*.*"), recursive=True)
            if os.path.isfile(p) and "lumen" in _read(p).lower()]
    assert hits == []
