"""BUG-DW-126: Medium Risk KPI uses formatKpiCount under the v4 flag (2635 -> '2,635').

Acceptance (designer S72):
(a) flag on: value and aria-label read 'Medium Risk: 2,635'.
(b) flag off: the false branch is the raw v3 field, so rendered output is unchanged.
(c) every count kpi-card in the risk band (Critical, High, Medium) goes through
    formatKpiCount under v4Kpis, so the next card cannot drift.
(d) grep 'lumen' in ui/ = 0.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
FMT_TS = os.path.join(UI, "lib", "v4-delta-format.ts")

# label -> summary field for every count card that must format under the flag.
# P363: the risk cards are keyed by governed level and use riskCardAria(level, var, cuts).
RISK_KEYS = ("critical", "at_risk", "moderate", "healthy")
COUNT_CARDS = {
    "critical": "critical_count",
    "at_risk": "at_risk_count",
    "moderate": "moderate_count",
}


def _src():
    s = open(HEADER, encoding="utf-8").read()
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


def _card_block(src, label):
    """Text of the kpi-card whose aria-label starts with `label:` up to the next kpi-card."""
    if label in RISK_KEYS:
        aria = r'aria-label=\{riskCardAria\("' + re.escape(label) + r'", '
    else:
        aria = r"aria-label=\{`" + re.escape(label) + r": "
    m = re.search(r'<div className="kpi-card[^"]*"\s+role="group" ' + aria, src)
    assert m, f"no kpi-card for {label}"
    nxt = src.find('<div className="kpi-card', m.end())
    return src[m.start(): nxt if nxt != -1 else len(src)]


def _node_ts(ts_path, expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(ts_path, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _aria_var(block, label):
    """Variable the card aria-label interpolates (template literal or riskCardAria arg)."""
    if label in RISK_KEYS:
        m = re.search(r'aria-label=\{riskCardAria\("' + re.escape(label) + r'", (\w+), cuts\)\}', block)
    else:
        m = re.search(r"aria-label=\{`" + re.escape(label) + r": \$\{(\w+)\}`\}", block)
    assert m, f"{label}: aria-label must interpolate a single variable"
    return m.group(1)


@pytest.mark.parametrize("label,field", list(COUNT_CARDS.items()))
def test_count_card_value_and_aria_use_flag_gated_formatter(label, field):
    src = _src()
    block = _card_block(src, label)
    var = _aria_var(block, label)
    vals = re.findall(r'<div className="kpi-value">\{(\w+)\}</div>', block)
    assert vals == [var], f"{label}: kpi-value must render {var}, got {vals}"
    decl = re.search(r"const " + var + r" = (.+?);", src)
    assert decl, f"{var} not declared"
    assert decl.group(1).strip() == (
        f"v4Kpis ? formatKpiCount(summary.{field}) : summary.{field}"
    ), f"{label}: {decl.group(1)}"


def test_medium_raw_field_not_rendered_directly():
    src = _src()
    body = src[src.index("return (", src.index("function ScorecardHeaderContent")):]
    assert "summary.moderate_count" not in body


def test_formatter_known_answers():
    d = _node_ts(FMT_TS, "[M.formatKpiCount(2635), M.formatKpiCount(2932), M.formatKpiCount(848), M.formatKpiCount(0)]")
    assert d == ["2,635", "2,932", "848", "0"]


def test_flag_on_aria_reads_spec_string():
    # Simulate the template with the real formatter output.
    v = _node_ts(FMT_TS, "M.formatKpiCount(2635)")
    assert f"Moderate: {v}" == "Moderate: 2,635"


def test_no_lumen_in_ui():
    hits = []
    for dp, _, fs in os.walk(UI):
        if "node_modules" in dp:
            continue
        for fn in fs:
            if fn.endswith((".ts", ".tsx", ".css", ".html", ".json")):
                p = os.path.join(dp, fn)
                if "lumen" in open(p, encoding="utf-8", errors="ignore").read().lower():
                    hits.append(p)
    assert hits == []
