"""BUG-DW-127: every count KPI card formats under the v4 flag (value + aria-label).

Acceptance (designer S74):
(a) Low Risk, Single-Point Failures and Monitored Services use
    `v4Kpis ? formatKpiCount(summary.X) : summary.X` for both value and aria-label.
(b) Flag off: the false branch is the raw v3 field (unchanged output).
(c) SRLG Groups: under the flag the card is SrlgGroupsV4Card, which formats via
    formatCount for value and aria; the raw v3 card is reachable only when v4Kpis is false.
(d) No count card in the row renders a raw summary.* count field directly.
"""
import os
import re

import pytest

from test_scorecard_dw126 import FMT_TS, UI, _card_block, _node_ts, _src

DISCLOSURE_TS = os.path.join(UI, "lib", "bb-srlg-disclosure.ts")

ALL_COUNT_CARDS = {
    "Critical Risk": "critical_count",
    "High Risk": "high_risk_count",
    "Medium Risk": "medium_risk_count",
    "Low Risk": "low_risk_count",
    "Single-Point Failures": "total_single_point_failures",
    "Monitored Services": "total_services",
}


@pytest.mark.parametrize("label,field", list(ALL_COUNT_CARDS.items()))
def test_count_card_flag_gated(label, field):
    src = _src()
    block = _card_block(src, label)
    aria = re.search(r"aria-label=\{`" + re.escape(label) + r": \$\{(\w+)\}`\}", block)
    assert aria, f"{label}: aria-label must interpolate a single variable"
    var = aria.group(1)
    vals = re.findall(r'<div className="kpi-value">\{(\w+)\}</div>', block)
    assert vals == [var], f"{label}: kpi-value must render {var}, got {vals}"
    decl = re.search(r"const " + var + r" = (.+?);", src)
    assert decl, f"{var} not declared"
    assert decl.group(1).strip() == f"v4Kpis ? formatKpiCount(summary.{field}) : summary.{field}"


def test_no_raw_count_field_rendered_in_row():
    src = _src()
    body = src[src.index("return (", src.index("function ScorecardHeaderContent")):]
    for field in ALL_COUNT_CARDS.values():
        assert f"summary.{field}" not in body, field


def test_srlg_v3_card_only_on_flag_off_branch():
    src = _src()
    body = src[src.index("return (", src.index("function ScorecardHeaderContent")):]
    m = re.search(r"\{v4Kpis \? \(\s*<SrlgGroupsV4Card(.*?)\) : \((.*?)\)\}", body, re.S)
    assert m, "SRLG card must be a v4Kpis ternary with SrlgGroupsV4Card on the true branch"
    assert "total={summary.total_srlg_groups}" in m.group(1)
    assert "aria-label={`SRLG Groups: ${summary.total_srlg_groups}`}" in m.group(2)
    assert body.count("summary.total_srlg_groups") == 3  # v4 prop + v3 aria + v3 value


def test_srlg_v4_card_formats_value_and_aria():
    src = _src()
    fn = src[src.index("function SrlgGroupsV4Card"):src.index("function ScorecardHeaderContent")]
    assert "const n = formatCount(total);" in fn
    assert "`SRLG Groups: ${n}, metro and access spans only`" in fn
    assert re.search(r'<div className="kpi-value">\s*\{n\}', fn)
    assert "{total}" not in fn


def test_formatter_known_answers_live_values():
    d = _node_ts(FMT_TS, "[M.formatKpiCount(1585), M.formatKpiCount(8000), M.formatKpiCount(312), M.formatKpiCount(0)]")
    assert d == ["1,585", "8,000", "312", "0"]
    # SRLG card uses a different helper; it must agree for integers so the row is uniform.
    e = _node_ts(DISCLOSURE_TS, "[M.formatCount(1585), M.formatCount(8000), M.formatCount(312)]")
    assert e == d[:3]


# ---------------------------------------------------------------------------
# BUG-DW-137 (designer S98 / P122): raw counts >= 1,000 outside the scorecard header.
# Appended here (not a new file) per @repo-pruner's file-cap request.
# ---------------------------------------------------------------------------
AQ_TSX = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
ST_TSX = os.path.join(UI, "components", "dashboard", "service-table.tsx")
TOPO_TSX = os.path.join(UI, "routes", "topology.tsx")

