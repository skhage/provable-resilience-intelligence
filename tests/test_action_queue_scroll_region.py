"""BUG-DW-103: /actions table scroll region (2.1.1), pagination reflow (1.4.10), border contrast (1.4.11).

Static source checks (no npm on serverless). Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import os
import re

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_TSX = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
_CSS = os.path.join(UI, "styles", "lakelink-theme.css")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _region_open_tag(s):
    m = re.search(r'<div\s+className="data-table table-scroll"(.*?)>', s, re.S)
    assert m, "populated action table is not a .table-scroll region"
    return m


def test_region_is_named_focusable_scroll_region():
    attrs = _region_open_tag(_read(_TSX)).group(1)
    assert 'role="region"' in attrs
    assert 'aria-label="Action queue table, scrolls horizontally"' in attrs
    assert "tabIndex={0}" in attrs
    # Remains the BUG-DW-102 programmatic focus fallback.
    assert "ref={tableRegionRef}" in attrs
    assert "aria-busy={isFiltering || undefined}" in attrs


def test_scroll_hint_precedes_region():
    s = _read(_TSX)
    hint = s.index('<p className="text-caption table-scroll-hint" aria-hidden="true">')
    assert hint < _region_open_tag(s).start()
    assert "Scroll for more columns" in s


def test_pagination_outside_scroll_region():
    s = _read(_TSX)
    region = _region_open_tag(s)
    table_close = s.index("</table>", region.end())
    nav = s.index('<nav className="pagination-bar pagination-bar-detached"')
    # The region's closing </div> comes right after </table>, before the nav.
    between = s[table_close:nav]
    assert re.match(r"</table>\s*</div>", between), "nav is still inside the scroll wrapper"
    assert s.count('<nav className="pagination-bar') == 1


def _rule(css, selector):
    # Base (top-level) rule: selector at line start, so media-query overrides are skipped.
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_pagination_borders_iron():
    css = _read(_CSS)
    assert "border: 1px solid var(--lf-iron)" in _rule(css, ".pagination-bar select")
    assert "border: 1px solid var(--lf-iron)" in _rule(css, ".pagination-bar button")
    assert "--lf-platinum" not in _rule(css, ".pagination-bar select")


def test_pagination_wraps_on_mobile():
    css = _read(_CSS)
    blocks = re.findall(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S)
    joined = "\n".join(blocks)
    m = re.search(r"\.pagination-bar \{([^}]*)\}", joined)
    assert m and "flex-wrap: wrap" in m.group(1) and "row-gap: var(--space-sm)" in m.group(1)
    assert re.search(r"\.pagination-bar \.page-controls \{[^}]*flex-wrap: wrap", joined)


def test_detached_card_and_focus_ring():
    css = _read(_CSS)
    assert "background: var(--lf-white)" in _rule(css, ".pagination-bar-detached")
    assert "outline: 2px solid var(--lf-dark-teal)" in _rule(css, ".data-table.table-scroll:focus-visible")
    assert re.search(r"\.pagination-bar select,\s*\.pagination-bar button \{ border-color: ButtonText; \}", css)


def test_no_old_brand_token():
    for p in (_TSX, _CSS):
        assert "lumen" not in _read(p).lower()
