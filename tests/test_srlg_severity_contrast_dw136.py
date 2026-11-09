"""BUG-DW-136: SRLG severity badge text meets WCAG 2.1 1.4.3 (>=4.5:1, 12px/700 is not large text).

Ruling: low badge colour #6B7280 -> #4B5563 on #F3F4F6. Critical/high/medium rules unchanged.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1]
       / "apps/resilience-scorecard/src/resilience_scorecard/ui/styles/lakelink-theme.css")

EXPECTED = {
    "critical": ("#FEE2E2", "#991B1B"),
    "high": ("#FEF3C7", "#92400E"),
    "medium": ("#E8E8E8", "#4D4D4D"),
    "low": ("#F3F4F6", "#4B5563"),
}


def _strip_comments(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def _rules(severity):
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    sel = re.escape(f'.srlg-severity-badge[data-severity="{severity}"]')
    return re.findall(r"(?m)^" + sel + r"\s*\{([^}]*)\}", css)


def _decl(body, prop):
    m = re.findall(r"(?:^|;|\s)" + prop + r"\s*:\s*([^;]+);", body)
    assert len(m) == 1, (prop, body)
    return m[0].strip().upper()


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_helper_known_answers():
    assert round(_contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(_contrast("#6B7280", "#F3F4F6"), 2) == 4.39  # designer's measured failing value


def test_low_badge_colour_is_4b5563():
    rules = _rules("low")
    assert len(rules) == 1
    assert _decl(rules[0], "color") == "#4B5563"
    assert _decl(rules[0], "background") == "#F3F4F6"


@pytest.mark.parametrize("severity", sorted(EXPECTED))
def test_every_severity_badge_meets_aa_normal_text(severity):
    (body,) = _rules(severity)
    bg, fg = _decl(body, "background"), _decl(body, "color")
    assert (bg, fg) == EXPECTED[severity]
    assert _contrast(fg, bg) >= 4.5, (severity, fg, bg, _contrast(fg, bg))


def test_base_badge_typography_unchanged():
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    (body,) = re.findall(r"(?m)^\.srlg-severity-badge\s*\{([^}]*)\}", css)
    assert _decl(body, "font-size") == "12PX"
    assert _decl(body, "font-weight") == "700"
    assert _decl(body, "letter-spacing") == "0.5PX"


# ---------------------------------------------------------------------------
# BUG-DW-138: .mobile-tree-meta (12px, not large text) must reach >=4.5:1 after
# compounding every opacity in its ancestor chain (row modifier x meta).
# ---------------------------------------------------------------------------

def _all_bodies(selector):
    """Every rule body whose selector list contains `selector` (base and @media)."""
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    out = []
    for sels, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        names = [s.strip() for s in sels.split(",")]
        if selector in names:
            out.append(body)
    return out


def _opacity(selector):
    """Product of all opacity declarations on `selector` (worst case across rules)."""
    a = 1.0
    for body in _all_bodies(selector):
        for v in re.findall(r"(?:^|;|\s)opacity\s*:\s*([0-9.]+)", body):
            a *= float(v)
    return a


def _blend_on_white(hex_fg, alpha):
    c = [int(hex_fg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * alpha + 255 * (1 - alpha)):02X}" for x in c)


def _iron():
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    (v,) = set(re.findall(r"--lf-iron\s*:\s*(#[0-9A-Fa-f]{6})", css))
    return v.upper()


def test_dw138_blend_helper_known_answers():
    # Designer's measured failing values on the old CSS.
    assert _blend_on_white("#4D4D4D", 0.7) == "#828282"
    assert round(_contrast("#828282", "#FFFFFF"), 2) == 3.84
    assert _blend_on_white("#4D4D4D", 0.85 * 0.7) == "#959595"
    assert round(_contrast("#959595", "#FFFFFF"), 2) == 3.00


def test_dw138_mobile_tree_meta_has_no_opacity():
    bodies = _all_bodies(".mobile-tree-meta")
    assert bodies, "missing .mobile-tree-meta rule"
    assert _opacity(".mobile-tree-meta") == 1.0
    assert all("iron" in _decl(b, "color").lower() for b in bodies if "color" in b)


@pytest.mark.parametrize("row", ["region", "site", "conduit"])
def test_dw138_mobile_tree_meta_compound_contrast(row):
    alpha = _opacity(f".mobile-tree-row--{row}") * _opacity(".mobile-tree-meta")
    fg = _blend_on_white(_iron(), alpha)
    ratio = _contrast(fg, "#FFFFFF")
    assert ratio >= 4.5, (row, alpha, fg, round(ratio, 2))


# ---------------------------------------------------------------------------
# BUG-DW-143 / BUG-DW-144: WCAG 1.4.11 non-text contrast (>=3:1) for the
# /topology toolbar button, overlay toggle (border + unchecked dot) and the
# path-trace Clear button. Platinum #E8E8E8 on white was 1.23:1.
# Checked / hover states and .topo-chip must stay dark teal (unchanged).
# ---------------------------------------------------------------------------

def _root_vars():
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    return {k: v.upper() for k, v in re.findall(r"(--lf-[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{6})", css)}


def _resolve(value):
    """Hex colour of a declaration value: literal #hex or var(--lf-*)."""
    m = re.search(r"#[0-9A-Fa-f]{6}", value)
    if m:
        return m.group(0).upper()
    m = re.search(r"var\(\s*(--lf-[a-z-]+)", value, flags=re.I)
    assert m, value
    return _root_vars()[m.group(1).lower()]


