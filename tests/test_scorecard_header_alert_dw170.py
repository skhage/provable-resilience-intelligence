"""BUG-DW-170 regression tests: ScorecardHeader ErrorBoundary fallback announces failure (WCAG 4.1.3).

Acceptance (from @designer S116):
  * scorecard-header.tsx fallbackRender outer container carries role="alert".
  * Message text, kpi-row/kpi-card classes and the real Retry <button> wired to
    resetErrorBoundary are unchanged.
  * Every fallbackRender in ui/ now has role="alert" on its first rendered element
    (ScorecardHeader was the last one without it).
  * grep lumen = 0 in the touched component.
The TSX is parsed as text because serverless has no JSX transpiler.
These tests fail on HEAD b5dba6b and pass after the fix.
"""
import pathlib
import re

_UI = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui"
)
_HEADER = _UI / "components/dashboard/scorecard-header.tsx"
_MESSAGE = "Failed to load summary"
_ALLOWED_ROLE = re.compile(r'role="alert"|role=\{announce \? "alert" : undefined\}')


def _src() -> str:
    return _HEADER.read_text(encoding="utf-8")


def _fallback_body(src: str, start: int) -> str:
    """Text of a fallbackRender arrow from its '=>' up to the first JSX tag close."""
    arrow = src.find("=>", start)
    lt = src.find("<", arrow)
    gt = src.find(">", lt)
    return src[lt : gt + 1]


def test_header_fallback_outer_has_role_alert():
    src = _src()
    i = src.find("fallbackRender")
    assert i >= 0
    tag = _fallback_body(src, i)
    assert 'className="kpi-row"' in tag, tag
    assert 'role="alert"' in tag, tag


def test_header_fallback_keeps_message_and_kpi_card():
    src = _src()
    i = src.find("fallbackRender")
    block = src[i : src.find("</ErrorBoundary>", i)]
    assert _MESSAGE in block
    assert 'className="kpi-card"' in block


def test_header_retry_is_real_button_wired_to_reset():
    src = _src()
    i = src.find(_MESSAGE)
    block = src[i : src.find("</div>", i)]
    assert re.search(r'<button[^>]*onClick=\{resetErrorBoundary\}', block), block
    assert "Retry" in block
    assert 'role="button"' not in block


def test_header_has_single_alert_not_nested():
    src = _src()
    i = src.find("fallbackRender")
    block = src[i : src.find("</ErrorBoundary>", i)]
    assert block.count('role="alert"') == 1


def test_every_fallback_render_in_ui_has_alert_role():
    missing = []
    for p in sorted(_UI.rglob("*.tsx")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"fallbackRender=\{", src):
            tag = _fallback_body(src, m.end())
            if not _ALLOWED_ROLE.search(tag):
                line = src.count("\n", 0, m.start()) + 1
                missing.append(f"{p.relative_to(_UI)}:{line} {tag}")
    assert missing == [], missing


def test_no_lumen_in_header():
    assert "lumen" not in _src().lower()
