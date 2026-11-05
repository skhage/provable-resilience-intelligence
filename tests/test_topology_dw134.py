"""BUG-DW-134: conduit panel SRLG list state is announced (WCAG 4.1.3 Status Messages).

One persistent role=status container wraps the list-state area in EdgeDetailPanel.
It announces the loading copy, then the unavailable copy or a sr-only
'M shared risk groups loaded' that uses the true M (srlgTotal), never the 25 shown.
The rows are not live. Visible copy and the .panel-srlg-status style are unchanged.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
LIB = os.path.join(UI, "lib", "srlg-summary.ts")
TOPO = os.path.join(UI, "routes", "topology.tsx")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not available")


def _node(expr):
    script = f"import * as m from {json.dumps(LIB)}; console.log(JSON.stringify({expr}));"
    out = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _read(p):
    with open(p) as f:
        return f.read()


def _panel():
    """EdgeDetailPanel body, with JSX {/* */} comments stripped."""
    src = _read(TOPO)
    start = src.index("function EdgeDetailPanel(")
    end = src.index("\nfunction ", start + 10)
    return re.sub(r"\{/\*.*?\*/\}", "", src[start:end], flags=re.S)


def _live_block(panel):
    """The text of the panel-srlg-live container up to its matching </div>."""
    i = panel.index('className="panel-srlg-live"')
    open_at = panel.rindex("<div", 0, i)
    depth, j = 0, open_at
    for m in re.finditer(r"<div\b|</div>", panel[open_at:]):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            j = open_at + m.end()
            break
    assert depth == 0, "unbalanced div around panel-srlg-live"
    return panel[open_at:j], open_at


@needs_node
def test_loaded_spoken_uses_count_and_plural():
    assert _node("m.srlgListLoadedSpoken(134)") == "134 shared risk groups loaded"
    assert _node("m.srlgListLoadedSpoken(1)") == "1 shared risk group loaded"
    assert _node("m.srlgListLoadedSpoken(1340)") == "1,340 shared risk groups loaded"
    assert _node("m.srlgListLoadedSpoken(2.4)") == "2 shared risk groups loaded"


def test_single_persistent_status_container_in_panel():
    panel = _panel()
    assert panel.count('className="panel-srlg-live"') == 1
    block, at = _live_block(panel)
    opener = block[: block.index(">") + 1]
    assert 'role="status"' in opener and 'aria-live="polite"' in opener
    # Persistent: not gated on srlgListMode (only on the section itself), so it is in the
    # DOM before the fetch effect runs and before the state changes.
    before = panel[max(0, at - 80):at]
    assert "srlgListMode" not in before, before


def test_loading_and_unavailable_copy_inside_live_region():
    block, _ = _live_block(_panel())
    assert '<p className="panel-srlg-status">{SRLG_LIST_LOADING_MSG}</p>' in block
    assert "srlgUnavailableMsg(conduit.conduit_id, srlgListState)" in block
    assert block.count('className="panel-srlg-status"') == 2


def test_loaded_announcement_uses_true_m_not_rows_shown():
    block, _ = _live_block(_panel())
    assert '<span className="sr-only">{srlgListLoadedSpoken(srlgTotal)}</span>' in block
    for wrong in ("srlgRows.length", "srlgGroups.length", "PANEL_SRLG_INITIAL"):
        assert wrong not in block


def test_rows_and_cap_note_are_not_live():
    panel = _panel()
    block, at = _live_block(panel)
    assert "srlgRows.map" not in block and "{srlgListId}" not in block and "site-cap-note" not in block
    # rows container comes after the live region and carries no live semantics
    rows_at = panel.index("<div id={srlgListId}>")
    assert rows_at > at + len(block)
    # exactly one live region in the panel
    assert len(re.findall(r'role="status"', panel)) == 1
    assert "aria-live" not in panel[rows_at:]


def test_visible_style_unchanged_and_branding():
    css = _read(CSS)
    assert re.search(r"(?m)^\.panel-srlg-status \{[^}]*color: var\(--lf-iron\)", css)
    assert "panel-srlg-live" not in css  # no new visual styling
    for p in (TOPO, LIB):
        assert "lumen" not in _read(p).lower()
