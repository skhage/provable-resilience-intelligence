"""BUG-DW-174 regression tests: /topology legend + canvas hazard markers use Lucide, not emoji.

Acceptance (from @designer S123, BRAND-GUIDE §6, forced-colors):
  1. No emoji code points (U+1F300-1FAFF, U+2600-27BF) anywhere in ui/routes/topology.tsx.
  2. The SRLG legend renders SRLG_PANEL_ICONS (via SrlgPanelIcon); the emoji SRLG_ICONS map is gone.
  3. Canvas hazard markers render a Lucide icon from HazardTypeCell's HAZARD_ICONS map; no emoji map.
  4. hazard-type-cell.tsx JSDoc no longer shows an emoji.
  5. grep lumen = 0 in touched files.
These tests fail on HEAD f6b756f (and 9bba952) and pass after the fix.
"""
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_UI = _ROOT / "apps/resilience-scorecard/src/resilience_scorecard/ui"
_TOPO = _UI / "routes/topology.tsx"
_HTC = _UI / "components/hazards/hazard-type-cell.tsx"

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def _legend_srlg_section(src: str) -> str:
    start = src.index("Shared Risk Groups (edge badge)")
    end = src.index("Double ring = critical severity", start)
    return src[start:end]


def test_no_emoji_code_points_in_topology():
    src = _read(_TOPO)
    hits = [(src.count("\n", 0, m.start()) + 1, m.group()) for m in _EMOJI.finditer(src)]
    assert hits == [], f"emoji code points in topology.tsx: {hits}"


def test_no_variation_selector_or_info_emoji():
    src = _read(_TOPO)
    assert "\ufe0f" not in src
    assert "\u2139" not in src


def test_emoji_srlg_icons_map_removed():
    assert re.search(r"\bSRLG_ICONS\b", _read(_TOPO)) is None


def test_legend_uses_srlg_panel_icons():
    legend = _legend_srlg_section(_read(_TOPO))
    assert "<SrlgPanelIcon type={k} />" in legend
    src = _read(_TOPO)
    m = re.search(r"function SrlgPanelIcon[\s\S]*?SRLG_PANEL_ICONS\[type\]", src)
    assert m, "SrlgPanelIcon must resolve icons from SRLG_PANEL_ICONS"


def test_panel_icon_props_decorative():
    src = _read(_TOPO)
    m = re.search(r"const PANEL_ICON_PROPS = \{([^}]*)\}", src)
    assert m
    props = m.group(1)
    for needle in ("size: 16", "strokeWidth: 1.5", '"aria-hidden": true', 'focusable: "false"'):
        assert needle in props


def test_emoji_hazard_icons_map_removed_from_topology():
    src = _read(_TOPO)
    assert re.search(r"const HAZARD_ICONS\s*:", src) is None
    assert "HAZARD_ICONS[h.hazard_type]" not in src


def test_topology_imports_lucide_hazard_map():
    src = _read(_TOPO)
    assert re.search(
        r'import \{[^}]*HAZARD_ICONS as HAZARD_TYPE_ICONS[^}]*\} from "@/components/hazards/hazard-type-cell"',
        src,
    )


def test_hazard_marker_uses_lucide_component():
    src = _read(_TOPO)
    m = re.search(r"function HazardMarkerIcon\([\s\S]*?\n\}\n", src)
    assert m, "HazardMarkerIcon helper missing"
    body = m.group(0)
    assert "HAZARD_TYPE_ICONS[type] ?? AlertTriangle" in body
    for needle in ('aria-hidden="true"', 'focusable="false"', "strokeWidth={1.5}", "color={color}"):
        assert needle in body
    assert "<HazardMarkerIcon type={h.hazard_type} cx={hx} cy={hy} color={hazColor} />" in src


def test_hazard_marker_icon_size_in_range():
    m = re.search(r"const HAZARD_MARKER_ICON_SIZE = (\d+);", _read(_TOPO))
    assert m and 14 <= int(m.group(1)) <= 16


def test_hazard_marker_keeps_name_label():
    src = _read(_TOPO)
    marker = src.index("<HazardMarkerIcon type={h.hazard_type}")
    assert "{h.name.slice(0, 20)}" in src[marker:marker + 1200]


def test_hazard_type_cell_lucide_map_and_doc():
    src = _read(_HTC)
    assert _EMOJI.search(src) is None
    assert "Renders: Lucide Flame icon" in src
    assert re.search(r"export \{[^}]*HAZARD_ICONS", src)


def test_lumen_absent_in_touched_files():
    for p in (_TOPO, _HTC):
        assert "lumen" not in _read(p).lower(), p
