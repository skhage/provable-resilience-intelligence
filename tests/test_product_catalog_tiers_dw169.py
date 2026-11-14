"""BUG-DW-169 regression tests: product catalog SLA tier badges use neutral Lakelink tokens.

Acceptance (from @designer S122, P191):
  * product-catalog.tsx references no severity-* class.
  * 3 tiers + unknown tier + Diverse Yes/No are covered.
  * CSS tier family exists with the contrast comments 7.02 / 6.07 / 6.90, no
    accent-orange #F26522 text, and a CanvasText (not LinkText) forced-colors border.
  * Empty-state hint uses no table names.
  * grep lumen = 0.
The pure helper block is run with `node --experimental-strip-types` when node
is available; otherwise those behaviour tests are skipped.
These tests fail on HEAD e47f230 and pass after the fix.
"""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

_UI = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui"
)
_TSX = _UI / "components/dashboard/product-catalog.tsx"
_CSS = _UI / "styles/lakelink-theme.css"


def _src() -> str:
    return _TSX.read_text(encoding="utf-8")


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _hex_lum(h: str) -> float:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a: str, b: str) -> float:
    la, lb = sorted([_hex_lum(a), _hex_lum(b)], reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


# ---- static source checks -------------------------------------------------

def test_no_severity_class_in_product_catalog():
    assert "severity-" not in _src()


def test_no_empty_classname_fallback():
    assert 'className: ""' not in _src()


def test_empty_state_copy_has_no_table_names():
    src = _src()
    assert "Product reference data is not available yet." in src
    assert "product_offering table" not in src
    assert "seeded" not in src


def test_no_lumen_in_touched_files():
    assert "lumen" not in _src().lower()
    assert "lumen" not in _css().lower()


def test_diverse_glyph_stays_aria_hidden_with_visible_text():
    src = _src()
    assert '<span aria-hidden="true">{p.is_diverse_eligible ? "\\u2713" : "\\u2717"}</span>' in src
    assert '{p.is_diverse_eligible ? "Yes" : "No"}' in src
    assert "diverseBadgeClass(p.is_diverse_eligible)" in src


# ---- CSS checks -----------------------------------------------------------

_TIER_RULES = {
    "tier-premium-plus": ("7.02:1", "#006272", "#FFFFFF"),
    "tier-premium": ("6.07:1", "#E0F2F1", "#006272"),
    "tier-standard": ("6.90:1", "#E8E8E8", "#4D4D4D"),
    "neutral": ("6.90:1", "#E8E8E8", "#4D4D4D"),
}


@pytest.mark.parametrize("cls", list(_TIER_RULES))
def test_tier_css_rule_and_contrast_comment(cls):
    comment, bg, fg = _TIER_RULES[cls]
    m = re.search(r"^\.badge\." + re.escape(cls) + r"\s*\{([^}]*)\}\s*/\*([^*]*)\*/", _css(), re.M)
    assert m, f".badge.{cls} rule with contrast comment missing"
    body, note = m.group(1), m.group(2)
    assert comment in note
    assert "F26522" not in body.upper() and "accent-orange" not in body
    # the documented ratio matches the WCAG formula
    assert f"{_ratio(bg, fg):.2f}:1" == comment


def test_forced_colors_tier_border_is_canvastext():
    css = _css()
    m = re.search(
        r"\.badge\.tier-premium-plus,\s*\.badge\.tier-premium,\s*\.badge\.tier-standard,\s*\.badge\.neutral\s*\{([^}]*)\}",
        css,
    )
    assert m, "forced-colors tier rule missing"
    body = m.group(1)
    assert "CanvasText" in body and "LinkText" not in body
    assert "solid" in body and "1px" in body
    # the rule sits inside a forced-colors block
    start = css.rfind("@media (forced-colors: active)", 0, m.start())
    assert start >= 0


# ---- behaviour checks (node) ----------------------------------------------

_NODE = shutil.which("node")


def _run_helpers(expr: str):
    src = _src()
    a = src.index("export const SLA_TIER_BADGE")
    b = src.index("const SERVICE_TYPE_LABELS")
    block = src[a:b]
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "h.mts"
        p.write_text(block + f"\nconsole.log(JSON.stringify({expr}));\n", encoding="utf-8")
        out = subprocess.run(
            [_NODE, "--experimental-strip-types", "--no-warnings", str(p)],
            capture_output=True, text=True, timeout=60,
        )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


needs_node = pytest.mark.skipif(_NODE is None, reason="node not available")


@needs_node
@pytest.mark.parametrize(
    "tier,label,cls",
    [
        ("premium_plus", "Premium+", "tier-premium-plus"),
        ("premium", "Premium", "tier-premium"),
        ("standard", "Standard", "tier-standard"),
    ],
)
def test_known_tiers(tier, label, cls):
    assert _run_helpers(f"slaTierBadge({json.dumps(tier)})") == {"label": label, "className": cls}


@needs_node
@pytest.mark.parametrize(
    "tier,label",
    [("gold_plus", "Gold Plus"), ("ENTERPRISE", "Enterprise"), (None, "Unknown"), ("", "Unknown")],
)
def test_unknown_tier_is_neutral_and_title_cased(tier, label):
    got = _run_helpers(f"slaTierBadge({json.dumps(tier)})")
    assert got == {"label": label, "className": "neutral"}


@needs_node
def test_diverse_yes_no():
    assert _run_helpers("[diverseBadgeClass(true), diverseBadgeClass(false)]") == ["completed", "neutral"]
