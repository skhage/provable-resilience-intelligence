"""BUG-DW-171 regression tests: mobile tree search input resting border (WCAG 1.4.11).

Acceptance (from @designer S116):
  * .mobile-tree-search-input resting border uses var(--lf-platinum-shade), not var(--lf-platinum).
  * --lf-platinum-shade resolves to #858585: >= 3:1 on white (#FFFFFF) and on platinum (#E8E8E8).
  * :focus-visible keeps the dark-teal border and box-shadow.
  * No .mobile-tree-search-input rule anywhere re-applies a platinum border.
  * grep lumen = 0 in the theme file.
These tests fail on HEAD 6cdc0f2 and pass after the fix.
"""
import pathlib
import re

_CSS = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui/styles/lakelink-theme.css"
)


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _rules(src: str, selector: str):
    """Yield (selector_text, body) for every rule whose selector list contains selector exactly."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
        head = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
        sels = [s.strip() for s in head.split(",")]
        if selector in sels:
            yield m.group(1), m.group(2)


def _var(src: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9A-Fa-f]{{6}})", src)
    assert m, name
    return m.group(1)


def _lum(hex_: str) -> float:
    out = []
    for i in (1, 3, 5):
        c = int(hex_[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = out
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contrast_helper_known_values():
    assert round(_ratio("#000000", "#FFFFFF"), 1) == 21.0
    assert round(_ratio("#E8E8E8", "#FFFFFF"), 2) == 1.23


def test_resting_border_uses_platinum_shade():
    bodies = [b for _, b in _rules(_css(), ".mobile-tree-search-input")]
    assert len(bodies) >= 1
    base = bodies[0]
    assert re.search(r"border\s*:\s*2px solid var\(--lf-platinum-shade\)", base), base


def test_no_platinum_border_on_search_input_anywhere():
    for sel, body in _rules(_css(), ".mobile-tree-search-input"):
        assert not re.search(r"border(-color)?\s*:[^;]*var\(--lf-platinum\)", body), sel


def test_platinum_shade_meets_non_text_contrast():
    src = _css()
    shade = _var(src, "--lf-platinum-shade")
    assert shade.upper() == "#858585"
    assert _ratio(shade, "#FFFFFF") >= 3.0
    assert _ratio(shade, _var(src, "--lf-platinum")) >= 3.0


def test_wrapper_background_is_white():
    bodies = [b for _, b in _rules(_css(), ".mobile-tree-search")]
    if bodies:
        assert "var(--lf-white)" in bodies[0]


def test_focus_visible_unchanged():
    bodies = [b for _, b in _rules(_css(), ".mobile-tree-search-input:focus-visible")]
    assert bodies, "focus-visible rule missing"
    b = bodies[0]
    assert "border-color: var(--lf-dark-teal)" in b
    assert "box-shadow: 0 0 0 3px rgba(0, 98, 114, 0.15)" in b


def test_placeholder_rule_unchanged():
    bodies = [b for _, b in _rules(_css(), ".mobile-tree-search-input::placeholder")]
    assert bodies and "color: var(--lf-iron)" in bodies[0]


def test_no_lumen_in_theme():
    assert "lumen" not in _css().lower()
