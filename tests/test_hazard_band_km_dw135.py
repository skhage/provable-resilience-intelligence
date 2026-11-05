"""BUG-DW-135: hazard proximity band labels use SI spacing (one space before km).

Designer ruling (S93): 'Direct Impact (<1 km)', 'Near Field (1\u20135 km)'
(U+2013 en dash kept), 'Buffer Zone (\u22655 km)' (U+2265 kept), and the KPI
label 'Direct Impact (&lt;1 km)'. Copy only; no class/colour change.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAZ = ROOT / "apps/resilience-scorecard/src/resilience_scorecard/ui/components/hazards"
TABLE = HAZ / "hazard-crosswalk-table.tsx"
KPIS = HAZ / "hazard-crosswalk-kpis.tsx"
UNIT_RE = re.compile(r"\d km\)$")


def _band_labels():
    src = TABLE.read_text(encoding="utf-8")
    block = re.search(r"const BAND_LABELS[^{]*\{(.*?)\};", src, re.S)
    assert block, "BAND_LABELS block not found"
    return dict(re.findall(r'(\w+):\s*"([^"]*)"', block.group(1)))


def _kpi_direct_label():
    src = KPIS.read_text(encoding="utf-8")
    labels = re.findall(r'<div className="kpi-label">([^<]*)</div>', src)
    direct = [lbl for lbl in labels if lbl.startswith("Direct Impact")]
    assert len(direct) == 1, labels
    return direct[0]


def test_band_labels_exact_copy():
    assert _band_labels() == {
        "direct_impact": "Direct Impact (<1 km)",
        "near_field": "Near Field (1\u20135 km)",
        "buffer_zone": "Buffer Zone (\u22655 km)",
    }


def test_all_band_labels_and_kpi_label_match_si_unit_pattern():
    labels = list(_band_labels().values()) + [_kpi_direct_label()]
    assert len(labels) == 4
    for label in labels:
        assert UNIT_RE.search(label), label


def test_kpi_direct_impact_label_exact():
    assert _kpi_direct_label() == "Direct Impact (&lt;1 km)"


def test_no_unspaced_km_in_hazard_components():
    for f in HAZ.glob("*.tsx"):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"\dkm\b", src), f.name


def test_dash_and_ge_glyphs_preserved():
    labels = _band_labels()
    assert "\u2013" in labels["near_field"] and "-" not in labels["near_field"]
    assert "\u2265" in labels["buffer_zone"] and ">=" not in labels["buffer_zone"]
