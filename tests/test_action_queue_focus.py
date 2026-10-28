"""BUG-DW-102: /actions focus retention (filter + Start/Complete) and result announcement.

Pure helpers in ui/lib/action-queue-focus.ts are evaluated with Node (TS type stripping).
JSX wiring in action-queue-table.tsx is checked statically (no npm on serverless).
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
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _src():
    with open(_TSX, encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- pure helpers -----------------------------------------------------------------

@needs_node
@pytest.mark.parametrize("total,page,size,exp", [
    (42, 1, 25, {"totalPages": 2, "page": 1, "first": 1, "last": 25}),
    (42, 2, 25, {"totalPages": 2, "page": 2, "first": 26, "last": 42}),
    (42, 9, 25, {"totalPages": 2, "page": 2, "first": 26, "last": 42}),  # clamp
    (0, 3, 25, {"totalPages": 1, "page": 1, "first": 0, "last": 0}),
    (5, 0, 10, {"totalPages": 1, "page": 1, "first": 1, "last": 5}),
])
def test_page_window(total, page, size, exp):
    assert _node(f"out = m.pageWindow({total}, {page}, {size});") == exp


@needs_node
@pytest.mark.parametrize("args,exp", [
    ((42, 1, 25, None), "42 actions \u00b7 showing 1\u201325"),
    ((42, 2, 25, None), "42 actions \u00b7 showing 26\u201342"),
    ((1, 1, 25, "pending"), "1 pending action \u00b7 showing 1\u20131"),
    ((12, 1, 10, "in_progress"), "12 in progress actions \u00b7 showing 1\u201310"),
    ((0, 1, 25, "completed"), "No completed actions"),
    ((0, 1, 25, None), "No actions"),
    ((1234, 1, 25, None), "1,234 actions \u00b7 showing 1\u201325"),
    ((3, 1, 25, "toString"), "3 actions \u00b7 showing 1\u20133"),  # prototype key must not leak
])
def test_result_message(args, exp):
    t, p, s, f = args
    assert _node(f"out = m.queueResultMessage({t}, {p}, {s}, {json.dumps(f)} ?? undefined);") == exp


@needs_node
def test_result_message_sentence_case():
    out = _node("out = [m.queueResultMessage(5,1,25,'cancelled'), m.queueResultMessage(0,1,25,'pending')];")
    for s in out:
        assert s[0].isupper() or s[0].isdigit()
        assert s[1:] == s[1:].lower()


@needs_node
def test_view_key():
    out = _node("out = [m.viewKey(undefined,1,25), m.viewKey('pending',1,25), m.viewKey('pending',2,25)];")
    assert out == ["all|1|25", "pending|1|25", "pending|2|25"]
    assert len(set(out)) == 3


@needs_node
@pytest.mark.parametrize("present,exp", [
    (["A", "B", "C"], "A"),        # (a) row still visible: Start -> Complete in place
    (["B", "C"], "B"),             # (b) row left the filtered view -> next row
    (["C"], "C"),                  # (b) next row has no button (completed) -> skip to the one after
    ([], None),                    # (c) nothing left -> caller focuses the table
    (["Z"], None),                 # rows BEFORE the clicked one are not used
])
def test_pick_focus_target(present, exp):
    out = _node(f"const s = new Set({json.dumps(present)});"
                " out = m.pickFocusTarget('A', ['B','C'], (id) => s.has(id));")
    assert out == exp


@needs_node
def test_ids_after():
    out = _node("out = [m.idsAfter(['Z','A','B','C'],'A'), m.idsAfter(['A'],'A'), m.idsAfter(['B'],'A')];")
    assert out == [["B", "C"], [], []]


# --- JSX wiring (static) ------------------------------------------------------------

def test_filter_and_paging_run_in_transition():
    s = _src()
    assert "useTransition" in s
    assert re.search(r"startFilterTransition\(\(\) => \{ setStatusFilter\(s\); setPage\(1\); \}\)", s)
    assert "onClick={() => changeFilter(s)}" in s
    assert "changePage((p) => Math.max(1, p - 1))" in s
    assert "changePage((p) => Math.min(totalPages, p + 1))" in s
    assert "changePageSize(Number(e.target.value))" in s
    # No direct (non-transition) filter/page setters left in handlers.
    assert "onClick={() => { setStatusFilter" not in s
    assert "onClick={() => setPage(" not in s


def test_table_busy_not_whole_region():
    s = _src()
    assert s.count("aria-busy={isFiltering || undefined}") == 2  # table + empty-state wrapper


def test_action_buttons_row_scoped_and_focusable():
    s = _src()
    assert "disabled={isPending}" not in s
    assert s.count("aria-disabled={isRowBusy(a.action_id) || undefined}") == 2
    assert s.count("ref={setActionButtonRef(a.action_id)}") == 2
    assert "mutatingVars?.actionId === actionId" in s
    assert "if (isRowBusy(actionId)) return;" in s


def test_focus_effect_and_fallback():
    s = _src()
    assert re.search(r"pickFocusTarget\(req\.actionId, req\.following,", s)
    assert "tableRegionRef.current?.focus()" in s
    assert s.count("ref={tableRegionRef} tabIndex={-1}") == 2
    assert "}, [actions]);" in s


def test_persistent_status_region():
    s = _src()
    m = re.search(r'<p className="sr-only" role="status" aria-live="polite" aria-atomic="true">\s*'
                  r'\{resultMessage\}\s*</p>', s)
    assert m, "persistent result-count status region missing"
    # Region is outside the empty/table conditional (rendered before it).
    assert m.start() < s.index("{actions.length === 0 ? (")
    # Initial message is empty (no announcement on first load).
    assert 'useState("")' in s
    assert "announcedKeyRef = useRef(viewKey(" in s


def test_kpi_cards_stay_in_same_boundary():
    # Cards and table share the outer Suspense; the transition keeps both mounted.
    s = _src()
    assert re.search(r"<ActionSummaryCards />\s*<ActionTableContent />", s)


def test_css_busy_and_focus_rules():
    with open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8") as f:
        css = f.read()
    assert '.btn[aria-disabled="true"]' in css
    assert '.data-table[tabindex="-1"]:focus-visible' in css


def test_no_old_brand_token():
    for p in (_TSX, _LIB):
        with open(p, encoding="utf-8") as f:
            assert "lumen" not in f.read().lower()
