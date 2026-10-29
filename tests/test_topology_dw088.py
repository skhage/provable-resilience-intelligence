"""BUG-DW-088: /topology SRLG badge '+N' label must not collide with the critical outer ring.

Geometry is checked numerically (glyph box vs ring stroke band, 100% and 200% zoom), the
halo + forced-colors CSS statically, and maxSrlgSeverity is computed once per conduit.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import math
import os
import re

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))

# Badge geometry from topology.tsx (BUG-DW-087): inner r=8 stroke<=3, critical outer r=11 stroke 1.5.
INNER_R, INNER_SW = 8.0, 3.0
OUTER_R, OUTER_SW = 11.0, 1.5
FONT_PX = 10.0          # .srlg-badge-extra font size
CAP_HEIGHT = 0.73       # Inter cap/figure height ratio (digits and '+' sit within it)
ADVANCE = 0.62          # generous per-glyph advance for Inter 600 digits/'+'
HALO_SW = 3.0           # .srlg-badge-extra stroke-width (halo)


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _label_anchor(src):
    x = int(re.search(r"const SRLG_EXTRA_LABEL_X = (-?\d+);", src).group(1))
    y = int(re.search(r"const SRLG_EXTRA_LABEL_Y = (-?\d+);", src).group(1))
    return x, y


def _glyph_box(x, y, chars=2, scale=1.0):
    """text-anchor start + alphabetic baseline: box spans [x, x+w] x [y-cap, y]."""
    w = chars * ADVANCE * FONT_PX
    return (x * scale, (y - CAP_HEIGHT * FONT_PX) * scale, (x + w) * scale, y * scale)


def _min_dist(box):
    x0, y0, x1, y1 = box
    dx = 0.0 if x0 <= 0 <= x1 else min(abs(x0), abs(x1))
    dy = 0.0 if y0 <= 0 <= y1 else min(abs(y0), abs(y1))
    return math.hypot(dx, dy)


def _clears_rings(x, y, scale):
    """True if glyph box (inflated by half the halo) stays outside the outer ring stroke band."""
    inner_edge = _min_dist(_glyph_box(x, y, scale=scale)) - (HALO_SW / 2) * scale
    outer_ring_out = (OUTER_R + OUTER_SW / 2) * scale
    return inner_edge > outer_ring_out


def test_known_answer_old_anchor_collides():
    # Designer's evidence: (9,-7) is ~11.4px from centre, inside the 10.25-11.75 ring band.
    d = _min_dist(_glyph_box(9, -7))
    assert d == pytest.approx(11.40, abs=0.01)
    assert (OUTER_R - OUTER_SW / 2) <= d <= (OUTER_R + OUTER_SW / 2)
    assert not _clears_rings(9, -7, 1.0)


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_new_anchor_clears_both_rings(scale):
    x, y = _label_anchor(_read("routes", "topology.tsx"))
    assert (x, y) == (13, -10)
    assert _clears_rings(x, y, scale)
    # and clear of the inner ring stroke as well
    assert _min_dist(_glyph_box(x, y, scale=scale)) > (INNER_R + INNER_SW / 2) * scale


def test_label_uses_anchor_constants_everywhere():
    src = _read("routes", "topology.tsx")
    assert "x={9} y={-7}" not in src
    m = re.search(r'<text x=\{(\w+)\} y=\{(\w+)\} className="srlg-badge-extra">', src)
    assert m and m.groups() == ("SRLG_EXTRA_LABEL_X", "SRLG_EXTRA_LABEL_Y")
    # route file keeps a single export (TanStack code-splitting)
    assert re.findall(r"(?m)^export ", src) == ["export "]


def test_max_severity_computed_once_per_conduit():
    src = _read("routes", "topology.tsx")
    calls = re.findall(r"maxSrlgSeverity\(", src)
    assert len(calls) == 2, "definition + single memoised call expected"
    assert "maxSrlgSeverity(srlgs.filter(" not in src
    assert "const srlgSevByConduit = useMemo(" in src
    assert src.count("srlgSevByConduit.get(c.conduit_id)") == 3  # glow, aria-label, badge
    block = src[src.index('className="srlg-badge-layer"'):]
    block = block[:block.index("</g>\n      )}")]
    assert "isCritical && (" in block and "strokeWidth={isCritical ? 3 : 2}" in block


def _rule(css, selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_halo_css():
    css = _read("styles", "lakelink-theme.css")
    body = _rule(css, ".srlg-badge-extra")
    assert re.search(r"paint-order:\s*stroke;", body)
    assert re.search(r"stroke:\s*#FFFFFF;", body, re.I)
    assert re.search(r"stroke-width:\s*3px;", body)
    assert re.search(r"fill:\s*var\(--lf-iron\);", body)


def test_halo_forced_colors():
    css = _read("styles", "lakelink-theme.css")
    blocks = re.findall(r"@media \(forced-colors: active\) \{([^@]*?)\n\}", css)
    hit = [b for b in blocks if ".srlg-badge-extra" in b]
    assert hit, "forced-colors rule for .srlg-badge-extra missing"
    assert re.search(r"\.srlg-badge-extra\s*\{[^}]*stroke:\s*Canvas;", hit[0])


def test_legend_unchanged():
    src = _read("routes", "topology.tsx")
    assert '<circle cx="13" cy="13" r="11" className="srlg-badge-critical-ring" stroke={BRAND.iron} strokeWidth="1.5" fill="none" />' in src
    assert '<circle cx="13" cy="13" r="8" className="srlg-badge-ring" stroke={BRAND.iron} strokeWidth="3" />' in src
    assert "Double ring = critical severity" in src


def test_no_old_brand_name():
    for rel in (("routes", "topology.tsx"), ("styles", "lakelink-theme.css")):
        assert "lumen" not in _read(*rel).lower()
