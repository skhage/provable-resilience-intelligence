"""BUG-DW-167 regression tests: /actions hazard severity badge reuses SEVERITY_BADGE_CLASS.

Acceptance (from @designer S118, P173):
  * No raw `severity-${` interpolation anywhere in ui/ (grep = 0).
  * The /actions badge resolves to a CSS-defined class for all 4 values
    (critical/high/medium/low), and null renders an em dash with no badge.
  * The visible label is capitalized (severityLabel).
  * The map is not duplicated. It is defined once and imported via the hazards barrel.
  * grep lumen = 0.
The TSX is parsed as text because serverless has no JSX transpiler.
These tests fail on HEAD 9186cb9 (and 30ceb9e) and pass after the fix.
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
_BARREL = _HAZ / "index.ts"
_ACTIONS = _UI / "components/actions/action-queue-table.tsx"
LIVE_SEVERITIES = ["critical", "high", "medium", "low"]


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def actions_src() -> str:
    return _read(_ACTIONS)


def _severity_block(src: str) -> str:
    i = src.find('<div className="detail-label">Severity</div>')
    assert i >= 0, "Severity detail block not found in action-queue-table.tsx"
    j = src.find('<div className="detail-label">', i + 10)
    return src[i : j if j > 0 else i + 1200]


def _badge_map() -> dict:
    m = re.search(r"SEVERITY_BADGE_CLASS[^=]*=\s*\{([^}]*)\}", _read(_TABLE))
    assert m
    return dict(re.findall(r"(\w+)\s*:\s*\"(severity-[a-z]+)\"", m.group(1)))


def test_no_raw_severity_interpolation_in_ui():
    hits = [
        f"{p.relative_to(_UI)}:{n}"
        for p in _UI.rglob("*")
        if p.suffix in {".ts", ".tsx", ".css"} and p.is_file()
        for n, line in enumerate(_read(p).splitlines(), 1)
        if "severity-${" in line
    ]
    assert hits == [], hits


def test_helpers_exported_from_summary_table():
    src = _read(_TABLE)
    assert re.search(r"export function severityBadgeClass\(", src)
    assert re.search(r"export function severityLabel\(", src)


def test_helpers_null_safe_signature():
    src = _read(_TABLE)
    for fn in ("severityBadgeClass", "severityLabel"):
        assert re.search(fn + r"\(severity: string \| null \| undefined\)", src), fn
    assert "(severity ?? \"\").toLowerCase()" in src


def test_barrel_reexports_helpers():
    b = _read(_BARREL)
    for name in ("SEVERITY_BADGE_CLASS", "severityBadgeClass", "severityLabel"):
        assert re.search(r"\b" + name + r"\b", b), name


def test_actions_imports_from_hazards_barrel(actions_src):
    m = re.search(r"import\s*\{([^}]*)\}\s*from\s*\"@/components/hazards\"", actions_src)
    assert m
    names = {s.strip() for s in m.group(1).split(",")}
    assert {"severityBadgeClass", "severityLabel"} <= names


def test_map_not_duplicated():
    hits = [p.name for p in _UI.rglob("*.ts*") if re.search(r"SEVERITY_BADGE_CLASS[^=\n]*=\s*\{", _read(p))]
    assert hits == ["hazard-summary-table.tsx"], hits
    assert "severity-major" not in _read(_ACTIONS)


def test_actions_badge_uses_helpers(actions_src):
    blk = _severity_block(actions_src)
    assert "className={`badge ${severityBadgeClass(a.hazard_severity)}`}" in blk
    assert "{severityLabel(a.hazard_severity)}" in blk
    assert "data-severity={a.hazard_severity}" in blk


def test_actions_null_renders_em_dash_without_badge(actions_src):
    blk = _severity_block(actions_src)
    m = re.search(r"\{a\.hazard_severity\s*\?\s*\((.*?)\)\s*:\s*\(\s*\"\u2014\"\s*\)\s*\}", blk, re.S)
    assert m, "null branch must render an em dash"
    assert "badge" in m.group(1)
    after_colon = blk[blk.find(":", m.start(1) + len(m.group(1))):]
    assert "badge" not in after_colon.split("}")[0]


@pytest.mark.parametrize("sev", LIVE_SEVERITIES)
def test_every_value_resolves_to_css_class(sev):
    css = _read(_CSS)
    cls = _badge_map()[sev]
    assert re.search(r"\.badge\." + cls + r"\s*\{", css), cls
    assert re.search(r"\." + cls + r"\s*\{[^}]*border", css), f"forced-colors rule missing for {cls}"


def test_no_lumen():
    for p in (_ACTIONS, _TABLE, _BARREL):
        assert "lumen" not in _read(p).lower(), p.name
