"""BUG-DW-175: decorative U+2192 arrows in visible JSX text must not be spoken.

Every U+2192 that appears in JSX text in ui/**/*.tsx (comments excluded) must sit
inside an element with aria-hidden="true" or an element that carries an aria-label
(which replaces the computed name). Conduit endpoints must expose "to" to AT.

Negative check: these tests fail on e47f230.
"""
import os
import re
from pathlib import Path

import pytest

REPO = Path(os.environ.get("PRI_REPO", Path(__file__).resolve().parents[1]))
UI = REPO / "apps/resilience-scorecard/src/resilience_scorecard/ui"
TOPOLOGY = UI / "routes/topology.tsx"
ARROW = "\u2192"

TAG_RE = re.compile(
    r"<(/?)([A-Za-z][\w.]*)"
    r"((?:[^<>\"'{}]|\"[^\"]*\"|'[^']*'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})*?)"
    r"(/?)>",
    re.S,
)


def strip_comments(src: str) -> str:
    """Blank out comments (keep offsets) so arrows in comments are ignored."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    src = re.sub(r"\{/\*.*?\*/\}", blank, src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", blank, src, flags=re.S)
    src = re.sub(r"(?<![:\w\"'])//[^\n]*", blank, src)
    return src


def ancestors_at(src: str, pos: int):
    """Return the open-element stack (name, attrs) enclosing offset pos."""
    stack = []
    for m in TAG_RE.finditer(src, 0, pos):
        closing, name, attrs, selfclose = m.groups()
        if selfclose:
            continue
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        else:
            stack.append((name, attrs))
    return stack


NAME_FROM_LABEL_TAGS = {"a", "Link", "button", "Button"}


def is_silenced(stack) -> bool:
    """aria-hidden on any ancestor silences; aria-label only replaces the content name
    on link/button-like elements (a dialog/region aria-label does NOT hide its text)."""
    for name, attrs in stack:
        if re.search(r'aria-hidden=("true"|\{true\})', attrs):
            return True
        if "aria-label" in attrs and (
            name in NAME_FROM_LABEL_TAGS or re.search(r'role="(button|link)"', attrs)
        ):
            return True
    return False


def unsilenced_arrows():
    bad = []
    for f in sorted(UI.rglob("*.tsx")):
        if "node_modules" in f.parts:
            continue
        src = strip_comments(f.read_text(encoding="utf-8"))
        for m in re.finditer(ARROW, src):
            # Only JSX text: skip arrows inside JS string literals on the same line
            line_start = src.rfind("\n", 0, m.start()) + 1
            prefix = src[line_start:m.start()]
            if prefix.count('"') % 2 == 1 or prefix.count("`") % 2 == 1:
                continue
            if not is_silenced(ancestors_at(src, m.start())):
                line = src.count("\n", 0, m.start()) + 1
                bad.append(f"{f.relative_to(UI)}:{line}")
    return bad


def test_ui_dir_exists():
    assert TOPOLOGY.is_file()


def test_no_unsilenced_arrow_in_jsx_text():
    bad = unsilenced_arrows()
    assert bad == [], f"U+2192 spoken by screen readers at: {bad}"


def test_scanner_detects_unsilenced_arrow():
    sample = '<p className="x">\n  <a href="/">Next \u2192</a>\n</p>'
    pos = sample.index(ARROW)
    assert not is_silenced(ancestors_at(sample, pos))


def test_scanner_region_label_does_not_silence():
    s = '<div role="dialog" aria-label="Details">\n  <dd>A \u2192 B</dd>\n</div>'
    assert not is_silenced(ancestors_at(s, s.index(ARROW)))


def test_scanner_accepts_aria_hidden_and_label():
    hidden = '<p aria-hidden="true">Scroll \u2192</p>'
    labelled = '<Link to="/a" search={{ x: 1 }} aria-label={`Open ${id}`}>Open \u2192</Link>'
    for s in (hidden, labelled):
        assert is_silenced(ancestors_at(s, s.index(ARROW)))


def test_scanner_ignores_comments():
    s = strip_comments("// a \u2192 b\n{/* c \u2192 d */}\nconst u = 'https://x';")
    assert ARROW not in s
    assert "https://x" in s


def test_service_table_link_uses_lucide_arrow():
    src = TOPOLOGY.read_text(encoding="utf-8")
    assert "View in Service Table \u2192" not in src
    assert re.search(r"import \{[^}]*\bArrowRight\b[^}]*\} from \"lucide-react\"", src)
    m = re.search(r'className="path-trace-link"\s*>(.*?)</Link>', src, re.S)
    assert m, "path-trace-link not found"
    body = m.group(1)
    assert "View in Service Table" in body
    assert re.search(r'<ArrowRight[^>]*aria-hidden="true"[^>]*focusable="false"', body)
    assert 'size={14}' in body and 'strokeWidth={1.5}' in body


def test_region_drill_hint_arrow_hidden():
    src = TOPOLOGY.read_text(encoding="utf-8")
    assert "Click to explore \u2192\n" not in src
    assert 'Click to explore <tspan aria-hidden="true">\u2192</tspan>' in src


def test_endpoints_expose_to_for_at():
    src = TOPOLOGY.read_text(encoding="utf-8")
    assert "{detailConduit.site_a_id} \u2192 {detailConduit.site_z_id}" not in src
    m = re.search(r"<dt>Endpoints</dt>\s*<dd>(.*?)</dd>", src, re.S)
    assert m, "Endpoints <dd> not found"
    dd = strip_comments(m.group(1))
    assert '<span aria-hidden="true">\u2192</span>' in dd
    assert '<span className="sr-only">to</span>' in dd
    assert dd.index("site_a_id") < dd.index("sr-only") < dd.index("site_z_id")


@pytest.mark.parametrize("rel", [
    "routes/conduits.tsx",
    "components/dashboard/service-table.tsx",
    "components/actions/action-queue-table.tsx",
    "components/hazards/hazard-crosswalk-table.tsx",
    "components/hazards/hazard-summary-table.tsx",
])
def test_scroll_hints_remain_aria_hidden(rel):
    src = (UI / rel).read_text(encoding="utf-8")
    assert re.search(r'aria-hidden="true"[^>]*>\s*Scroll for more columns \u2192', src)


def test_open_action_link_keeps_aria_label():
    src = TOPOLOGY.read_text(encoding="utf-8")
    m = re.search(r'className="panel-action-link"\s*aria-label=\{`Open actions for SRLG \$\{s\.srlg_id\}`\}\s*>\s*Open action \u2192', src)
    assert m


def test_no_lumen_in_ui():
    hits = [str(f.relative_to(UI)) for f in UI.rglob("*.tsx")
            if "node_modules" not in f.parts and re.search(r"lumen", f.read_text(encoding="utf-8"), re.I)]
    assert hits == []
