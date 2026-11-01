"""BUG-DW-093: v4 MRC Protected card polish.

(1) .info-tooltip stacks above the sticky .app-header (and below .skip-nav).
(2) .info-btn hit area is >=44x44 at <=768px while the visual button stays 24px.
(3) The caption middle dot is aria-hidden; spoken text is
    "<services> services <share>% of MRC" with no run-together words.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "apps" / "resilience-scorecard" / "src" / "resilience_scorecard" / "ui"
CSS = (UI / "styles" / "lakelink-theme.css").read_text()
TSX = (UI / "components" / "actions" / "action-queue-table.tsx").read_text()


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _top_level_rule(css: str, selector: str) -> str:
    """Body of the first top-level (not inside @media) rule for selector."""
    css = _strip_comments(css)
    depth, i, n = 0, 0, len(css)
    start = 0
    while i < n:
        ch = css[i]
        if ch == "{":
            if depth == 0:
                head = css[start:i].strip()
                end = css.index("}", i) if not head.startswith("@") else None
                if not head.startswith("@") and selector in [s.strip() for s in head.split(",")]:
                    return css[i + 1:end]
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                start = i + 1
        elif ch == ";" and depth == 0:
            start = i + 1
        i += 1
    raise AssertionError(f"top-level rule not found: {selector}")


def _media_blocks(css: str, query: str):
    css = _strip_comments(css)
    out = []
    for m in re.finditer(r"@media\s*" + re.escape(query) + r"\s*{", css):
        i, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    return out


def _prop(body: str, prop: str) -> str:
    m = re.search(r"(?:^|[;{\s])" + re.escape(prop) + r"\s*:\s*([^;]+);", body)
    assert m, f"{prop} missing in {body!r}"
    return m.group(1).strip()


def _px(v: str) -> int:
    m = re.fullmatch(r"(\d+)px", v)
    assert m, v
    return int(m.group(1))


# (1) ---------------------------------------------------------------------
def test_tooltip_stacks_above_sticky_header_below_skip_nav():
    tip = int(_prop(_top_level_rule(CSS, ".info-tooltip"), "z-index"))
    header = int(_prop(_top_level_rule(CSS, ".app-header"), "z-index"))
    skip = int(_prop(_top_level_rule(CSS, ".skip-nav"), "z-index"))
    toast = int(_prop(_top_level_rule(CSS, ".toast-stack"), "z-index"))
    assert header < tip < skip < toast, (header, tip, skip, toast)
    assert tip == 150  # value named in the binding spec


def test_no_kpi_ancestor_creates_a_stacking_context():
    # A z-index on .info-tooltip only beats the header if no KPI ancestor traps it.
    for sel in (".kpi-row", ".kpi-card", ".kpi-label-row", ".info-tip"):
        try:
            body = _top_level_rule(CSS, sel)
        except AssertionError:
            continue
        for p in ("z-index", "transform", "isolation", "filter", "will-change", "contain"):
            assert not re.search(r"(?:^|[;\s])" + p + r"\s*:", body), (sel, p)


# (2) ---------------------------------------------------------------------
def test_info_btn_visual_size_unchanged():
    base = _top_level_rule(CSS, ".info-btn")
    assert _px(_prop(base, "width")) == 24
    assert _px(_prop(base, "height")) == 24


def test_info_btn_mobile_hit_area_44():
    hits = []
    for block in _media_blocks(CSS, "(max-width: 768px)"):
        m = re.search(r"\.info-btn::before\s*{([^}]*)}", block)
        if m:
            hits.append((block, m.group(1)))
    assert len(hits) == 1, "expected exactly one mobile .info-btn::before rule"
    block, before = hits[0]
    assert _px(_prop(before, "width")) >= 44
    assert _px(_prop(before, "height")) >= 44
    assert _prop(before, "position") == "absolute"
    assert _prop(before, "content") in ('""', "''")
    assert _prop(before, "background") == "transparent"
    # the pseudo-element is positioned against the button itself
    m = re.search(r"(?:^|[}\s])\.info-btn\s*{([^}]*)}", block)
    assert m and _prop(m.group(1), "position") == "relative"
    # centred on the 24px button: offset (44-24)/2 = 10px each side
    assert _prop(before, "transform") == "translate(-50%, -50%)"
    assert _prop(before, "top") == "50%" and _prop(before, "left") == "50%"


# (3) ---------------------------------------------------------------------
def _caption_jsx() -> str:
    m = re.search(r'<div className="kpi-caption">(.*?)</div>', TSX, flags=re.S)
    assert m, "kpi-caption not found"
    return m.group(1)


def _spoken(jsx: str, services: str, share: str) -> str:
    s = re.sub(r'<span aria-hidden="true">.*?</span>', "", jsx, flags=re.S)
    s = s.replace('{" "}', " ").replace("{services}", services).replace("{share}", share)
    assert "<" not in s and "{" not in s, s
    # JSX: newline+indent between text is collapsed; same-line spaces are kept
    s = re.sub(r"\s*\n\s*", "", s)
    return re.sub(r" {2,}", " ", s).strip()


def test_caption_separator_is_aria_hidden():
    jsx = _caption_jsx()
    hidden = re.findall(r'<span aria-hidden="true">(.*?)</span>', jsx, flags=re.S)
    assert hidden == ["\u00b7"]
    visible = re.sub(r'<span aria-hidden="true">.*?</span>', "", jsx, flags=re.S)
    assert "\u00b7" not in visible and "&middot;" not in visible


def test_caption_spoken_text_known_answer():
    assert _spoken(_caption_jsx(), "4,625", "57.8") == "4,625 services 57.8% of MRC"


def test_caption_visual_text_unchanged():
    jsx = _caption_jsx()
    vis = re.sub(r'<span aria-hidden="true">(.*?)</span>', r"\1", jsx, flags=re.S)
    vis = vis.replace('{" "}', " ").replace("{services}", "4,625").replace("{share}", "57.8")
    vis = re.sub(r"\s*\n\s*", "", vis).strip()
    assert vis == "4,625 services \u00b7 57.8% of MRC"


def test_card_aria_label_unchanged():
    assert (
        "aria-label={`MRC Protected: ${spoken} per month across ${services} services "
        "with at least one completed action`}" in TSX
    )