def _base_body(selector):
    """The single top-level (non-@media) rule body for `selector`."""
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    bodies = re.findall(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert len(bodies) == 1, (selector, len(bodies))
    return bodies[0]


def _border_hex(body):
    m = re.findall(r"(?:^|;|\s)border\s*:\s*([^;]+);", body)
    assert len(m) == 1, body
    return _resolve(m[0])


def _blend_hex(fg_hex, alpha, bg_hex):
    f = [int(fg_hex[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg_hex[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(f, b))


def test_dw143_known_answers():
    v = _root_vars()
    assert v["--lf-platinum"] == "#E8E8E8"
    assert v["--lf-platinum-shade"] == "#858585"
    assert round(_contrast("#E8E8E8", "#FFFFFF"), 2) == 1.23
    assert round(_contrast("#858585", "#FFFFFF"), 2) == 3.69


@pytest.mark.parametrize("selector", [".topo-toolbar button", ".topo-toggle"])
def test_dw143_white_surface_borders_meet_3_to_1(selector):
    # Both controls set background: var(--lf-white) and sit on the white toolbar.
    body = _base_body(selector)
    assert _resolve(_decl(body, "background")) == "#FFFFFF"
    fg = _border_hex(body)
    assert fg != "#E8E8E8"
    assert _contrast(fg, "#FFFFFF") >= 3.0, (selector, fg)


def _path_trace_clear_surfaces():
    """Clear has background:none inside .path-trace-banner, which renders in a
    fragment directly in main.page-content (no white card) on the body.
    Surface = banner background teal tint (each gradient stop) over the body
    colour, plus the :hover platinum fill."""
    body_bg = _resolve(_decl(_base_body("body"), "background-color"))
    banner_bg = _decl(_base_body(".path-trace-banner"), "background")
    alphas = [float(a) for a in re.findall(r"RGBA\(0,\s*98,\s*114,\s*([0-9.]+)\)", banner_bg)]
    assert alphas, banner_bg
    hover = _resolve(_decl(_base_body(".path-trace-clear:hover"), "background"))
    return body_bg, [_blend_hex("#006272", a, body_bg) for a in alphas] + [hover]


def test_dw143_path_trace_clear_surface_known_answer():
    body_bg, surfaces = _path_trace_clear_surfaces()
    assert body_bg == "#E8E8E8"  # body is platinum, so white-only maths is wrong here
    # The designer's platinum-shade would fail on the 6% stop: 2.76:1.
    assert round(min(_contrast("#858585", s) for s in surfaces), 2) == 2.76


def test_dw143_path_trace_clear_on_banner_meets_3_to_1():
    body = _base_body(".path-trace-clear")
    assert "NONE" in _decl(body, "background")
    fg = _border_hex(body)
    _, surfaces = _path_trace_clear_surfaces()
    worst = min(_contrast(fg, s) for s in surfaces)
    assert worst >= 3.0, (fg, surfaces, round(worst, 2))


def test_dw144_unchecked_toggle_dot_meets_3_to_1():
    body = _base_body(".topo-toggle .toggle-dot")
    fg = _resolve(_decl(body, "background"))
    assert fg != "#E8E8E8"
    assert _contrast(fg, "#FFFFFF") >= 3.0, fg


@pytest.mark.parametrize("selector,prop", [
    ('.topo-toggle[aria-checked="true"]', "border-color"),
    ('.topo-toggle[aria-checked="true"] .toggle-dot', "background"),
    (".topo-toggle:hover", "border-color"),
    (".topo-toolbar button:hover", "border-color"),
])
def test_dw143_checked_and_hover_states_stay_dark_teal(selector, prop):
    assert _resolve(_decl(_base_body(selector), prop)) == "#006272"


def test_dw143_topo_chip_not_touched():
    bodies = _all_bodies(".topo-toolbar .topo-chip")
    assert bodies
    assert _resolve(_decl(_base_body(".topo-toolbar .topo-chip"), "border-color")
                    if "border-color" in _base_body(".topo-toolbar .topo-chip")
                    else _border_hex(_base_body(".topo-toolbar .topo-chip"))) == "#006272"
    assert not any("platinum-shade" in b for b in bodies)


# ---------------------------------------------------------------------------
# BUG-DW-145: score gauge track (WCAG 1.4.11). ScoreGauge renders in the
# service-table rows, so the track outline is checked against every row surface
# (white, platinum zebra, 5% teal hover). Fills are checked against the white interior.
# ---------------------------------------------------------------------------

GAUGE = ".score-gauge .gauge-bar"


def _score_token(name):
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    m = re.search(r"--score-" + name + r"\s*:\s*([^;]+);", css)
    assert m, name
    return _resolve(m.group(1))


def _row_surfaces():
    zebra = _resolve(_decl(_base_body(".data-table tbody tr:nth-child(even)"), "background"))
    hover_decl = _decl(_base_body(".data-table tbody tr:hover"), "background")
    m = re.search(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", hover_decl, flags=re.I)
    assert m, hover_decl
    fg = "#" + "".join(f"{int(m.group(i)):02X}" for i in (1, 2, 3))
    hover = _blend_hex(fg, float(m.group(4)), "#FFFFFF")
    return {"white": "#FFFFFF", "zebra": zebra, "hover": hover}


def test_dw145_known_answers():
    s = _row_surfaces()
    assert s["zebra"] == "#E8E8E8"
    assert s["hover"] == "#F2F7F8"
    assert round(_contrast("#858585", "#FFFFFF"), 2) == 3.69
    assert round(_contrast("#E8E8E8", "#FFFFFF"), 2) == 1.23  # designer's measured failing value


def test_dw145_gauge_track_has_platinum_shade_border():
    body = _base_body(GAUGE)
    assert "var(--lf-platinum-shade)" in body
    assert _border_hex(body) == "#858585"
    assert re.search(r"border\s*:\s*1px\s+solid", body)


@pytest.mark.parametrize("surface", ["white", "zebra", "hover"])
def test_dw145_track_outline_meets_3_to_1_on_every_row_surface(surface):
    border = _border_hex(_base_body(GAUGE))
    bg = _row_surfaces()[surface]
    assert _contrast(border, bg) >= 3.0, (surface, border, bg, _contrast(border, bg))


def test_dw145_track_interior_is_white():
    assert _resolve(_decl(_base_body(GAUGE), "background")) == "#FFFFFF"


@pytest.mark.parametrize("grade", ["excellent", "good", "poor", "failing"])
def test_dw145_fills_meet_3_to_1_on_white_interior(grade):
    interior = _resolve(_decl(_base_body(GAUGE), "background"))
    assert _contrast(_score_token(grade), interior) >= 3.0, grade


def test_dw145_no_media_rule_reintroduces_platinum_track():
    for b in _all_bodies(GAUGE):
        assert "var(--lf-platinum)" not in b.replace("var(--lf-platinum-shade)", ""), b
