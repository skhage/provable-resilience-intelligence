"""BUG-DW-184: service table + hazard summary pagination keep focus at the page boundary.

Source checks (no node_modules here): both tables must use the /actions BUG-DW-109
pattern - type="button", aria-disabled (never native disabled) plus an onClick guard
built on pageBoundary(), and decorative chevron glyphs inside aria-hidden spans.
"""
import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "apps/resilience-scorecard/src/resilience_scorecard/ui"
FILES = {
    "service": UI / "components/dashboard/service-table.tsx",
    "hazard": UI / "components/hazards/hazard-summary-table.tsx",
}
CSS = UI / "styles/lakelink-theme.css"
PREV = "\u2039"
NEXT = "\u203a"


def _src(key):
    return FILES[key].read_text(encoding="utf-8")


def _button(src, label):
    m = re.search(r'<button\b((?:(?!<button\b).)*?aria-label="' + label + r'"[^>]*)>(.*?)</button>', src, re.S)
    assert m, f"{label} button not found"
    return m.group(1), m.group(2)


@pytest.mark.parametrize("key", list(FILES))
def test_no_native_disabled(key):
    assert not re.search(r'(?<!aria-)disabled=\{', _src(key))


@pytest.mark.parametrize("key", list(FILES))
def test_imports_page_boundary(key):
    assert 'import { pageBoundary } from "@/lib/action-queue-focus";' in _src(key)


@pytest.mark.parametrize("key", list(FILES))
@pytest.mark.parametrize("label,flag", [("Previous page", "atFirst"), ("Next page", "atLast")])
def test_button_aria_disabled_and_guard(key, label, flag):
    attrs, _ = _button(_src(key), label)
    assert 'type="button"' in attrs
    assert re.search(r'aria-disabled=\{pageBoundary\([^)]*\)\.' + flag + r' \|\| undefined\}', attrs)
    assert re.search(r'onClick=\{\(\) => \{ if \(!pageBoundary\([^)]*\)\.' + flag + r'\) setPage', attrs)


@pytest.mark.parametrize("key", list(FILES))
def test_visible_copy_and_hidden_glyphs(key):
    s = _src(key)
    _, prev = _button(s, "Previous page")
    _, nxt = _button(s, "Next page")
    assert prev.strip() == f'<span aria-hidden="true">{PREV}</span> Previous'
    assert nxt.strip() == f'Next <span aria-hidden="true">{NEXT}</span>'
    assert f"{PREV} Prev\n" not in s and f"Next {NEXT}\n" not in s
    # every chevron glyph in the file sits inside an aria-hidden span
    for g in (PREV, NEXT):
        assert s.count(g) == s.count(f'<span aria-hidden="true">{g}</span>')


def test_css_keeps_disabled_visual_for_aria_disabled():
    css = CSS.read_text(encoding="utf-8")
    assert '.pagination-bar button[aria-disabled="true"]' in css
    assert ':not([aria-disabled="true"]):hover' in css


def test_page_boundary_semantics():
    src = (UI / "lib/action-queue-focus.ts").read_text(encoding="utf-8")
    assert "return { atFirst: page <= 1, atLast: page >= totalPages };" in src


@pytest.mark.parametrize("key", list(FILES))
def test_brand(key):
    assert "lum" + "en" not in _src(key).lower()
