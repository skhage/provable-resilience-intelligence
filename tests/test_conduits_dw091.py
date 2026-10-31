"""BUG-DW-091: /conduits polish (binding, @designer S35/S40).

1) Inventory coverage pill must keep its shape on platinum zebra rows (it was platinum on platinum).
2) .coverage-warning left border is #C2410C (brand-orange #F26522 is < 3:1 on #FFF7ED, WCAG 1.4.11).
3) Contrast figures in the 'Conduit Coverage' CSS header comment must match measured values.
CSS-only; checked statically with a WCAG contrast calculator (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
CSS_PATH = os.path.join(UI, "styles", "lakelink-theme.css")

WARN_BG = "#FFF7ED"
WHITE = "#FFFFFF"


def _css():
    with open(CSS_PATH, encoding="utf-8") as f:
        return f.read()


def _rel_lum(hexc):
    h = hexc.lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _contrast(a, b):
    la, lb = sorted((_rel_lum(a), _rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _vars(css):
    return {k: v.upper() for k, v in re.findall(r"--(lf-[a-z-]+):\s*(#[0-9A-Fa-f]{6})", css)}


def _resolve(val, v):
    m = re.search(r"var\(--(lf-[a-z-]+)\)", val)
    if m:
        return v[m.group(1)]
    m = re.search(r"#[0-9A-Fa-f]{6}", val)
    return m.group(0).upper() if m else val


def _base_rule(css, selector):
    """Top-level (column-0) rule only, so media-query overrides are skipped."""
    pat = r"(?m)^" + r"\s+".join(re.escape(p) for p in selector.split()) + r"\s*\{([^}]*)\}"
    m = re.search(pat, css)
    assert m, selector
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    return dict((p.strip(), x.strip()) for p, x in
                (d.split(":", 1) for d in body.split(";") if ":" in d))


def _forced_colors_block(css):
    i = css.index(".coverage-badge { border-color: CanvasText; }")
    start = css.rfind("@media (forced-colors: active)", 0, i)
    assert start != -1
    return css[start:i + 60]


def test_contrast_helper_known_answers():
    assert round(_contrast("#006272", WHITE), 2) == 7.02
    assert round(_contrast("#000000", WHITE), 1) == 21.0
    assert round(_contrast(WHITE, WHITE), 1) == 1.0


def test_zebra_premise_is_platinum():
    css = _css()
    v = _vars(css)
    zebra = _resolve(_base_rule(css, ".data-table tbody tr:nth-child(even)")["background"], v)
    assert zebra == "#E8E8E8"


def test_badge_base_has_1px_border_so_border_color_renders():
    rule = _base_rule(_css(), ".badge")
    assert rule["border"].startswith("1px solid")


def test_inventory_pill_visible_on_zebra_and_white_rows():
    css = _css()
    v = _vars(css)
    zebra = _resolve(_base_rule(css, ".data-table tbody tr:nth-child(even)")["background"], v)
    inv = _base_rule(css, ".coverage-badge.cov-inv")
    bg = _resolve(inv["background"], v)
    border = _resolve(inv["border-color"], v)
    text = _resolve(inv["color"], v)
    assert bg != zebra, "pill fill must differ from the zebra row fill"
    # Pill boundary (outline) must meet 3:1 against both row fills (WCAG 1.4.11)
    assert _contrast(border, zebra) >= 3.0
    assert _contrast(border, WHITE) >= 3.0
    # Text on its own pill fill stays AA
    assert _contrast(text, bg) >= 4.5


def test_other_coverage_pills_unchanged():
    css = _css()
    assert _base_rule(css, ".coverage-badge.cov-real")["background"] == "#E0F2F1"
    assert _base_rule(css, ".coverage-badge.cov-bb")["background"] == "#FFEDD5"


def test_forced_colors_keeps_badge_outline():
    assert "border-color: CanvasText" in _forced_colors_block(_css())


def test_warning_border_is_c2410c_and_meets_non_text_contrast():
    css = _css()
    rule = _base_rule(css, ".coverage-warning")
    border = rule["border-left"]
    assert "#C2410C" in border.upper()
    assert "lf-accent-orange" not in border
    assert _contrast("#C2410C", WARN_BG) >= 3.0
    assert _contrast("#F26522", WARN_BG) < 3.0  # why the old token failed
    assert "coverage-warning { border-left-color: CanvasText; }" in css


def _header_comment(css):
    start = css.index("/* === Conduit Coverage (P35-APP-CONDUIT-COVERAGE-BADGE) ===")
    return css[start:css.index("*/", start)]


def test_header_comment_figures_match_measured_contrast():
    c = _header_comment(_css())
    expected = {
        "real": _contrast("#006272", "#E0F2F1"),
        "bb": _contrast("#9A3412", "#FFEDD5"),
        "inv": _contrast("#4D4D4D", WHITE),
    }
    badge_line = c[c.index("Badge text contrast"):c.index("Map lines")]
    for k, val in expected.items():
        m = re.search(k + r" (\d+\.\d+):1", badge_line)
        assert m, k
        assert abs(float(m.group(1)) - val) < 0.01, (k, m.group(1), val)
    line_part = c[c.index("Map lines"):]
    for k, color in (("real", "#006272"), ("bb", "#C2410C"), ("inv", "#858585")):
        m = re.search(k + r" " + color + r" (\d+\.\d+):1", line_part)
        assert m, k
        assert abs(float(m.group(1)) - _contrast(color, "#F7F9FA")) < 0.01
    # stale figures from the original comment must be gone
    assert "6.5:1" not in c and "5.53:1" not in c and "~" not in c


def test_inv_outline_figures_in_comment_match():
    c = _header_comment(_css())
    m = re.search(r"(\d+\.\d+):1 on platinum rows, (\d+\.\d+):1 on white rows", c)
    assert m
    assert abs(float(m.group(1)) - _contrast("#858585", "#E8E8E8")) < 0.01
    assert abs(float(m.group(2)) - _contrast("#858585", WHITE)) < 0.01


def test_no_old_brand_name():
    assert "lumen" not in _css().lower()
