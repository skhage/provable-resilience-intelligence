"""BUG-DW-109: /actions residuals after BUG-DW-102.

1) Pagination boundary keeps focus (aria-disabled + guard, never native disabled).
2) Filter pressed state + busy styling update immediately (requestedFilter, aria-busy CSS).
3) Grouped number formatting in the SR line and visible pagination text.
4) Concurrent row mutations: per-row in-flight set + per-row focus contexts; only the most
   recent user-initiated row moves focus.
Pure helpers are evaluated with Node (TS type stripping); JSX/CSS wiring is checked statically.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_LIB = os.path.join(UI, "lib", "action-queue-focus.ts")
_TSX = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
_CSS = os.path.join(UI, "styles", "lakelink-theme.css")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _pagination_block(s):
    i = s.index('aria-label="Action queue pagination"')
    return s[i:s.index("</nav>", i)]


# --- item 3: number formatting ------------------------------------------------------

@needs_node
def test_sr_line_acceptance_string():
    # 1,234 actions at 25/page -> last page 50 shows 1,226-1,234.
    assert _node("out = m.queueResultMessage(1234, 50, 25, undefined);") == \
        "1,234 actions \u00b7 showing 1,226\u20131,234"


@needs_node
@pytest.mark.parametrize("args,exp", [
    ((1234, 50, 25), "Showing 1,226\u20131,234 of 1,234"),
    ((42, 2, 25), "Showing 26\u201342 of 42"),
    ((42, 9, 25), "Showing 26\u201342 of 42"),            # clamped like pageWindow
    ((12000, 1, 100), "Showing 1\u2013100 of 12,000"),
])
def test_pagination_summary(args, exp):
    assert _node(f"out = m.paginationSummary({args[0]}, {args[1]}, {args[2]});") == exp


@needs_node
def test_format_range_and_count():
    out = _node("out = [m.formatRange(1001, 2000), m.fmtCount(1234567), m.fmtCount(-3)];")
    assert out == ["1,001\u20132,000", "1,234,567", "0"]


def test_visible_pagination_uses_formatter():
    blk = _pagination_block(_read(_TSX))
    assert "paginationSummary(actions.length, safeCurrentPage, pageSize)" in blk
    # Old unformatted arithmetic is gone.
    assert "(safeCurrentPage - 1) * pageSize + 1" not in blk
    assert "of {actions.length}" not in blk


# --- item 1: pagination boundary focus ----------------------------------------------

@needs_node
def test_page_boundary():
    out = _node("out = [m.pageBoundary(1,3), m.pageBoundary(2,3), m.pageBoundary(3,3), m.pageBoundary(1,1)];")
    assert out == [
        {"atFirst": True, "atLast": False},
        {"atFirst": False, "atLast": False},
        {"atFirst": False, "atLast": True},
        {"atFirst": True, "atLast": True},
    ]


def test_pagination_buttons_never_natively_disabled():
    blk = _pagination_block(_read(_TSX))
    assert not re.search(r"\bdisabled=\{", blk.replace("aria-disabled=", ""))
    assert "aria-disabled={atFirst || undefined}" in blk
    assert "aria-disabled={atLast || undefined}" in blk
    # onClick guards so an aria-disabled button is inert.
    assert "if (!atFirst) changePage(" in blk
    assert "if (!atLast) changePage(" in blk
    assert blk.count('type="button"') >= 2


def test_pagination_aria_disabled_css():
    css = _read(_CSS)
    assert re.search(r'\.pagination-bar button\[aria-disabled="true"\]\s*\{[^}]*opacity', css)
    assert ':not([aria-disabled="true"]):hover' in css
    assert re.search(r"\.pagination-bar button:focus-visible\s*\{[^}]*outline:", css)
    # forced-colors: dimmed state must not rely on opacity alone.
    fc = css[css.index(".pagination-bar button { border-color: ButtonText; }"):]
    assert 'button[aria-disabled="true"] { color: GrayText' in fc[:400]


# --- item 2: immediate filter feedback ----------------------------------------------

def test_requested_filter_drives_pressed_state():
    s = _read(_TSX)
    assert "aria-pressed={requestedFilter === s}" in s
    assert 'requestedFilter === s ? "btn-primary" : "btn-outline"' in s
    assert "aria-pressed={statusFilter === s}" not in s
    # Set urgently, BEFORE (outside) the transition.
    m = re.search(r"const changeFilter = \(s: string \| undefined\) => \{\s*"
                  r"setRequestedFilter\(s\);\s*startFilterTransition\(", s)
    assert m, "setRequestedFilter must run before startFilterTransition"
    # The committed filter still drives the query.
    assert "params: { status_filter: statusFilter }" in s


def test_busy_css_and_reduced_motion():
    css = _read(_CSS)
    m = re.search(r'\.data-table\[aria-busy="true"\]\s*\{([^}]*)\}', css)
    assert m and "opacity: 0.6" in m.group(1) and "cursor: progress" in m.group(1)
    # Any transition is gated on no-preference.
    for t in re.finditer(r"transition: opacity 120ms", css):
        head = css[:t.start()]
        assert head.rfind("@media (prefers-reduced-motion: no-preference)") > head.rfind("}\n}")


def test_scroll_region_focus_ring_still_applies():
    # Coordination note: populated wrapper is role=region tabIndex=0 (DW-103).
    css = _read(_CSS)
    assert ".data-table.table-scroll:focus-visible" in css


# --- item 4: concurrent mutations ---------------------------------------------------

@needs_node
def test_in_flight_set_is_per_row():
    out = _node(
        "let s = new Set();"
        "s = m.withInFlight(s, 'A'); s = m.withInFlight(s, 'B');"
        "const both = [s.has('A'), s.has('B')];"
        "const s2 = m.withoutInFlight(s, 'B');"
        "const same = m.withoutInFlight(s2, 'Z') === s2;"
        "out = {both, afterB: [s2.has('A'), s2.has('B')], same, origUntouched: s.has('B')};")
    assert out == {"both": [True, True], "afterB": [True, False], "same": True,
                   "origUntouched": True}


@needs_node
def test_two_rapid_clicks_focus_second_row():
    # Click A then B; A settles first, then B. Only B produces a focus request.
    out = _node(
        "const ctx = new Map([['A',{actionId:'A',following:['B','C']}],"
        "                     ['B',{actionId:'B',following:['C']}]]);"
        "let latest = 'B';"
        "const a = m.focusRequestFor('A', latest, ctx);"
        "const b = m.focusRequestFor('B', latest, ctx);"
        "out = {a, b};")
    assert out["a"] is None
    assert out["b"] == {"actionId": "B", "following": ["C"]}


@needs_node
def test_b_settles_before_a():
    out = _node(
        "const ctx = new Map([['A',{actionId:'A',following:[]}],['B',{actionId:'B',following:[]}]]);"
        "out = [m.focusRequestFor('B','B',ctx), m.focusRequestFor('A', null, ctx)];")
    assert out == [{"actionId": "B", "following": []}, None]


@needs_node
def test_single_click_keeps_dw102_behavior():
    out = _node("out = m.focusRequestFor('A','A', new Map());")
    assert out == {"actionId": "A", "following": []}


def test_mutation_wiring():
    s = _read(_TSX)
    # No latest-call-only busy tracking from useMutation.
    assert "const { mutate: updateStatus } = useUpdateActionStatus({" in s
    assert "mutatingVars" not in s
    assert "clickContextRef" not in s  # single shared context replaced
    assert "clickContextsRef.current.set(actionId," in s
    assert "latestClickRef.current = actionId;" in s
    assert "setInFlight((prev) => withInFlight(prev, actionId));" in s
    assert re.search(r"focusRequestFor\(variables\.actionId, latestClickRef\.current,", s)
    # Both success and error release the row.
    assert s.count("settle(variables.actionId);") == 2
    assert "const isRowBusy = (actionId: string) => inFlight.has(actionId);" in s


def test_no_old_brand_token():
    for p in (_TSX, _LIB):
        assert "lumen" not in _read(p).lower()