ACTION_CARDS = {
    "Critical Pending": "critical_pending",
    "Total Pending": "pending_count",
    "In Progress": "in_progress_count",
    "Completed": "completed_count",
}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _action_cards_fn():
    src = _read(AQ_TSX)
    start = src.index("function ActionSummaryCards")
    return src[start:src.index("const PAGE_SIZES", start)]


@pytest.mark.parametrize("label,field", list(ACTION_CARDS.items()))
def test_dw137_action_card_value_and_aria_formatted(label, field):
    fn = _action_cards_fn()
    aria = re.search(r"aria-label=\{`" + re.escape(label) + r": \$\{(\w+)\}`\}", fn)
    assert aria, f"{label}: aria-label must interpolate a single variable"
    var = aria.group(1)
    card_end = fn.index("</div>\n      </div>", aria.end()) + len("</div>")
    card = fn[aria.end():card_end]
    vals = re.findall(r'<div className="kpi-value">\{(\w+)\}</div>', card)
    assert vals == [var], f"{label}: kpi-value must render {var}, got {vals}"
    assert f"const {var} = formatCount(summary.{field});" in fn


def test_dw137_action_cards_no_raw_summary_counts():
    fn = _action_cards_fn()
    assert not re.search(r"\{summary\.\w+\}", fn)
    assert not re.search(r"\$\{summary\.\w+\}", fn)
    assert 'import { formatCount } from "@/lib/bb-srlg-disclosure";' in _read(AQ_TSX)


def test_dw137_service_table_pagination_formatted():
    src = _read(ST_TSX)
    nav = src[src.index('aria-label="Service table pagination"'):]
    nav = nav[:nav.index("</span>")]
    assert "of {formatCount(scores.length)}" in nav
    assert "Showing {formatCount((safeCurrentPage - 1) * pageSize + 1)}" in nav
    assert "{formatCount(Math.min(safeCurrentPage * pageSize, scores.length))}" in nav
    assert "of {scores.length}" not in nav
    assert re.search(r"import \{[^}]*\bformatCount\b[^}]*\} from \"@/lib/bb-srlg-disclosure\"", src)


@pytest.mark.parametrize("raw", [
    "${totalSites} sites", "${totalConduits} conduits",
    "${r.site_count} sites", "${r.conduit_count} conduits",
    "{r.site_count} sites", "{r.co_count} COs", "{r.dc_count} DCs",
    "{r.conduit_count} conduits", "{r.span_count} spans",
    "${region.site_count} sites", "${region.conduit_count} conduits",
    "{region.site_count} sites",
])
def test_dw137_topology_region_counts_not_raw(raw):
    assert raw not in _read(TOPO_TSX), f"raw count still rendered: {raw}"


def test_dw137_topology_region_counts_formatted():
    src = _read(TOPO_TSX)
    for s in (
        "${formatCount(totalSites)} sites, ${formatCount(totalConduits)} conduits",
        "${r.region} region: ${formatCount(r.site_count)} sites, ${formatCount(r.conduit_count)} conduits.",
        "{formatCount(r.conduit_count)} conduits \u00b7 {formatCount(r.span_count)} spans",
        "{formatCount(r.site_count)} sites \u00b7 {formatCount(r.co_count)} COs",
        "${region.region} region, ${formatCount(region.site_count)} sites",
        "{formatCount(region.site_count)} sites\n",
    ):
        assert s in src, s


def test_dw137_known_answers_live_values():
    # Live values from designer P122: 3159/6181 pending/completed, 480 critical, 8000 services,
    # 3152/2610 region spans, 2969 overview sites.
    d = _node_ts(DISCLOSURE_TS, "[3159,6181,480,8000,3152,2610,2969,999,1000,0].map(M.formatCount)")
    assert d == ["3,159", "6,181", "480", "8,000", "3,152", "2,610", "2,969", "999", "1,000", "0"]
    # Uniform with the header formatter used beside it under the v4 flag.
    k = _node_ts(FMT_TS, "[3159,6181,8000,3152].map(M.formatKpiCount)")
    assert k == d[:2] + [d[3], d[4]]


