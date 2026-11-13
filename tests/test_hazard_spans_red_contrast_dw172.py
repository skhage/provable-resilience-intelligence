"""BUG-DW-172 regression tests: risk-red table text contrast (WCAG 1.4.3).

Acceptance (from @designer S116):
  * hazard-summary-table spans_affected > 5 no longer uses inline var(--lf-risk-red) (#D32F2F, 4.06:1 on platinum zebra).
  * The emphasized number uses a CSS class whose color is #B71C1C (>= 4.5:1 on white, platinum zebra and teal hover rows).
  * Same fix applied to hazard-crosswalk-table direct_impact intersection counts (same pattern, same failure).
  * No .tsx file applies var(--lf-risk-red) as an inline text color.
  * grep lumen = 0 in touched files.
These tests fail on HEAD 9bba952 and pass after the fix.
"""
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_UI = _ROOT / "apps/resilience-scorecard/src/resilience_scorecard/ui"
_CSS = _UI / "styles/lakelink-theme.css"
_SUMMARY = _UI / "components/hazards/hazard-summary-table.tsx"
_CROSSWALK = _UI / "components/hazards/hazard-crosswalk-table.tsx"


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


def _blend(fg: str, bg: str, alpha: float) -> str:
    ch = [round(int(fg[i:i + 2], 16) * alpha + int(bg[i:i + 2], 16) * (1 - alpha)) for i in (1, 3, 5)]
    return "#" + "".join(f"{c:02X}" for c in ch)


def _var(src: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9A-Fa-f]{{6}})", src)
    assert m, f"{name} not defined"
    return m.group(1).upper()


def _rule_body(src: str, selector: str) -> str:
    m = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", src)
    assert m, f"{selector} rule missing"
    return m.group(1)


def test_summary_table_no_inline_risk_red():
    assert "var(--lf-risk-red)" not in _read(_SUMMARY)


def test_summary_table_spans_uses_class():
    assert re.search(r'spans_affected\s*>\s*5\s*\?\s*"text-risk-strong"', _read(_SUMMARY))


def test_crosswalk_table_no_inline_risk_red():
    assert "var(--lf-risk-red)" not in _read(_CROSSWALK)


def test_crosswalk_direct_impact_uses_class():
    assert re.search(r'"direct_impact"\s*\?\s*"text-risk-strong', _read(_CROSSWALK))


def test_text_token_value():
    assert _var(_read(_CSS), "--lf-risk-red-text") == "#B71C1C"


def test_text_risk_strong_uses_token():
    body = _rule_body(_read(_CSS), ".text-risk-strong")
    assert re.search(r"color\s*:\s*var\(--lf-risk-red-text\)", body)


def test_contrast_all_row_backgrounds():
    src = _read(_CSS)
    fg = _var(src, "--lf-risk-red-text")
    white, plat, teal = "#FFFFFF", _var(src, "--lf-platinum"), _var(src, "--lf-dark-teal")
    backgrounds = {
        "white": white,
        "platinum zebra": plat,
        "teal hover over white": _blend(teal, white, 0.05),
        "teal hover over platinum": _blend(teal, plat, 0.05),
    }
    for name, bg in backgrounds.items():
        assert _ratio(fg, bg) >= 4.5, f"{name}: {_ratio(fg, bg):.2f}:1"


def test_old_red_fails_on_zebra_documented():
    """Sanity check that the bug was real: #D32F2F is below 4.5:1 on platinum."""
    src = _read(_CSS)
    assert _ratio(_var(src, "--lf-risk-red"), _var(src, "--lf-platinum")) < 4.5


def test_semibold_declared_after_risk_strong():
    src = _read(_CSS)
    assert src.index(".text-semibold") > src.index(".text-risk-strong {")


def test_no_tsx_inline_risk_red_text():
    offenders = []
    for p in _UI.rglob("*.tsx"):
        if "node_modules" in p.parts:
            continue
        if re.search(r"color\s*:\s*[\"']var\(--lf-risk-red\)", _read(p)):
            offenders.append(str(p.relative_to(_UI)))
    assert not offenders, offenders


def test_no_lumen_in_touched_files():
    for p in (_CSS, _SUMMARY, _CROSSWALK):
        assert "lumen" not in _read(p).lower(), p.name
