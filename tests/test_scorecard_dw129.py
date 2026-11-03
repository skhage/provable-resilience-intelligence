"""BUG-DW-129 + BUG-DW-097: SRLG Groups v4 card '(metro/access)' qualifier.

DW-129 / DW-097 item 2: the visual slash qualifier is aria-hidden; speech comes only from the
card role=group aria-label ('metro and access'), with no sr-only duplicate.
DW-097 item 1: v4-only .kpi-sub--disclosure modifier = solid iron #4D4D4D; v3 .kpi-sub unchanged.
DW-097 item 3: .mobile-tree-diversity-summary wraps (already shipped in BUG-DW-106; pinned here).
"""
import glob
import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")

# sha256 of the flag-off (v3) SRLG card branch and the base .kpi-sub rule at HEAD 430e05a.
V3_SRLG_BRANCH_SHA = "bb907dca76000fddfa2ee3920b2a47ceb7e2d1ef1d817e51313bf99ba7bfedbe"
KPI_SUB_RULE_SHA = "9be55cdc3f1b77e70049ec74ed786ecbc38783b622b40abd94f0cf41a4ad100e"


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _strip_jsx_comments(src):
    return re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)


def _v4_card(src):
    return src[src.index("function SrlgGroupsV4Card"):src.index("function ScorecardHeaderContent")]


def _enclosing_open_tags(src, pos):
    """Open JSX tags enclosing pos (simple stack scan; ignores self-closing and {..} bodies)."""
    stack = []
    for m in re.finditer(r"<(/?)([A-Za-z][\w.]*)((?:[^<>{}]|\{[^{}]*\})*?)(/?)>", src[:pos]):
        closing, name, attrs, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        if selfclose:
            continue
        if closing:
            while stack and stack[-1][0] != name:
                stack.pop()
            if stack:
                stack.pop()
        else:
            stack.append((name, attrs))
    return stack


def test_every_metro_access_render_in_ui_is_aria_hidden():
    """(a) ui/-wide: every JSX render of ${METRO_ACCESS} is inside an aria-hidden element."""
    files = glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True)
    assert files
    hits = 0
    for f in files:
        src = _strip_jsx_comments(_read(f))
        for m in re.finditer(r"\$\{METRO_ACCESS\}", src):
            hits += 1
            tags = _enclosing_open_tags(src, m.start())
            assert any('aria-hidden="true"' in attrs for _, attrs in tags), (
                os.path.relpath(f, UI), src[src.rfind("\n", 0, m.start()) + 1: src.find("\n", m.end())].strip())
    # scorecard-header (1) + service-table (1) + topology (2)
    assert hits >= 4, hits


def test_v4_card_qualifier_aria_hidden_no_sr_only_duplicate():
    card = _strip_jsx_comments(_v4_card(_read(HEADER)))
    assert ('{partial && <span className="kpi-sub kpi-sub--disclosure" aria-hidden="true">'
            '{`\\u00A0${METRO_ACCESS}`}</span>}') in card
    # spoken form comes only from the group aria-label: no sr-only span, no METRO_ACCESS_SPOKEN
    assert "sr-only" not in card
    assert "METRO_ACCESS_SPOKEN" not in card


def test_v4_card_aria_label_spoken_form_never_slash():
    """(b) aria-label contains 'metro and access' while partial, never '/'."""
    card = _v4_card(_read(HEADER))
    m = re.search(r"const aria = partial\s*\?\s*`([^`]*)`\s*:\s*`([^`]*)`;", card)
    assert m, "aria ternary not found"
    partial_lbl, full_lbl = m.group(1), m.group(2)
    assert "metro and access" in partial_lbl
    assert "/" not in partial_lbl and "/" not in full_lbl
    assert 'role="group" aria-label={aria}' in card


def test_comment_corrected():
    card = _v4_card(_read(HEADER))
    assert "speech comes from the card aria-label */" not in card
    assert "does NOT hide its children" in card and "aria-hidden" in card


def test_flag_off_v3_srlg_card_byte_identical():
    """(c) v3 SRLG branch unchanged vs HEAD 430e05a."""
    src = _read(HEADER)
    m = re.search(r"\{v4Kpis \? \(\s*<SrlgGroupsV4Card(.*?)\) : \((.*?)\)\}", src, re.S)
    assert m
    assert hashlib.sha256(m.group(2).encode()).hexdigest() == V3_SRLG_BRANCH_SHA
    assert "kpi-sub--disclosure" not in m.group(2)


def test_base_kpi_sub_rule_byte_identical():
    css = _read(CSS)
    rule = re.search(r"(?m)^\.kpi-sub \{[^}]*\}", css).group(0)
    assert hashlib.sha256(rule.encode()).hexdigest() == KPI_SUB_RULE_SHA


def _rel_lum(hex_):
    h = hex_.lstrip("#")
    def ch(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_disclosure_modifier_solid_iron():
    """DW-097 item 1: solid #4D4D4D, more specific than .kpi-sub, contrast >= 7:1 on white."""
    css = re.sub(r"/\*.*?\*/", "", _read(CSS), flags=re.S)
    m = re.search(r"(?m)^\.kpi-sub\.kpi-sub--disclosure \{([^}]*)\}", css)
    assert m, "modifier rule missing"
    color = re.search(r"color:\s*(#[0-9A-Fa-f]{6})\s*;", m.group(1)).group(1)
    assert color.upper() == "#4D4D4D"
    ratio = (1.0 + 0.05) / (_rel_lum(color) + 0.05)
    assert ratio >= 7.0, ratio
    assert "rgba" not in m.group(1)


def test_mobile_diversity_summary_wraps():
    """DW-097 item 3 (closed by BUG-DW-106): pinned so it cannot regress."""
    css = re.sub(r"/\*.*?\*/", "", _read(CSS), flags=re.S)
    m = re.search(r"(?m)^\.mobile-tree-diversity-summary \{([^}]*)\}", css)
    assert m and re.search(r"flex-wrap:\s*wrap", m.group(1))


def test_no_lumen_in_ui():
    """(d) branding mandate."""
    for f in glob.glob(os.path.join(UI, "**", "*"), recursive=True):
        if os.path.isfile(f) and f.endswith((".tsx", ".ts", ".css")):
            assert "lumen" not in _read(f).lower(), f
