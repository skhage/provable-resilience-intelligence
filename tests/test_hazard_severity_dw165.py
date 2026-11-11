"""BUG-DW-165 regression tests: hazard severity badges and hazard error fallbacks.

Acceptance (from @designer S115, P172):
  (a) No hazard severity value (critical/high/medium/low) maps to an undefined
      badge class. The class list is parsed from lakelink-theme.css.
      Labels are capitalized. Each fg/bg pair is >= 4.5:1. Forced-colors
      rules cover every mapped class.
  (b) The 4 hazard ErrorBoundary fallbacks have role="alert" on the
      container, not on the Retry button.
  (c) grep lumen = 0.
The TSX is parsed as text because serverless has no JSX transpiler.
These tests fail on HEAD 22ed333 / 86df7f0 and pass after the fix.
"""
import pathlib
import re

import pytest

_UI = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui"
)
_HAZ = _UI / "components/hazards"
_CSS = _UI / "styles/lakelink-theme.css"
_TABLE = _HAZ / "hazard-summary-table.tsx"
_FALLBACK_FILES = [
    "hazard-kpi-row.tsx",
    "hazard-summary-table.tsx",
    "hazard-crosswalk-kpis.tsx",
    "hazard-crosswalk-table.tsx",
]
# Live distinct values in geographic_hazard_event.severity (8,276 active rows).
LIVE_SEVERITIES = ["critical", "high", "medium", "low"]


@pytest.fixture(scope="module")
def css() -> str:
    return _CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table_src() -> str:
    return _TABLE.read_text(encoding="utf-8")


def _badge_classes(css: str) -> dict:
    """Return {class: (bg, fg)} for every `.badge.severity-X { background; color }` rule."""
    out = {}
    for m in re.finditer(r"\.badge\.(severity-[a-z]+)\s*\{([^}]*)\}", css):
        body = m.group(2)
        bg = re.search(r"background:\s*(#[0-9A-Fa-f]{6})", body)
        fg = re.search(r"(?<!-)color:\s*(#[0-9A-Fa-f]{6})", body)
        out[m.group(1)] = (bg and bg.group(1), fg and fg.group(1))
    return out


def _badge_map(src: str) -> dict:
    m = re.search(r"SEVERITY_BADGE_CLASS[^=]*=\s*\{([^}]*)\}", src)
    assert m, "SEVERITY_BADGE_CLASS lookup not found in hazard-summary-table.tsx"
    return dict(re.findall(r"(\w+)\s*:\s*\"(severity-[a-z]+)\"", m.group(1)))


def _lum(hex_: str) -> float:
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---------- (a) severity badge mapping --------------------------------------


def test_contrast_helper_known_pair():
    """Positive control: black on white is 21:1."""
    assert round(_contrast("#000000", "#FFFFFF"), 1) == 21.0


def test_badge_no_raw_severity_interpolation(table_src: str):
    """The old `severity-${h.severity}` interpolation must be gone."""
    assert "severity-${h.severity}" not in table_src


@pytest.mark.parametrize("sev", LIVE_SEVERITIES)
def test_every_live_severity_maps_to_defined_class(sev, css, table_src):
    classes = _badge_classes(css)
    mapping = _badge_map(table_src)
    assert sev in mapping, f"severity '{sev}' missing from SEVERITY_BADGE_CLASS"
    assert mapping[sev] in classes, f"{sev} -> {mapping[sev]} not defined in CSS"


def test_mapping_matches_spec(table_src):
    assert _badge_map(table_src) == {
        "critical": "severity-critical",
        "high": "severity-major",
        "medium": "severity-moderate",
        "low": "severity-minor",
    }


def test_unknown_severity_falls_back_to_defined_class(table_src, css):
    m = re.search(r"SEVERITY_BADGE_CLASS\[[^\]]*\]\s*\?\?\s*\"(severity-[a-z]+)\"", table_src)
    assert m, "no ?? fallback class for unknown severities"
    assert m.group(1) in _badge_classes(css)


def test_mapped_classes_are_distinct(table_src):
    vals = list(_badge_map(table_src).values())
    assert len(set(vals)) == len(vals), "high/medium/low must not share a badge class"


@pytest.mark.parametrize("sev", LIVE_SEVERITIES)
def test_badge_contrast_aa(sev, css, table_src):
    bg, fg = _badge_classes(css)[_badge_map(table_src)[sev]]
    assert bg and fg, f"{sev}: badge rule lacks background/color"
    ratio = _contrast(fg, bg)
    assert ratio >= 4.5, f"{sev}: {fg} on {bg} = {ratio:.2f}:1 < 4.5:1"


def test_labels_capitalized(table_src):
    for label in ("Critical", "High", "Medium", "Low"):
        assert f'"{label}"' in table_src, f"visible label {label} missing"
    assert "{severityLabel(h.severity)}" in table_src


def test_forced_colors_cover_mapped_classes(css, table_src):
    fc = css[css.find("@media (forced-colors: active)") :]
    assert fc, "forced-colors block missing"
    styles = {}
    for cls in set(_badge_map(table_src).values()):
        m = re.search(r"\." + cls + r"\s*\{([^}]*border-style:\s*(\w+)[^}]*)\}", fc)
        assert m, f"forced-colors rule missing for .{cls}"
        width = re.search(r"border-width:\s*(\w+)", m.group(1))
        color = re.search(r"border-color:\s*(\w+)", m.group(1))
        styles[cls] = (m.group(2), width and width.group(1), color and color.group(1))
    assert len(set(styles.values())) == len(styles), f"forced-colors styles not distinct: {styles}"


# ---------- (b) role=alert on fallbacks -------------------------------------


@pytest.mark.parametrize("fname", _FALLBACK_FILES)
def test_fallback_container_role_alert(fname):
    src = (_HAZ / fname).read_text(encoding="utf-8")
    m = re.search(r"fallbackRender=\{\(\{ resetErrorBoundary \}\) => \(\s*<div([^>]*)>", src)
    assert m, f"{fname}: fallbackRender container not found"
    assert 'role="alert"' in m.group(1), f"{fname}: fallback container lacks role=alert"
    assert not re.search(r"<button[^>]*role=\"alert\"", src), f"{fname}: role=alert on button"


# ---------- (c) branding -----------------------------------------------------


def test_no_lumen_in_touched_files():
    for p in [_CSS] + [_HAZ / f for f in _FALLBACK_FILES]:
        assert "lumen" not in p.read_text(encoding="utf-8").lower(), p.name
