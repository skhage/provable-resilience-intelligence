"""BUG-DW-115: /topology hazard marker must not have a child <title> (SVG-AAM description fallback).

A focusable SVG element whose direct child is <title> gets that title as its accessible
description, so the hazard summary was announced twice (aria-label + description). The fix
mirrors BUG-DW-100: <g role="none"><title/><g role=img tabIndex=0 aria-label=...>...</g></g>.

The structural test generalises DW-100: no element carrying tabIndex, in topology.tsx or any
ui/**/*.tsx, may have a direct child <title>. A small JSX tag scanner builds the element tree.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import glob
import os
import re

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
TOPOLOGY = os.path.join(UI, "routes", "topology.tsx")

# Character-for-character copy of the hazard aria-label template before the fix (acceptance b).
HAZARD_ARIA_LABEL = (
    'aria-label={`${h.hazard_type.replace(/_/g, " ")} hazard: ${h.name}, severity ${h.severity}, '
    '${h.direct_impact_spans} direct impact spans, ${h.near_impact_spans} near impact spans`}'
)
HAZARD_TITLE_TEXT = (
    '{h.hazard_type.replace(/_/g, " ")} hazard: {h.name} ({h.severity}) \u2014 '
    '{h.direct_impact_spans} direct, {h.near_impact_spans} near impact spans'
)

_IDENT = re.compile(r"[A-Za-z0-9_$.)\]]")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    """Blank /* */ blocks (keeping newlines) and whole-line // comments."""
    src = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return "\n".join("" if ln.lstrip().startswith("//") else ln for ln in src.split("\n"))


def _skip_braces(s, i):
    """s[i] == '{'. Return the index after the matching '}' (skips strings and template literals)."""
    depth, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = i + 1
            while j < n and s[j] != c:
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if c == "`":
            j = i + 1
            while j < n and s[j] != "`":
                if s[j] == "\\":
                    j += 2
                    continue
                if s.startswith("${", j):
                    j = _skip_braces(s, j + 1)
                    continue
                j += 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces")


def jsx_tags(src):
    """Yield (event, name, attrs, line) for JSX tags; event is open | close | self.

    A '<' preceded by an identifier char (generics such as useState<T>, a<b) is not a tag.
    """
    s = _strip_comments(src)
    i, n = 0, len(s)
    while i < n:
        if s[i] != "<":
            i += 1
            continue
        prev = s[i - 1] if i else " "
        m = re.match(r"</([A-Za-z][\w.]*)\s*>", s[i:])
        if m:
            yield ("close", m.group(1), "", s.count("\n", 0, i) + 1)
            i += m.end()
            continue
        m = re.match(r"<([A-Za-z][\w.]*)", s[i:])
        if not m or _IDENT.match(prev):
            i += 1
            continue
        j = start = i + m.end()
        while j < n and s[j] != ">":
            if s[j] == "{":
                j = _skip_braces(s, j)
            elif s[j] in "\"'":
                j = s.index(s[j], j + 1) + 1
            else:
                j += 1
        attrs = s[start:j]
        ev = "self" if attrs.rstrip().endswith("/") else "open"
        yield (ev, m.group(1), attrs, s.count("\n", 0, i) + 1)
        i = j + 1


def focusable_with_child_title(src):
    """[(parent_tag, parent_line, title_line)] for every tabIndex element with a direct <title> child.

    Raises ValueError if the tag tree does not balance, so a scanner miss cannot pass silently.
    """
    stack, bad = [], []
    for ev, name, attrs, line in jsx_tags(src):
        if ev == "open":
            if name == "title" and stack and re.search(r"\btabIndex\s*=", stack[-1][1]):
                bad.append((stack[-1][0], stack[-1][2], line))
            stack.append((name, attrs, line))
        elif ev == "close":
            if not stack or stack[-1][0] != name:
                raise ValueError(f"mismatched </{name}> at line {line}")
            stack.pop()
    if stack:
        raise ValueError(f"unclosed tags: {[(t, ln) for t, _, ln in stack]}")
    return bad


# --- scanner known-answer cases -------------------------------------------------------------

@pytest.mark.parametrize("src,expected", [
    ('<g tabIndex={0} aria-label="x"><title>t</title><circle/></g>', 1),
    ('<line tabIndex={0}><title>t</title></line>', 1),
    ('<g role="none"><title>t</title><g tabIndex={0}><circle r={a > b ? 1 : 2}/></g></g>', 0),
    ('const x = useState<string>(""); return (<line tabIndex={0} onKeyDown={(e) => '
     '{ if (a<b) {} }}><title>q</title></line>);', 1),
    ('<g tabIndex={0}><g><title>nested, not direct</title></g></g>', 0),
    ('<g aria-label={`${a} > ${b}`} tabIndex={-1}><title>t</title></g>', 1),
])
def test_scanner_known_answers(src, expected):
    assert len(focusable_with_child_title(src)) == expected


def test_scanner_rejects_unbalanced_tree():
    with pytest.raises(ValueError):
        focusable_with_child_title("<g><title>t</title>")


# --- acceptance (a): structural --------------------------------------------------------------

def test_topology_no_focusable_element_has_child_title():
    assert focusable_with_child_title(_read(TOPOLOGY)) == []


def test_all_ui_tsx_no_focusable_element_has_child_title():
    files = glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True)
    assert len(files) > 5
    offenders = {}
    for p in files:
        bad = focusable_with_child_title(_read(p))
        if bad:
            offenders[os.path.relpath(p, UI)] = bad
    assert offenders == {}


# --- acceptance (b)/(c): label unchanged, tooltip kept via ancestor --------------------------

def _hazard_block():
    t = _read(TOPOLOGY)
    start = t.index("overlays.hazard && hazards.map(")
    end = t.index("BUG-DW-056: sr-only hazard summary", start)
    return t[start:end]


def test_hazard_aria_label_unchanged():
    block = _hazard_block()
    assert block.count(HAZARD_ARIA_LABEL) == 1


def test_hazard_tooltip_on_role_none_ancestor():
    block = _hazard_block()
    m = re.search(
        r'<g key=\{h\.hazard_id\} role="none">\s*<title>\s*(.*?)\s*</title>\s*<g\s+className="hazard-overlay-marker"',
        block, flags=re.S)
    assert m, "hover <title> must be the first child of the role=none wrapper, before the marker"
    assert m.group(1) == HAZARD_TITLE_TEXT
    # key moved to the wrapper; the inner marker keeps role=img + tabIndex=0 (focus-visible CSS)
    marker = block[block.index('className="hazard-overlay-marker"'):]
    marker = marker[:marker.index(">")]
    assert 'role="img"' in marker and "tabIndex={0}" in marker and "key=" not in marker


def test_hazard_focus_visible_css_targets_marker_class():
    css = _read(os.path.join(UI, "styles", "lakelink-theme.css"))
    assert re.search(r"(?m)^\.hazard-overlay-marker:focus-visible\s*\{", css)
    assert "> .hazard-overlay-marker" not in css


def test_tabindex_rationale_documented():
    assert "Removal requires a designer decision" in _hazard_block()


# --- acceptance (d) --------------------------------------------------------------------------

def test_no_legacy_brand_token():
    """CEO branding mandate: the legacy brand token never appears in the route source."""
    assert "lumen" not in _read(TOPOLOGY).lower()
