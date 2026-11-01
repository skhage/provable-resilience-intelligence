"""BUG-DW-122: /actions PROVISIONAL page note must sit UNDER the h2.

.section-header is display:flex; justify-content:space-between (no wrap), so a
note that is a direct child of .section-header renders beside the h2 and is
squeezed at 320px (SC 1.4.10, V4-KPI-COPY-SPEC S7.4). The fix wraps the h2 and
the note in a plain <div>, the same structure hazards.tsx already uses. The
global .section-header rule must not change.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
ACTIONS = os.path.join(UI, "routes", "actions.tsx")
HAZARDS = os.path.join(UI, "routes", "hazards.tsx")
THEME = os.path.join(UI, "styles", "lakelink-theme.css")

_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9.]*)((?:[^<>{}]|\{[^{}]*\})*?)(/?)>")


def _tree(src):
    """Return a list of nodes {tag, attrs, parent, children} from JSX source.

    JSX comments are stripped first. Raises if the tag tree is unbalanced.
    """
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    root = {"tag": "#root", "attrs": "", "parent": None, "children": []}
    stack = [root]
    nodes = []
    for m in _TAG.finditer(src):
        closing, tag, attrs, selfclose = m.groups()
        if closing:
            if stack[-1]["tag"] != tag:
                raise AssertionError(f"unbalanced </{tag}> vs <{stack[-1]['tag']}>")
            stack.pop()
            continue
        node = {"tag": tag, "attrs": attrs, "parent": stack[-1], "children": []}
        stack[-1]["children"].append(node)
        nodes.append(node)
        if not selfclose:
            stack.append(node)
    return nodes


def _section_body(path, fn):
    src = open(path, encoding="utf-8").read()
    start = src.index(f"function {fn}")
    ret = src.index("return (", start)
    return src[ret:]


def _note(nodes):
    hits = [n for n in nodes if n["tag"] == "p" and "provisional-page-note" in n["attrs"]]
    assert len(hits) == 1, f"expected 1 provisional-page-note, got {len(hits)}"
    return hits[0]


def _assert_note_under_heading(path, fn):
    nodes = _tree(_section_body(path, fn))
    note = _note(nodes)
    wrapper = note["parent"]
    assert wrapper["tag"] == "div", f"note parent is <{wrapper['tag']}>"
    assert "section-header" not in wrapper["attrs"], "note is a direct .section-header child"
    assert "className" not in wrapper["attrs"], "wrapper should be a plain <div>"
    assert any(c["tag"] == "h2" for c in wrapper["children"]), "wrapper must also contain the h2"
    h2_idx = next(i for i, c in enumerate(wrapper["children"]) if c["tag"] == "h2")
    note_idx = wrapper["children"].index(note)
    assert h2_idx < note_idx, "note must follow the h2"
    header = wrapper["parent"]
    assert header["tag"] == "div" and "section-header" in header["attrs"], \
        "wrapper must sit inside .section-header"


def test_actions_note_inside_plain_div_with_h2():
    _assert_note_under_heading(ACTIONS, "ActionsPage")


def test_hazards_reference_structure_unchanged():
    _assert_note_under_heading(HAZARDS, "HazardExposurePage")


def test_actions_note_copy_and_role_unchanged():
    src = open(ACTIONS, encoding="utf-8").read()
    assert '<p role="note" className="provisional-page-note">' in src
    # BUG-DW-123: copy now comes from constants (byte-identity is checked in test_provisional_dw123.py).
    assert "<strong>{PROVISIONAL_NOTE_LEAD}</strong>{PROVISIONAL_NOTE_BODY}" in src
    assert "showNote && (" in src


def test_section_header_rule_not_changed_globally():
    css = open(THEME, encoding="utf-8").read()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?m)^\.section-header\s*\{([^}]*)\}", css)
    assert m, ".section-header base rule missing"
    body = m.group(1)
    assert "display: flex" in body or "display:flex" in body
    assert "space-between" in body
    assert "flex-wrap" not in body, "do not change .section-header globally (BUG-DW-122)"


def test_tree_scanner_known_answer():
    bad = 'function X() { return (<div className="section-header"><h2>T</h2>' \
          '<p role="note" className="provisional-page-note">n</p></div>); }'
    nodes = _tree(bad[bad.index("return ("):])
    note = _note(nodes)
    assert "section-header" in note["parent"]["attrs"]


def test_no_lumen_in_actions():
    assert "lumen" not in open(ACTIONS, encoding="utf-8").read().lower()
