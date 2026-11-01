"""BUG-DW-125: Service Table PROVISIONAL caption Info tooltip must not be clipped by .data-table.

The caption is the first box inside .data-table (overflow:hidden). The default tooltip opens
ABOVE the trigger, so it was fully clipped. Fix (designer option a): caption-scoped variant that
opens BELOW, anchors to the badge wrap's left edge, caps width to the 320px content box, and
mirrors the BUG-DW-092 hover bridge downward. The default tooltip and .data-table overflow stay.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "apps" / "resilience-scorecard" / "src" / "resilience_scorecard" / "ui"
CSS_PATH = UI / "styles" / "lakelink-theme.css"
TSX_PATH = UI / "components" / "dashboard" / "service-table.tsx"
CSS = CSS_PATH.read_text()
TSX = TSX_PATH.read_text()


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _top_level_rules(css: str):
    """Yield (selectors, body) for top-level rules only (skips @media blocks)."""
    css = _strip_comments(css)
    depth, start = 0, 0
    head = None
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                head = css[start:i].strip()
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                if head is not None and not head.startswith("@"):
                    yield [s.strip() for s in head.split(",")], css[body_start:i]
                start = i + 1
                head = None


def _decls(selector: str) -> dict:
    """Merged declarations of all top-level rules for selector (later wins)."""
    out = {}
    for sels, body in _top_level_rules(CSS):
        if selector in sels:
            for d in body.split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    out[k.strip()] = re.sub(r"\s+", " ", v.strip())
    return out


def test_caption_tooltip_opens_below():
    d = _decls(".service-table-caption .info-tooltip")
    assert d.get("top") == "calc(100% + 6px)"
    assert d.get("bottom") == "auto"


def test_caption_tooltip_left_anchored_not_centred():
    d = _decls(".service-table-caption .info-tooltip")
    assert d.get("left") == "0"
    assert d.get("transform") == "none"


def test_caption_tooltip_fits_320px_content_box():
    d = _decls(".service-table-caption .info-tooltip")
    m = re.fullmatch(r"min\((\d+)px, calc\(100vw - (\d+)px\)\)", d.get("max-width", ""))
    assert m, d.get("max-width")
    cap, gutter = int(m.group(1)), int(m.group(2))
    # 320px viewport, mobile page padding 16px each side -> 288px content box
    assert min(cap, 320 - gutter) <= 320 - 2 * 16
    assert gutter >= 2 * 16


def test_containing_block_is_badge_wrap():
    assert _decls(".service-table-caption .interim-badge-wrap").get("position") == "relative"
    assert _decls(".service-table-caption .info-tip").get("position") == "static"


def test_hover_bridge_mirrored_downward_and_covers_gap():
    d = _decls(".service-table-caption .info-tooltip::after")
    assert d.get("bottom") == "100%"
    assert d.get("top") == "auto"
    base = _decls(".info-tooltip::after")
    gap = int(re.search(r"(\d+)px", _decls(".service-table-caption .info-tooltip")["top"]).group(1))
    assert int(base["height"].rstrip("px")) > gap  # BUG-DW-092: bridge must exceed the gap


def test_default_tooltip_unchanged():
    d = _decls(".info-tooltip")
    assert d.get("bottom") == "calc(100% + 6px)"
    assert d.get("transform") == "translateX(-50%)"
    assert "top" not in d
    assert _decls(".info-tooltip::after").get("top") == "100%"


def test_data_table_overflow_hidden_kept():
    assert _decls(".data-table").get("overflow") == "hidden"


def test_caption_still_renders_single_provisional_badge_inside_table():
    m = re.search(r'<caption className="service-table-caption">(.*?)</caption>', TSX, re.S)
    assert m
    assert m.group(1).count("<InterimBadge") == 1
    assert 'variant="provisional"' in m.group(1)
    assert TSX.count("<InterimBadge") == 1


def test_no_legacy_brand_name():
    for p in (CSS_PATH, TSX_PATH, Path(__file__)):
        assert "lu" + "men" not in p.read_text().lower()
