"""BUG-DW-117: hazard marker keyboard-focus callout (parity with the hover <title> tooltip).

Pure helpers in ui/lib/hazard-callout.ts are evaluated with Node (>= 22.18 strips TS types).
JSX wiring and CSS are checked statically (no npm on serverless). The DW-115 scanner and the
byte-identical aria-label are re-asserted here.
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
CANVAS_W, CANVAS_H = 1200, 600


def _load_dw115():
    spec = importlib.util.spec_from_file_location(
        "_dw115_for_dw117", os.path.join(HERE, "test_topology_dw115.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DW115 = _load_dw115()


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


# --- copy -----------------------------------------------------------------------------------

@needs_node
def test_callout_text_known_answer():
    out = _node(f"out = m.hazardCalloutText({json.dumps(_hazard())});")
    assert out == "severe weather hazard: Derecho Line \u00b7 high \u00b7 3 direct / 12 near spans"


@needs_node
def test_callout_text_carries_every_fact_in_aria_label():
    h = _hazard(hazard_type="dig_ticket", name="811 Ticket 42", severity="critical",
                direct_impact_spans=0, near_impact_spans=1)
    text = _node(f"out = m.hazardCalloutText({json.dumps(h)});")
    for fact in ("dig ticket", "811 Ticket 42", "critical", "0 direct", "1 near"):
        assert fact in text


# --- marker position unchanged (refactor regression) ----------------------------------------

def _old_inline_pos(hid):
    """Character-for-character port of the pre-DW-117 inline placement in topology.tsx."""
    h = sum(ord(c) for c in hid)
    return {"x": 80 + (h % (CANVAS_W - 160)), "y": 60 + ((h * 7) % (CANVAS_H - 120))}


@needs_node
def test_marker_position_matches_previous_inline_formula():
    ids = ["HZ-0001", "WF-2026-CA-117", "FL-9", "", "DIG-811-000042", "x" * 300]
    out = _node(f"out = {json.dumps(ids)}.map((i) => m.hazardMarkerPos(i, {CANVAS_W}, {CANVAS_H}));")
    assert out == [_old_inline_pos(i) for i in ids]


@needs_node
def test_ring_radius():
    out = _node("out = [m.hazardRingRadius({direct_impact_spans: 0}), m.hazardRingRadius({direct_impact_spans: 2})];")
    assert out == [20, 30]


# --- geometry: never covers marker or ring, always on canvas -------------------------------

RING_EXTENT = 4      # focus outline 2px + offset 2px
STROKE_HALF = 1.5    # max severity stroke 2.5 / 2, rounded up
LABEL_BOTTOM = 33    # 9px name label baseline at +30, plus descender


def _marker_band(cy, r):
    return (cy - r - STROKE_HALF - RING_EXTENT, cy + max(r + STROKE_HALF, LABEL_BOTTOM) + RING_EXTENT)


@needs_node
def test_box_clear_of_marker_and_inside_canvas_full_sweep():
    text = "severe weather hazard: Derecho Line \u00b7 high \u00b7 3 direct / 12 near spans"
    cases = [(cx, cy, r) for cx in (80, 300, 600, 1119) for cy in range(60, 541, 4) for r in (20, 30)]
    out = _node(f"const t = {json.dumps(text)};\nout = {json.dumps(cases)}.map(([x, y, r]) => "
                f"m.hazardCalloutBox(x, y, r, t, {CANVAS_W}, {CANVAS_H}));")
    placements = set()
    for (cx, cy, r), b in zip(cases, out):
        placements.add(b["placement"])
        assert b["x"] >= 4 and b["y"] >= 4
        assert b["x"] + b["width"] <= CANVAS_W - 4 and b["y"] + b["height"] <= CANVAS_H - 4
        top, bottom = _marker_band(cy, r)
        assert b["y"] + b["height"] <= top or b["y"] >= bottom, (cx, cy, r, b)
        assert b["height"] == 12 + 2 * 8
        assert b["textX"] == b["x"] + 8 and b["textY"] == b["y"] + b["height"] / 2
        assert b["text"] == text
    assert placements == {"above", "below"}


@needs_node
def test_box_flips_below_near_top_known_answer():
    # cy=60, r=30: above would need y = 60-31.5-8-28 = -7.5 < 4, so flip below the name label.
    b = _node(f"out = m.hazardCalloutBox(600, 60, 30, 'abc', {CANVAS_W}, {CANVAS_H});")
    assert b["placement"] == "below"
    assert b["y"] == 60 + 33 + 8
    b = _node(f"out = m.hazardCalloutBox(600, 300, 30, 'abc', {CANVAS_W}, {CANVAS_H});")
    assert b["placement"] == "above" and b["y"] == 300 - 31.5 - 8 - 28


@needs_node
def test_box_width_fits_text_estimate():
    b = _node(f"out = m.hazardCalloutBox(600, 300, 20, 'x'.repeat(40), {CANVAS_W}, {CANVAS_H});")
    assert b["width"] == 40 * 0.6 * 12 + 16


@needs_node
def test_long_name_truncated_to_canvas():
    b = _node(f"out = m.hazardCalloutBox(600, 300, 20, 'N'.repeat(500), {CANVAS_W}, {CANVAS_H});")
    assert b["text"].endswith("\u2026") and len(b["text"]) < 500
    assert 4 <= b["x"] and b["x"] + b["width"] <= CANVAS_W - 4


# --- focus state helpers --------------------------------------------------------------------

@needs_node
def test_focused_hazard_for_only_the_focused_id():
    hz = [_hazard(hazard_id="A"), _hazard(hazard_id="B"), _hazard(hazard_id="C")]
    out = _node(f"const hz = {json.dumps(hz)};\nout = ["
                "m.focusedHazardFor(hz, 'B', true)?.hazard_id ?? null,"
                "m.focusedHazardFor(hz, 'B', false),"
                "m.focusedHazardFor(hz, null, true),"
                "m.focusedHazardFor(hz, 'GONE', true),"
                "m.focusedHazardFor([], 'B', true)];")
    assert out == ["B", None, None, None, None]


@needs_node
def test_next_focused_hazard_ignores_stale_blur():
    out = _node("out = [m.nextFocusedHazard('A','A'), m.nextFocusedHazard('B','A'), m.nextFocusedHazard(null,'A')];")
    assert out == [None, "B", None]


@needs_node
def test_is_keyboard_focus():
    out = _node("out = ["
                "m.isKeyboardFocus({matches: (s) => s === ':focus-visible'}),"
                "m.isKeyboardFocus({matches: () => false}),"
                "m.isKeyboardFocus({matches: () => { throw new Error('unsupported'); }}),"
                "m.isKeyboardFocus({}), m.isKeyboardFocus(null)];")
    assert out == [True, False, True, True, True]


# --- JSX wiring (static) --------------------------------------------------------------------

def _src():
    return _read(TOPOLOGY)


def _callout_block():
    t = _src()
    start = t.index('className="hazard-focus-callout"')
    start = t.rindex("{focusedHazard && (", 0, start)
    end = t.index("BUG-DW-056: sr-only hazard summary", start)
    return t[start:end]


def _marker_open_tag():
    t = _src()
    i = t.index('className="hazard-overlay-marker"')
    j = t.index("{/* Proximity ring */}", i)
    return t[i:j]


def test_callout_rendered_once_outside_marker_map():
    t = _src()
    assert t.count('className="hazard-focus-callout"') == 1
    map_start = t.index("overlays.hazard && hazards.map(")
    callout = t.index('className="hazard-focus-callout"')
    sr_only = t.index("BUG-DW-056: sr-only hazard summary")
    assert map_start < callout < sr_only
    # rendered after the map closes, i.e. once and on top of every marker
    assert t.rindex("})}", map_start, callout) > map_start
    assert "const focusedHazard = focusedHazardFor(hazards, focusedHazardId, overlays.hazard);" in t


def test_callout_is_aria_hidden_and_inert():
    block = _callout_block()
    assert 'aria-hidden="true"' in block
    assert 'pointerEvents="none"' in block
    for banned in ("tabIndex", "<title", "aria-describedby", "role=", "aria-label", "aria-live"):
        assert banned not in block, banned
    assert "data-hazard-id={focusedHazard.hazard_id}" in block
    assert "hazardCalloutText(focusedHazard)" in block and "{box.text}" in block


def test_marker_handlers_wired():
    tag = _marker_open_tag()
    assert "isKeyboardFocus(e.currentTarget)" in tag and "setFocusedHazardId(h.hazard_id)" in tag
    assert "onBlur={() => setFocusedHazardId((cur) => nextFocusedHazard(cur, h.hazard_id))}" in tag
    esc = tag[tag.index("onKeyDown"):]
    assert 'e.key === "Escape" && focusedHazardId === h.hazard_id' in esc
    # 1.4.13: dismissing the callout must not also fire the document Escape (drill-out)
    assert esc.index("e.stopPropagation()") < esc.index("setFocusedHazardId(null)")
    assert "aria-describedby" not in tag


def test_marker_uses_shared_position_and_radius():
    t = _src()
    assert "const { x: hx, y: hy } = hazardMarkerPos(h.hazard_id, CANVAS_W, CANVAS_H);" in t
    assert "r={hazardRingRadius(h)}" in t
    assert "(hash * 7) % (CANVAS_H - 120)" not in t  # single source now in the lib


def test_dw115_invariants_still_hold():
    t = _src()
    assert DW115.focusable_with_child_title(t) == []
    block = t[t.index("overlays.hazard && hazards.map("):t.index("BUG-DW-056: sr-only hazard summary")]
    assert block.count(DW115.HAZARD_ARIA_LABEL) == 1
    assert DW115.HAZARD_TITLE_TEXT in block


def test_all_ui_tsx_scanner_clean():
    for p in glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True):
        assert DW115.focusable_with_child_title(_read(p)) == [], p


# --- CSS ------------------------------------------------------------------------------------

def _rule(css, selector, forced=False):
    """Body of the first rule for selector, inside or outside @media (forced-colors: active)."""
    blocks, out = [], []
    for m in re.finditer(r"@media \(forced-colors: active\) \{", css):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        blocks.append((m.start(), i))
    for m in re.finditer(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css):
        inside = any(a < m.start() < b for a, b in blocks)
        if inside == forced:
            out.append(m.group(1))
    assert out, (selector, forced)
    return out[0]


def _rel_lum(hexcol):
    c = [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_css_base_style_matches_spec():
    css = _read(CSS)
    box = _rule(css, ".hazard-focus-callout-box")
    assert "fill: #FFFFFF" in box and "#4D4D4D" in box and "stroke-width: 1" in box
    txt = _rule(css, ".hazard-focus-callout-text")
    assert "12px" in txt and "Inter" in txt and "#4D4D4D" in txt
    ratio = (1.05) / (_rel_lum("#4D4D4D") + 0.05)
    assert round(ratio, 2) == 8.45


def test_css_forced_colors():
    css = _read(CSS)
    box = _rule(css, ".hazard-focus-callout-box", forced=True)
    assert "fill: Canvas" in box and "stroke: CanvasText" in box
    assert "fill: CanvasText" in _rule(css, ".hazard-focus-callout-text", forced=True)


# --- branding -------------------------------------------------------------------------------

def test_no_legacy_brand_name_in_ui():
    hits = []
    for p in glob.glob(os.path.join(UI, "**", "*.*"), recursive=True):
        if os.path.isfile(p) and "lumen" in _read(p).lower():
            hits.append(p)
    assert hits == []
