"""BUG-DW-176 regression tests: SLA tier lookup is case/separator-insensitive.

Acceptance (from @designer S127):
  * 'Premium' -> tier-premium (label 'Premium'; the spec's 'Premium+' label is the
    premium_plus tier, see SLA_TIER_BADGE).
  * 'PREMIUM_PLUS' and 'premium-plus' -> tier-premium-plus / 'Premium+'.
  * ' Standard ' -> tier-standard.
  * 'gold_plus' -> neutral 'Gold Plus'; null/empty -> neutral 'Unknown'.
  * The 18 DW-169 tests still pass; grep lumen = 0.
The helper block is run with `node --experimental-strip-types`.
These behaviour tests fail on 51f0950 and pass after the fix.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

_TSX = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui/components/dashboard/product-catalog.tsx"
)
_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="node not available")


def _src() -> str:
    return _TSX.read_text(encoding="utf-8")


def _run(expr: str):
    src = _src()
    block = src[src.index("export const SLA_TIER_BADGE"):src.index("const SERVICE_TYPE_LABELS")]
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "h.mts"
        p.write_text(block + f"\nconsole.log(JSON.stringify({expr}));\n", encoding="utf-8")
        out = subprocess.run(
            [_NODE, "--experimental-strip-types", "--no-warnings", str(p)],
            capture_output=True, text=True, timeout=60,
        )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_node
@pytest.mark.parametrize(
    "tier,label,cls",
    [
        ("Premium", "Premium", "tier-premium"),
        ("PREMIUM", "Premium", "tier-premium"),
        ("PREMIUM_PLUS", "Premium+", "tier-premium-plus"),
        ("premium-plus", "Premium+", "tier-premium-plus"),
        ("Premium-Plus", "Premium+", "tier-premium-plus"),
        ("premium plus", "Premium+", "tier-premium-plus"),
        (" Standard ", "Standard", "tier-standard"),
        ("premium_plus", "Premium+", "tier-premium-plus"),
    ],
)
def test_mixed_case_and_separator_tiers_map_to_tier_badges(tier, label, cls):
    assert _run(f"slaTierBadge({json.dumps(tier)})") == {"label": label, "className": cls}


@needs_node
@pytest.mark.parametrize(
    "tier,label",
    [("gold_plus", "Gold Plus"), ("Gold-Plus", "Gold Plus"), (None, "Unknown"), ("", "Unknown"), ("   ", "Unknown")],
)
def test_unknown_and_empty_stay_neutral(tier, label):
    assert _run(f"slaTierBadge({json.dumps(tier)})") == {"label": label, "className": "neutral"}


@needs_node
@pytest.mark.parametrize("tier", ["constructor", "toString", "__proto__"])
def test_prototype_keys_are_not_treated_as_tiers(tier):
    got = _run(f"slaTierBadge({json.dumps(tier)})")
    assert got["className"] == "neutral"


@needs_node
def test_normalize_tier_key():
    got = _run('["  PREMIUM--Plus ", "Standard", "_premium_"].map(normalizeTierKey)')
    assert got == ["premium_plus", "standard", "premium"]


def test_no_lumen_in_product_catalog():
    assert "lumen" not in _src().lower()
