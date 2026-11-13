"""BUG-DW-173 regression tests: /topology empty states (WCAG 1.4.3, brand icons, UX copy).

Acceptance (from @designer S117):
  1. Theme has a `.topo-canvas-wrap .empty-state` rule with color var(--lf-iron) (6.90:1 on platinum).
  2. No emoji characters inside any .empty-state block in ui/.
  3. No 'Gold tables' or 'pipeline' text in ui/ empty-hint copy.
  4. grep lumen = 0 in touched files.
These tests fail on HEAD e876744 (and 6cdc0f2) and pass after the fix.
"""
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_UI = _ROOT / "apps/resilience-scorecard/src/resilience_scorecard/ui"
_CSS = _UI / "styles/lakelink-theme.css"
_TOPO = _UI / "routes/topology.tsx"
_CROSSWALK = _UI / "components/hazards/hazard-crosswalk-table.tsx"

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def _lum(hex_: str) -> float:
    out = []
    for i in (1, 3, 5):
        c = int(hex_[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def _ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _var(src: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9A-Fa-f]{{6}})", src)
    assert m, f"{name} not defined"
    return m.group(1).upper()


def _empty_state_blocks(src: str) -> list[str]:
    """Return the JSX text from each className="empty-state" opening to its matching </div>."""
    blocks = []
    for m in re.finditer(r'<div className="empty-state"', src):
        depth, i = 0, m.start()
        tag = re.compile(r"<div\b|</div>")
        for t in tag.finditer(src, m.start()):
            depth += 1 if t.group(0) == "<div" else -1
            if depth == 0:
                blocks.append(src[m.start():t.end()])
                break
    return blocks


def _ui_files():
    return [p for p in _UI.rglob("*.tsx") if "node_modules" not in p.parts]


def test_topo_canvas_empty_state_rule_uses_iron():
    m = re.search(r"(?m)^\.topo-canvas-wrap \.empty-state\s*\{([^}]*)\}", _read(_CSS))
    assert m, ".topo-canvas-wrap .empty-state rule missing"
    assert re.search(r"color\s*:\s*var\(--lf-iron\)", m.group(1))


def test_iron_on_platinum_meets_aa():
    css = _read(_CSS)
    assert _ratio(_var(css, "--lf-iron"), _var(css, "--lf-platinum")) >= 4.5


def test_topo_canvas_wrap_is_platinum():
    m = re.search(r"(?m)^\.topo-canvas-wrap\s*\{([^}]*)\}", _read(_CSS))
    assert m and "var(--lf-platinum)" in m.group(1)


def test_default_empty_state_color_not_lowered():
    m = re.search(r"(?m)^\.empty-state\s*\{([^}]*)\}", _read(_CSS))
    assert m and "rgba(77, 77, 77, 0.8)" in m.group(1)


def test_topology_has_three_empty_states():
    assert len(_empty_state_blocks(_read(_TOPO))) == 3


def test_no_emoji_in_any_empty_state():
    offenders = []
    for p in _ui_files():
        for b in _empty_state_blocks(_read(p)):
            if _EMOJI.search(b):
                offenders.append(p.name)
    assert not offenders, offenders


def test_topology_empty_states_use_lucide_icons():
    src = _read(_TOPO)
    blocks = _empty_state_blocks(src)
    assert sum("<Network " in b for b in blocks) == 2
    assert sum("<MapPinOff " in b for b in blocks) == 1
    for b in blocks:
        assert re.search(r"size=\{32\}\s+strokeWidth=\{1\.5\}\s+aria-hidden=\"true\"", b)
    imp = re.search(r'import \{([^}]*)\} from "lucide-react";', src)
    assert imp and "Network" in imp.group(1) and "MapPinOff" in imp.group(1)


def test_no_jargon_in_empty_hints():
    offenders = []
    for p in _ui_files():
        for hint in re.findall(r'className="empty-hint">([^<]*)<', _read(p)):
            if re.search(r"gold tables|pipeline", hint, re.I):
                offenders.append((p.name, hint))
    assert not offenders, offenders


def test_topology_new_copy_present_twice():
    assert _read(_TOPO).count("Topology data is not available yet. Try again shortly.") == 2


def test_crosswalk_new_copy():
    src = _read(_CROSSWALK)
    assert "Hazard exposure data is not available yet." in src
    assert "intersection pipeline" not in src


def test_no_lumen_in_touched_files():
    for p in (_CSS, _TOPO, _CROSSWALK):
        assert "lumen" not in _read(p).lower(), p.name
