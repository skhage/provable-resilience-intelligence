"""BUG-DW-180 regression tests: the default .info-tooltip stays inside the viewport (WCAG 1.4.10).

Acceptance (from @designer S131 / P215):
  * The global .info-tooltip max-width contains calc(100vw (min(260px, calc(100vw - 32px))).
  * .info-tooltip--align-start / --align-end exist (left:0 or right:0, transform:none).
  * InfoTooltip measures getBoundingClientRect() on open and applies the modifier.
  * BUG-DW-092 hover bridge, BUG-DW-093 z-index 150 and the colour tokens are unchanged.
Beyond the spec: when neither edge anchor fits (260px tooltip, trigger at x=100 in a 320px
viewport), the centred tooltip is clamped with --info-tooltip-shift. The placement helper is run
with `node --experimental-strip-types` over a sweep of trigger positions at 320px, 375px,
640px (1280px at 200% zoom) and 1280px, and every final box must sit inside the 16px margins
and overlap the trigger horizontally (so the hover bridge still connects).
The runtime 320px / 200% browser check stays in P84.
"""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI = ROOT / "apps" / "resilience-scorecard" / "src" / "resilience_scorecard" / "ui"
CSS_PATH = UI / "styles" / "lakelink-theme.css"
TSX_PATH = UI / "components" / "ui" / "info-tooltip.tsx"
CSS = CSS_PATH.read_text(encoding="utf-8")
TSX = TSX_PATH.read_text(encoding="utf-8")
_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="node not available")
MARGIN = 16


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _top_level_rules(css: str):
    css = _strip_comments(css)
    depth, start, head, body_start = 0, 0, None, 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                head = css[start:i].strip()
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                if head is not None and not head.startswith("@"):
                    yield [s.strip() for s in head.split(",")], css[body_start:i]
                start = i + 1
                head = None


def _decls(selector: str) -> dict:
    out = {}
    for sels, body in _top_level_rules(CSS):
        if selector in sels:
            for d in body.split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    out[k.strip()] = re.sub(r"\s+", " ", v.strip())
    return out


# ---------------------------------------------------------------- CSS

def test_global_tooltip_width_clamped_to_viewport():
    mw = _decls(".info-tooltip").get("max-width", "")
    assert "calc(100vw" in mw
    m = re.fullmatch(r"min\((\d+)px, calc\(100vw - (\d+)px\)\)", mw)
    assert m, mw
    cap, gutter = int(m.group(1)), int(m.group(2))
    assert cap == 260
    assert gutter >= 2 * MARGIN
    assert min(cap, 320 - gutter) <= 320 - 2 * MARGIN


def test_align_start_modifier():
    d = _decls(".info-tooltip.info-tooltip--align-start")
    assert d == {"left": "0", "right": "auto", "transform": "none"}


def test_align_end_modifier():
    d = _decls(".info-tooltip.info-tooltip--align-end")
    assert d == {"left": "auto", "right": "0", "transform": "none"}


def test_default_tooltip_centred_with_zero_default_shift():
    d = _decls(".info-tooltip")
    assert d["left"] == "50%"
    assert d["transform"] == "translateX(calc(-50% + var(--info-tooltip-shift, 0px)))"
    assert d["bottom"] == "calc(100% + 6px)"


def test_dw092_bridge_dw093_zindex_and_tokens_unchanged():
    d = _decls(".info-tooltip")
    assert d["z-index"] == "150"
    assert d["border"] == "1px solid #4D4D4D"
    assert d["background"] == "#FFFFFF"
    assert d["color"] == "#4D4D4D"
    b = _decls(".info-tooltip::after")
    assert b == {
        "content": '""', "position": "absolute", "left": "0", "right": "0",
        "top": "100%", "height": "8px", "background": "transparent",
    }


def test_caption_variant_stays_left_anchored_over_modifiers():
    # Same specificity (0,2,0); the caption rule must come later and reset right.
    flat = _strip_comments(CSS)
    assert flat.index(".service-table-caption .info-tooltip {") > flat.index(".info-tooltip.info-tooltip--align-end")
    d = _decls(".service-table-caption .info-tooltip")
    assert d["left"] == "0" and d["right"] == "auto" and d["transform"] == "none"


