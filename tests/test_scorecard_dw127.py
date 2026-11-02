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
