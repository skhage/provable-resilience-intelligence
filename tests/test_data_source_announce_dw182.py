"""BUG-DW-182 (WCAG 4.1.3): the header data-source badge must not re-announce on route change.

The visible badge label is route-specific when live (Live Data / Lakebase State / ...), so a
role=status on it emits a polite announcement on every navigation, competing with the
BUG-DW-160 focus move. The fix moves role=status to a sibling sr-only region whose text
depends on the state only and is empty while loading.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(REPO, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
_LIB = os.path.join(UI, "lib", "data-source-badge.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

STATES = ["loading", "live", "mock", "unavailable"]
ROUTES = ["/", "/actions", "/hazards", "/topology", "/conduits", "/other"]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _root():
    return _strip_comments(_read(os.path.join(UI, "routes", "__root.tsx")))


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _open_tags(src, tag="span"):
    """Opening JSX tags (attributes only) for `tag`, brace-aware."""
    out = []
    for m in re.finditer(r"<" + tag + r"(?=[\s>/])", src):
        i, depth = m.end(), 0
        while i < len(src):
            c = src[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                break
            i += 1
        out.append((m.start(), src[m.end():i]))
    return out


# --- source: __root.tsx -------------------------------------------------------

def test_dw182_visible_badge_has_no_role():
    src = _root()
    badges = [(pos, a) for pos, a in _open_tags(src) if "dataSourceBadgeClass(" in a]
    assert len(badges) == 1, badges
    attrs = badges[0][1]
    assert "role=" not in attrs
    assert "aria-live" not in attrs
    assert attrs.strip() == "className={dataSourceBadgeClass(dataSource)}"


def test_dw182_single_status_region_is_sr_only_sibling():
    src = _root()
    status = [(pos, a) for pos, a in _open_tags(src) if 'role="status"' in a]
    assert len(status) == 1, status
    pos, attrs = status[0]
    assert 'className="sr-only"' in attrs
    # Its only child is the state-only announcement expression.
    body = src[pos:src.index("</span>", pos)]
    child = body[body.index(">") + 1:].strip()
    assert child == "{dataSourceAnnouncement(dataSource)}"
    # It follows the visible badge inside the same .ml-auto container.
    badge_pos = src.index("dataSourceBadgeClass(dataSource)")
    container = src.rindex('<div className="ml-auto">', 0, badge_pos)
    assert container < badge_pos < pos < src.index("</div>", pos)


def test_dw182_status_region_independent_of_pathname():
    src = _root()
    assert "dataSourceAnnouncement(dataSource)" in src
    assert not re.search(r"dataSourceAnnouncement\([^)]*pathname", src)
    assert "dataSourceAnnouncement" in src.split("from \"@/lib/data-source-badge\"")[0]


def test_dw182_visible_text_and_classes_unchanged():
    src = _root()
    assert "{dataSourceBadgeLabel(dataSource, pathname)}" in src
    assert '<span className="dot" aria-hidden="true" />' in src


def test_dw182_lib_signature_state_only():
    lib = _read(_LIB)
    m = re.search(r"export function dataSourceAnnouncement\(([^)]*)\)\s*:\s*string", lib)
    assert m, "dataSourceAnnouncement not exported"
    assert m.group(1).strip() == "state: DataSourceState"


def test_dw182_sr_only_class_exists():
    css = _strip_comments(_read(os.path.join(UI, "styles", "lakelink-theme.css")))
    m = re.search(r"(?m)^\.sr-only\s*\{([^}]*)\}", css)
    assert m
    assert "position: absolute" in m.group(1).replace("  ", " ")


# --- behaviour: pure helpers evaluated in Node --------------------------------

@needs_node
def test_dw182_loading_is_empty():
    assert _node("out = m.dataSourceAnnouncement('loading');") == ""


@needs_node
@pytest.mark.parametrize("state,expected", [
    ("live", "Data source: Live Data"),
    ("mock", "Data source: Mock Data"),
    ("unavailable", "Data source: unavailable"),
])
def test_dw182_settled_announcements(state, expected):
    assert _node(f"out = m.dataSourceAnnouncement({json.dumps(state)});") == expected


@needs_node
def test_dw182_navigation_does_not_change_announcement():
    """Simulate navigating every route in each state: the visible live label changes,
    the live-region text does not, so the region emits nothing on navigation."""
    out = _node(f"""out = {{}};
for (const s of {json.dumps(STATES)}) {{
  out[s] = {json.dumps(ROUTES)}.map((p) => [m.dataSourceBadgeLabel(s, p),
    m.dataSourceAnnouncement(s, p)]);
}}""")
    for state in STATES:
        announces = {a for _, a in out[state]}
        assert len(announces) == 1, (state, announces)
    assert len({label for label, _ in out["live"]}) == 5  # visible text still varies


@needs_node
def test_dw182_announcements_only_on_state_change():
    """Replay a session (loading -> live, then 5 navigations) and count text changes of
    the region, which is what triggers a polite announcement."""
    out = _node(f"""const steps = [['loading','/'], ['live','/'],
  ...{json.dumps(ROUTES[1:])}.map((p) => ['live', p])];
let prev = null; let changes = [];
for (const [s, p] of steps) {{
  const t = m.dataSourceAnnouncement(s);
  if (prev !== null && t !== prev && t !== '') changes.push(t);
  prev = t;
}}
out = changes;""")
    assert out == ["Data source: Live Data"]


@needs_node
def test_dw182_badge_labels_unchanged():
    out = _node(f"out = {json.dumps(ROUTES)}.map((p) => m.dataSourceBadgeLabel('live', p));")
    assert out == ["Live Data", "Lakebase State", "Live Crosswalk", "Live Topology",
                   "Live v4 Coverage", "Live Data"]
    out = _node("out = ['loading','mock','unavailable'].map((s) => m.dataSourceBadgeLabel(s, '/'));")
    assert out == ["Checking data source", "Mock Data", "Data source unavailable"]
