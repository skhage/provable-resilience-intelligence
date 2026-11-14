"""BUG-DW-177: an <svg role="img"> must not contain interactive descendants.

ARIA 1.2 role=img has presentational children, so focusable role=button nodes inside it
can be pruned from the accessibility tree (WCAG 4.1.2). The two /topology canvases
(RegionGraph and the site graph) now use role="group" with the same aria-label text.

Negative check: these tests fail on a8b522c.
"""
import os
import re
from pathlib import Path

REPO = Path(os.environ.get("PRI_REPO", Path(__file__).resolve().parents[1]))
UI = REPO / "apps/resilience-scorecard/src/resilience_scorecard/ui"
TOPOLOGY = UI / "routes/topology.tsx"

REGION_LABEL = (
    "aria-label={`Network topology overview: ${formatCount(totalSites)} sites, "
    "${formatCount(totalConduits)} conduits across ${sorted.length} regions`"
)
SITE_LABEL = "aria-label={siteGraphAriaLabel(regionName, siteCap, totalSites, drawnConduits, conduits.length)}"

# Opening/closing tags; attribute values may hold nested {...} (3 levels) and quoted strings.
TAG_RE = re.compile(
    r"<(/?)([A-Za-z][\w.]*)"
    r"((?:[^<>\"'{}]|\"[^\"]*\"|'[^']*'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})*?)"
    r"(/?)>",
    re.S,
)
INTERACTIVE_RE = re.compile(r'tabIndex=\{0\}|tabIndex="0"|role="button"|role="link"|\bonClick=')


def strip_comments(src: str) -> str:
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    src = re.sub(r"\{/\*.*?\*/\}", blank, src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", blank, src, flags=re.S)
    src = re.sub(r"(?<![:\w\"'])//[^\n]*", blank, src)
    return src


def img_svgs_with_interactive_children(src: str):
    """Return (line, attrs) for every <svg role=img> whose subtree has an interactive element."""
    src = strip_comments(src)
    bad = []
    stack = []  # entries: [attrs, is_img, start_pos, has_interactive]
    for m in TAG_RE.finditer(src):
        closing, name, attrs, selfclose = m.groups()
        if not closing and INTERACTIVE_RE.search(attrs or ""):
            for entry in stack:
                if entry[1]:
                    entry[3] = True
        if name != "svg" or selfclose:
            continue
        if closing:
            if stack:
                attrs0, is_img, start, hit = stack.pop()
                if is_img and hit:
                    bad.append((src.count("\n", 0, start) + 1, attrs0.strip()[:80]))
        else:
            stack.append([attrs, 'role="img"' in attrs, m.start(), False])
    return bad


def _topology():
    return TOPOLOGY.read_text(encoding="utf-8")


def _svg_open_tag_containing(src: str, needle: str) -> str:
    i = src.index(needle)
    start = src.rfind("<svg", 0, i)
    end = src.index(">\n", i)
    return src[start:end]


# --- scanner self-tests -------------------------------------------------------------

def test_scanner_flags_known_bad_snippet():
    bad = (
        '<svg role="img" aria-label="map">\n'
        '  <g tabIndex={0} role="button" aria-label={`x ${a}`} onClick={() => go("a")}>\n'
        '    <text>x</text>\n'
        '  </g>\n'
        '</svg>\n'
    )
    assert len(img_svgs_with_interactive_children(bad)) == 1


def test_scanner_ignores_group_and_leaf_img():
    ok = (
        '<svg role="group" aria-label="map">\n'
        '  <g role="img" tabIndex={0} aria-label="hazard"><circle /></g>\n'
        '  <g role="button" tabIndex={0} aria-label="node"><svg width="4" aria-hidden="true"><path /></svg></g>\n'
        '</svg>\n'
        '<svg role="img" aria-label="static"><line /><title>t</title></svg>\n'
    )
    assert img_svgs_with_interactive_children(ok) == []


def test_scanner_ignores_comments():
    src = '<svg role="img" aria-label="m">{/* <g tabIndex={0} role="button"> */}<line /></svg>'
    assert img_svgs_with_interactive_children(src) == []


# --- repo-wide rule -------------------------------------------------------------------

def test_no_img_svg_has_interactive_descendants_repo_wide():
    offenders = []
    for f in sorted(UI.rglob("*.tsx")):
        if "node_modules" in f.parts:
            continue
        for line, attrs in img_svgs_with_interactive_children(f.read_text(encoding="utf-8")):
            offenders.append(f"{f.relative_to(UI)}:{line} {attrs}")
    assert offenders == [], "svg role=img with focusable/clickable children: " + "; ".join(offenders)


# --- topology canvases ----------------------------------------------------------------

def test_region_graph_svg_is_group_with_verbatim_label():
    src = _topology()
    assert src.count(REGION_LABEL) == 1
    tag = _svg_open_tag_containing(src, REGION_LABEL)
    assert 'role="group"' in tag and 'role="img"' not in tag


def test_site_graph_svg_is_group_with_verbatim_label():
    src = _topology()
    assert src.count(SITE_LABEL) == 1
    tag = _svg_open_tag_containing(src, SITE_LABEL)
    assert 'role="group"' in tag and 'role="img"' not in tag


def test_interactive_children_unchanged():
    src = _topology()
    # region nodes, conduit edges and site nodes remain focusable named buttons
    assert "Press Enter to drill in.`}" in src
    assert "aria-label={conduitEdgeName(" in src
    assert "Press Enter for details.`}" in src
    assert src.count('role="button"') >= 3
    # hazard marker stays a focusable leaf role=img inside the group
    marker = src[src.index('className="hazard-overlay-marker"'):]
    marker = marker[: marker.index(">")]
    assert 'role="img"' in marker and "tabIndex={0}" in marker


def _text_open_tag_before(src: str, content_needle: str) -> str:
    i = src.index(content_needle)
    start = src.rfind("<text", 0, i)
    # the <text ...> opening tag (attributes span lines up to the content)
    return src[start:i]


def test_duplicate_visible_labels_are_aria_hidden():
    src = _topology()
    region_name = _text_open_tag_before(src, "{r.region}\n            </text>")
    hint = _text_open_tag_before(src, "Click to explore")
    site_abbr = _text_open_tag_before(src, '{s.site_type === "data_center" ? "DC" : "CO"}')
    for label, tag in (("region name", region_name), ("drill-in hint", hint), ("site DC/CO", site_abbr)):
        assert 'aria-hidden="true"' in tag, f"{label} <text> duplicates the button name; must be aria-hidden"


def test_no_competitor_brand_in_topology():
    banned = "lu" + "men"  # split so this test file itself stays grep-clean
    assert banned not in _topology().lower()
