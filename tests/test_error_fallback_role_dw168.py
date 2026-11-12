"""BUG-DW-168 regression tests: ErrorBoundary fallbacks announce failures (WCAG 4.1.3).

Acceptance (from @designer S122, P191):
  * Every `error-fallback` element in ui/ has role="alert" (or the conduits.tsx
    announce-guard `role={announce ? "alert" : undefined}`).
  * product-catalog.tsx and service-table.tsx fallbacks each carry role="alert",
    keep their message text, and keep Retry as a real <button> wired to
    resetErrorBoundary.
  * grep lumen = 0 in the touched components.
The TSX is parsed as text because serverless has no JSX transpiler.
These tests fail on HEAD 61e5f2c and pass after the fix.
"""
import pathlib
import re

import pytest

_UI = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui"
)
_DASH = _UI / "components/dashboard"

COMPONENTS = {
    "product-catalog.tsx": "Failed to load product catalog",
    "service-table.tsx": "Failed to load service scores",
}

_ALLOWED_ROLE = re.compile(
    r'role="alert"|role=\{announce \? "alert" : undefined\}'
)


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def _fallback_open_tag(src: str, message: str) -> str:
    i = src.find(message)
    assert i >= 0, f"fallback message {message!r} not found"
    j = src.rfind("<div", 0, i)
    assert j >= 0
    tag = src[j : src.find(">", j) + 1]
    assert "error-fallback" in tag, tag
    return tag


def _fallback_block(src: str, message: str) -> str:
    i = src.find(message)
    j = src.rfind("<div", 0, i)
    k = src.find("</div>", i)
    return src[j:k]


def test_every_error_fallback_in_ui_has_alert_role():
    missing = []
    for p in _UI.rglob("*.tsx"):
        for n, line in enumerate(_read(p).splitlines(), 1):
            if 'className="' in line and "error-fallback" in line and "<" in line:
                if not _ALLOWED_ROLE.search(line):
                    missing.append(f"{p.relative_to(_UI)}:{n}")
    assert missing == [], missing


@pytest.mark.parametrize("fname,message", COMPONENTS.items())
def test_fallback_has_role_alert(fname, message):
    tag = _fallback_open_tag(_read(_DASH / fname), message)
    assert 'role="alert"' in tag, tag


@pytest.mark.parametrize("fname,message", COMPONENTS.items())
def test_fallback_keeps_class_names(fname, message):
    tag = _fallback_open_tag(_read(_DASH / fname), message)
    assert 'className="data-table error-fallback"' in tag, tag


@pytest.mark.parametrize("fname,message", COMPONENTS.items())
def test_retry_is_real_button_wired_to_reset(fname, message):
    block = _fallback_block(_read(_DASH / fname), message)
    assert re.search(r"<button[^>]*onClick=\{resetErrorBoundary\}", block), block
    assert "Retry" in block
    assert 'role="button"' not in block


@pytest.mark.parametrize("fname", COMPONENTS)
def test_no_lumen_in_component(fname):
    assert "lumen" not in _read(_DASH / fname).lower()