# ---------------------------------------------------------------- TSX source

def test_component_measures_on_open_and_applies_modifier():
    assert "useLayoutEffect" in TSX
    assert TSX.count("getBoundingClientRect()") >= 2  # trigger + tooltip
    assert '"info-tooltip info-tooltip--align-start"' in TSX
    assert '"info-tooltip info-tooltip--align-end"' in TSX
    assert "className={ALIGN_CLASS[placement.align]}" in TSX
    assert '"--info-tooltip-shift"' in TSX
    assert 'window.addEventListener("resize", place)' in TSX
    assert 'window.removeEventListener("resize", place)' in TSX


def test_component_a11y_contract_unchanged():
    assert 'role="tooltip"' in TSX
    assert "aria-describedby={tipId}" in TSX
    assert "hidden={!open}" in TSX
    assert 'e.key === "Escape"' in TSX
    assert "HOVER_CLOSE_DELAY_MS = 150" in TSX


def test_no_banned_brand_string():
    banned = "lu" + "men"
    assert banned not in TSX.lower()


# ---------------------------------------------------------------- placement helper (node)

def _run(expr: str):
    block = TSX[TSX.index("export const TOOLTIP_VIEWPORT_MARGIN_PX"):TSX.index("const ALIGN_CLASS")]
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "h.mts"
        p.write_text(block + f"\nconsole.log(JSON.stringify({expr}));\n", encoding="utf-8")
        out = subprocess.run(
            [_NODE, "--experimental-strip-types", "--no-warnings", str(p)],
            capture_output=True, text=True, timeout=60,
        )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _box(tl, tw, w, placement):
    a, s = placement["align"], placement["shift"]
    if a == "start":
        left = tl
    elif a == "end":
        left = tl + tw - w
    else:
        left = tl + tw / 2 - w / 2 + s
    return left, left + w


@needs_node
@pytest.mark.parametrize(
    "tl,w,vw,align,shift",
    [
        (600, 260, 1280, "center", 0),   # desktop KPI card: unchanged
        (134, 260, 320, "center", 0),    # centred left = 146 - 130 = 16, exactly on the margin
        (133, 260, 320, "center", 1),    # 1px past the margin; start (133) > 44 does not fit -> +1px
        (20, 260, 320, "start", 0),      # first KPI card at 320px
        (260, 260, 320, "end", 0),       # trigger near the right edge
        (100, 260, 320, "center", 34),   # centred left -18; start 100 > 44, so clamp to 16 (+34)
        (200, 260, 320, "center", -38),  # centred left 82 > 44; end -36 < 16, so clamp to 44 (-38)
        (100, 260, 640, "start", 0),     # 1280px at 200% zoom
    ],
)
def test_placement_cases(tl, w, vw, align, shift):
    got = _run(f"computeTooltipPlacement({tl}, 24, {w}, {vw})")
    assert got == {"align": align, "shift": shift}


@needs_node
def test_sweep_every_box_inside_margins_and_touching_trigger():
    expr = (
        "(() => { const r = []; for (const vw of [320, 375, 640, 1280]) {"
        " for (const w of [Math.min(260, vw - 32), 120, 200]) {"
        " for (let tl = 16; tl <= vw - 16 - 24; tl += 1) {"
        " r.push([vw, w, tl, computeTooltipPlacement(tl, 24, w, vw)]); } } } return r; })()"
    )
    rows = _run(expr)
    assert len(rows) > 5000
    seen = set()
    for vw, w, tl, p in rows:
        left, right = _box(tl, 24, w, p)
        seen.add(p["align"])
        assert left >= MARGIN - 0.5, (vw, w, tl, p, left)
        assert right <= vw - MARGIN + 0.5, (vw, w, tl, p, right)
        assert left < tl + 24 and right > tl, (vw, w, tl, p)  # overlaps trigger (DW-092 bridge)
    assert seen == {"center", "start", "end"}
