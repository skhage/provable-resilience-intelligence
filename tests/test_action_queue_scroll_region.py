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


# --- BUG-DW-110: cascade-order checks -------------------------------------------------------
# Minimal cascade resolver: walks top-level rules and simple @media (max-width: Npx) blocks in
# source order and returns the last declaration that applies at a given viewport width for an
# exact selector. Good enough for this stylesheet (no nesting beyond one @media level).

def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _iter_rules(css):
    """Yield (media_max_width_or_None, media_raw_or_None, selector_list, body) in source order."""
    css = _strip_comments(css)
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        head = css[i:j].strip()
        if head.startswith("@"):  # @media recurses; @keyframes/@supports/etc. are skipped whole
            depth, k = 1, j + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            inner = css[j + 1:k - 1]
            m = re.fullmatch(r"@media \(max-width: (\d+)px\)", head)
            if head.startswith("@media"):
                for _, _, sel, body in _iter_rules(inner):
                    yield (int(m.group(1)) if m else None, head, sel, body)
            i = k
        else:
            k = css.find("}", j)
            yield (None, None, [s.strip() for s in head.split(",")], css[j + 1:k])
            i = k + 1


def _computed(css, selector, prop, width):
    val = None
    for mw, raw, sels, body in _iter_rules(css):
        if selector not in sels:
            continue
        if raw is not None and (mw is None or width > mw):
            continue  # non-width media (forced-colors, motion) or not matching this width
        for decl in body.split(";"):
            if ":" in decl:
                p, v = decl.split(":", 1)
                if p.strip() == prop:
                    val = v.strip()
    return val


def test_resolver_sanity_known_case():
    # Known answer: the old buggy ordering must resolve to 32px on mobile.
    css = (".pagination-bar button { min-height: 32px; }\n"
           "@media (max-width: 767px) {\n  .x { a: b; }\n}\n")
    old = ("@media (max-width: 767px) {\n  .pagination-bar button { min-height: 44px; }\n}\n" + css)
    assert _computed(old, ".pagination-bar button", "min-height", 375) == "32px"
    new = css + "@media (max-width: 767px) {\n  .pagination-bar button { min-height: 44px; }\n}\n"
    assert _computed(new, ".pagination-bar button", "min-height", 375) == "44px"
    assert _computed(new, ".pagination-bar button", "min-height", 1280) == "32px"


def test_mobile_pagination_targets_44px():
    css = _read(_CSS)
    for w in (320, 375, 767):
        assert _computed(css, ".pagination-bar button", "min-height", w) == "44px", w
        assert _computed(css, ".pagination-bar button", "min-width", w) == "44px", w
        assert _computed(css, ".pagination-bar select", "min-height", w) == "44px", w
    # Desktop keeps the compact 32px base.
    assert _computed(css, ".pagination-bar button", "min-height", 1280) == "32px"


def test_mobile_override_after_base_rule():
    css = _strip_comments(_read(_CSS))
    base = re.search(r"(?m)^\.pagination-bar button \{[^}]*min-height: 32px", css).start()
    override = [m.start() for m in re.finditer(r"\.pagination-bar button \{\s*min-height: 44px", css)]
    assert len(override) == 1, "exactly one 44px override (dead copy removed)"
    assert override[0] > base


def test_scroll_hint_visible_through_tablet():
    css = _read(_CSS)
    assert _computed(css, ".table-scroll-hint", "display", 320) == "block"
    assert _computed(css, ".table-scroll-hint", "display", 900) == "block"
    assert _computed(css, ".table-scroll-hint", "display", 1023) == "block"
    assert _computed(css, ".table-scroll-hint", "display", 1024) == "none"


def test_scroll_hint_stays_aria_hidden_on_both_routes():
    conduits = os.path.join(UI, "routes", "conduits.tsx")
    for p in (_TSX, conduits):
        s = _read(p)
        assert s.count("table-scroll-hint") == s.count('table-scroll-hint" aria-hidden="true"') >= 1, p
