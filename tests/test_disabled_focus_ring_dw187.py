"""BUG-DW-187: dimmed (aria-disabled) pagination and path-trace Retry buttons keep a full-strength focus ring.

`opacity` on an element also dims its outline. Boundary Prev/Next (DW-109/DW-184) and the in-flight
path-trace Retry (DW-105) stay in the tab order while dimmed, so on :focus-visible the opacity must be
restored to 1 (or the dim must not use opacity at all). Source-parses lakelink-theme.css (no browser here)
and checks the cascade outcome: last matching top-level rule with the higher specificity wins.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent
       / "apps/resilience-scorecard/src/resilience_scorecard/ui/styles/lakelink-theme.css")

TEAL = (0x00, 0x62, 0x72)
WHITE = (0xFF, 0xFF, 0xFF)
PLATINUM = (0xE8, 0xE8, 0xE8)

# (dimmed selector as written in the theme, its focus-visible variant)
TARGETS = {
    "pagination": ('.pagination-bar button[aria-disabled="true"]',
                   '.pagination-bar button[aria-disabled="true"]:focus-visible'),
    "path_trace_retry": (".path-trace-retry[aria-disabled]",
                         ".path-trace-retry[aria-disabled]:focus-visible"),
}


def _rules(css):
    """Return [(media_or_None, [selectors], {prop: value}, order)] with comments stripped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, order = [], 0

    def parse_block(text, media):
        nonlocal order
        pos = 0
        while True:
            ob = text.find("{", pos)
            if ob == -1:
                return
            head = text[pos:ob].strip()
            depth, j = 1, ob + 1
            while depth and j < len(text):
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            body = text[ob + 1:j - 1]
            if head.startswith("@media") or head.startswith("@supports"):
                parse_block(body, head)
            elif not head.startswith("@"):
                props = {}
                for decl in body.split(";"):
                    if ":" in decl:
                        k, v = decl.split(":", 1)
                        props[k.strip().lower()] = v.strip()
                sels = [re.sub(r"\s+", " ", s.strip()) for s in head.split(",")]
                out.append((media, sels, props, order))
                order += 1
            pos = j

    parse_block(css, None)
    return out


def _norm(sel):
    return re.sub(r"\s+", " ", sel.strip())


@pytest.fixture(scope="module")
def rules():
    return _rules(CSS.read_text(encoding="utf-8"))


def _top_level_with(rules, selector, prop):
    return [r for r in rules if r[0] is None and _norm(selector) in r[1] and prop in r[2]]


def _float(v):
    return float(v.replace("!important", "").strip())


def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _blend(fg, bg, alpha):
    return tuple(round(alpha * f + (1 - alpha) * g) for f, g in zip(fg, bg))


def _effective_focus_opacity(rules, key):
    """Opacity a focused dimmed button ends up with (outside forced-colors)."""
    dim_sel, focus_sel = TARGETS[key]
    dim = _top_level_with(rules, dim_sel, "opacity")
    focus = _top_level_with(rules, focus_sel, "opacity")
    if not dim:
        return 1.0  # dim does not use opacity at all (acceptable alternative)
    if focus:
        # focus variant has strictly higher specificity (+1 pseudo-class), so it wins regardless of order
        return _float(focus[-1][2]["opacity"])
    return _float(dim[-1][2]["opacity"])


def test_contrast_helper_matches_designer_numbers():
    # Known answers from the DW-187 report: teal ring at 0.4 on white ~ #99C0C7 = 1.96:1; full = 7.02:1.
    assert _blend(TEAL, WHITE, 0.4) == (0x99, 0xC0, 0xC7)
    assert round(_contrast(_blend(TEAL, WHITE, 0.4), WHITE), 2) == 1.96
    assert round(_contrast(TEAL, WHITE), 2) == 7.02


@pytest.mark.parametrize("key", list(TARGETS))
def test_focus_visible_rule_restores_opacity(rules, key):
    dim_sel, focus_sel = TARGETS[key]
    dim = _top_level_with(rules, dim_sel, "opacity")
    if not dim:
        return  # alternative fix: no opacity on the dimmed selector
    focus = _top_level_with(rules, focus_sel, "opacity")
    assert focus, f"missing top-level '{focus_sel} {{ opacity: 1 }}' rule"
    assert _float(focus[-1][2]["opacity"]) == 1.0


@pytest.mark.parametrize("key", list(TARGETS))
@pytest.mark.parametrize("bg", [WHITE, PLATINUM], ids=["white", "platinum"])
def test_focused_ring_meets_3_to_1(rules, key, bg):
    alpha = _effective_focus_opacity(rules, key)
    ring = _blend(TEAL, bg, alpha)
    assert _contrast(ring, bg) >= 3.0, f"{key} ring {ring} at opacity {alpha} on {bg}"


@pytest.mark.parametrize("key", list(TARGETS))
def test_resting_dim_preserved(rules, key):
    # Keep the dimmed resting visual (designer: keep resting state, cursor, forced-colors rules).
    dim_sel, _ = TARGETS[key]
    dim = [r for r in rules if r[0] is None and dim_sel in r[1]]
    assert dim, f"{dim_sel} rule missing"
    props = {k: v for r in dim for k, v in r[2].items()}
    assert props.get("cursor") == "default"
    assert "opacity" in props and _float(props["opacity"]) < 1.0


def test_forced_colors_graytext_kept(rules):
    fc = [r for r in rules if r[0] and "forced-colors" in r[0]]
    pag = [r for r in fc if TARGETS["pagination"][0] in r[1]]
    ret = [r for r in fc if TARGETS["path_trace_retry"][0] in r[1]]
    assert pag and pag[0][2].get("color") == "GrayText"
    assert ret and ret[0][2].get("color") == "GrayText"


def test_hover_exclusion_kept(rules):
    sel = '.pagination-bar button:not(:disabled):not([aria-disabled="true"]):hover'
    assert any(r[0] is None and sel in r[1] for r in rules)


def test_focus_ring_outline_unchanged(rules):
    for sel in (".pagination-bar button:focus-visible", ".path-trace-retry:focus-visible"):
        r = [x for x in rules if x[0] is None and sel in x[1] and "outline" in x[2]]
        assert r, sel
        assert r[-1][2]["outline"].startswith("2px solid")