# --- BUG-DW-147: APG sortable table headers (WCAG 4.1.2 / 2.1.1) ---------------
HX_TSX = os.path.join(UI, "components", "hazards", "hazard-crosswalk-table.tsx")
HS_TSX = os.path.join(UI, "components", "hazards", "hazard-summary-table.tsx")
THEME_CSS = os.path.join(UI, "styles", "lakelink-theme.css")
DW147_FILES = {ST_TSX: 1, HX_TSX: 4, HS_TSX: 3}  # expected sortable headers per file


def _th_open_tags(src):
    return re.findall(r"<th\b[^>]*>", src)


def _sort_fn_body(src, name):
    m = re.search(r"const " + name + r" = \(field: SortField[^)]*\) => \(\{?(.*?)\n  \}?\);", src, re.S)
    return m.group(1) if m else ""


@pytest.mark.parametrize("path", list(DW147_FILES))
def test_dw147_no_focusable_or_role_th(path):
    src = _read(path)
    for tag in _th_open_tags(src):
        assert "tabIndex" not in tag, tag
        assert "onKeyDown" not in tag and "onClick" not in tag, tag
        assert "role=" not in tag, tag
    assert 'role="columnheader"' not in src and 'role: "columnheader"' not in src
    # sortProps spreads onto the th, so it must carry aria-sort only.
    body = _sort_fn_body(src, "sortProps")
    if body:
        for bad in ("tabIndex", "onKeyDown", "onClick", "role", "cursor"):
            assert bad not in body, f"sortProps still has {bad}"
        assert '"aria-sort"' in body


@pytest.mark.parametrize("path,count", list(DW147_FILES.items()))
def test_dw147_each_sortable_th_has_one_button(path, count):
    src = _read(path)
    cells = re.findall(r"<th\b([^>]*)>(.*?)</th>", src, re.S)
    sortable = [(a, body) for a, body in cells if "aria-sort" in a or "sortProps" in a]
    assert len(sortable) == count, (path, len(sortable))
    for a, body in sortable:
        n_btn = body.count("<button") + body.count("sortButton(")
        assert n_btn == 1, body
    if "sortButton(" in src:
        fn = _sort_fn_body(src, "sortButton")
        assert fn.count("<button") == 1 and 'type="button"' in fn and 'className="th-sort-button"' in fn
        assert '<span aria-hidden="true">{sortIndicator(field)}</span>' in fn
    else:
        btn = re.search(r"<button[^>]*th-sort-button[^>]*>(.*?)</button>", src, re.S).group(1)
        assert '<span aria-hidden="true">' in btn and "▲" in btn


@pytest.mark.parametrize("path", list(DW147_FILES))
def test_dw147_glyphs_only_inside_aria_hidden(path):
    src = _read(path)
    # Every sort glyph literal in JSX/expressions must sit in the indicator helper or an aria-hidden span.
    for line in src.splitlines():
        if ("▲" in line or "▼" in line) and "sortIndicator = " not in line:
            stripped = line.strip()
            if stripped.startswith("sortField ==="):
                continue  # body of the sortIndicator arrow
            assert 'aria-hidden="true"' in line, line


def test_dw147_css_button_rules():
    css = _read(THEME_CSS)
    base = re.search(r"(?m)^\.th-sort-button \{(.*?)\}", css, re.S).group(1)
    for decl in ("font: inherit", "color: inherit", "background: none", "border: 0", "width: 100%", "cursor: pointer"):
        assert decl in base, decl
    ring = re.search(r"(?m)^\.data-table th \.th-sort-button:focus-visible \{(.*?)\}", css, re.S).group(1)
    assert "var(--lf-white)" in ring  # dark-teal global ring would be 1:1 on the dark-teal th
    assert re.search(r"@media \(max-width: 767px\) \{\s*\.th-sort-button \{ min-height: 44px; \}", css)
    # The old focusable-th rule is gone (th is no longer focusable).
    assert "th[aria-sort]:focus-visible" not in css


def test_dw147_brand():
    for p in list(DW147_FILES) + [THEME_CSS]:
        assert "lumen" not in _read(p).lower(), p
