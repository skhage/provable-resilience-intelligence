"""BUG-DW-195: mobile topology tree Enter/Space must activate the treeitem (WCAG 2.1.1).

handleTreeKeyDown used to call target.click() on the <li role="treeitem">, but the
onClick handlers sit on the direct child <div class="mobile-tree-row">. Click events
do not propagate downward, so Enter/Space did nothing and conduit detail was
unreachable by keyboard. The fix dispatches to
target.querySelector(':scope > .mobile-tree-row') and keeps onClick off the <li>.

Negative check: these tests fail on f70f90e.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(os.environ.get("PRI_REPO", Path(__file__).resolve().parents[1]))
TOPOLOGY = REPO / "apps/resilience-scorecard/src/resilience_scorecard/ui/routes/topology.tsx"
ROW_SELECTOR = ":scope > .mobile-tree-row"


def src() -> str:
    return TOPOLOGY.read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?<![:\w\"'])//[^\n]*", "", text)


def handler_body() -> str:
    s = strip_comments(src())
    start = s.index("const handleTreeKeyDown = useCallback(")
    end = s.index("[expandedRegions, expandedSites, toggleRegion, toggleSite]", start)
    return s[start:end]


def enter_branch(body: str) -> str:
    """Statements of the Enter/Space case, up to and including its break."""
    m = re.search(r'case "Enter":\s*case " ":\s*\{?(.*?)\bbreak;', body, re.S)
    assert m, "Enter/Space case not found in handleTreeKeyDown"
    return m.group(1)


def to_js(ts: str) -> str:
    return re.sub(r"\)\s*as\s+HTMLElement\s*\|\s*null", ")", ts)


# ---------- static checks ----------

def test_enter_branch_does_not_click_treeitem_itself():
    branch = enter_branch(handler_body())
    assert "target.click()" not in branch


def test_enter_branch_targets_direct_child_row():
    branch = enter_branch(handler_body())
    assert re.search(r'target\.querySelector\(\s*":scope > \.mobile-tree-row"\s*\)', branch), branch
    assert re.search(r"\?\.click\(\)", branch)


def test_enter_branch_keeps_prevent_default():
    assert "e.preventDefault()" in enter_branch(handler_body())


def test_treeitem_li_has_no_onclick():
    s = strip_comments(src())
    for m in re.finditer(r'<li\b(?:[^<>{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*?role="treeitem"(?:[^<>{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*?>', s, re.S):
        assert "onClick" not in m.group(0), m.group(0)[:200]


@pytest.mark.parametrize("level", ["region", "site", "conduit"])
def test_each_treeitem_first_child_is_clickable_row(level):
    s = strip_comments(src())
    li = s.index(f'className="mobile-tree-{level}"')
    after = s[li:]
    close = after.index(">")
    nxt = after[close + 1:].lstrip()
    assert nxt.startswith("<div"), nxt[:80]
    div = nxt[: nxt.index(">") + 1] if "onClick" not in nxt[: nxt.index(">")] else nxt[:400]
    assert f'className="mobile-tree-row mobile-tree-row--{level}"' in nxt[:200]
    assert "onClick=" in nxt[:300], div


def test_no_banned_brand_string():
    banned = "lu" + "men"
    assert banned not in src().lower()
    assert banned not in Path(__file__).read_text(encoding="utf-8").lower()


# ---------- behavioural check (Node fake DOM) ----------

NODE = shutil.which("node") or ("/usr/local/bin/node" if Path("/usr/local/bin/node").exists() else None)

HARNESS = r"""
const body = %s;
const calls = [];
const row = { click: () => calls.push('row') };
const nested = { click: () => calls.push('nested') };
const target = {
  click: () => calls.push('li'),
  querySelector: (sel) => { calls.push('qs:' + sel); return sel === ':scope > .mobile-tree-row' ? row : nested; },
};
let prevented = false;
const e = { preventDefault: () => { prevented = true; } };
new Function('e', 'target', body)(e, target);
console.log(JSON.stringify({ calls, prevented }));
"""


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_enter_dispatches_click_to_row_not_li():
    js = to_js(enter_branch(handler_body()))
    out = subprocess.run([NODE, "-e", HARNESS % json.dumps(js)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["prevented"] is True
    assert "li" not in res["calls"], res
    assert "nested" not in res["calls"], res
    assert res["calls"] == [f"qs:{ROW_SELECTOR}", "row"], res


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_enter_is_safe_when_row_missing():
    js = to_js(enter_branch(handler_body()))
    harness = HARNESS.replace("? row : nested", "? null : null")
    out = subprocess.run([NODE, "-e", harness % json.dumps(js)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["calls"] == [f"qs:{ROW_SELECTOR}"], res
