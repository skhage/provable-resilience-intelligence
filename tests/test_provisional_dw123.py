"""BUG-DW-123: High Risk KPI formatting under the v4 flag + PROVISIONAL copy from constants.

(1) V4-KPI-COPY-SPEC S7.7 #4: with PRI_V4_KPIS on, the High Risk card value and aria-label
    use formatKpiCount (2932 -> '2,932'), the same as Critical. Flag off keeps the raw v3 value.
(2) Route files must not hard-code the S7.4 page note or the S7.2 legend line. They render
    the constants from ui/lib/provisional-disclosure.ts, and the rendered text stays
    byte-identical to the spec.
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
LIB = os.path.join(UI, "lib")
PROV_TS = os.path.join(LIB, "provisional-disclosure.ts")
FMT_TS = os.path.join(LIB, "v4-delta-format.ts")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
ROUTES = {n: os.path.join(UI, "routes", n + ".tsx") for n in ("actions", "hazards", "topology")}

SPEC_NOTE = ("Provisional: hazard exposure on this page uses the v3 hazard model. "
             "Topology and conduits use the v4 build.")
SPEC_LEGEND = "Hazard overlay: provisional (v3 hazard model)"
# Distinctive fragments of the copy; none may appear as literals outside lib/.
COPY_FRAGMENTS = ("hazard exposure on this page", "use the v4 build", "Hazard overlay: provisional")


def _read(p):
    return open(p, encoding="utf-8").read()


def _strip_comments(src):
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _node_ts(ts_path, expr):
    """Evaluate expr against a .ts module using node type stripping (skip if unsupported)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    mod = os.path.join(d, "m.ts")
    shutil.copy(ts_path, mod)
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


# ---------- (2) copy from constants ----------

def test_note_constants_reassemble_spec_byte_for_byte():
    d = _node_ts(PROV_TS, "{lead:M.PROVISIONAL_NOTE_LEAD, body:M.PROVISIONAL_NOTE_BODY, "
                          "note:M.PROVISIONAL_PAGE_NOTE, legend:M.PROVISIONAL_HAZARD_LEGEND}")
    assert d["lead"] == "Provisional:"
    assert d["body"].startswith(" ") and not d["body"].startswith("  ")
    assert d["lead"] + d["body"] == SPEC_NOTE
    assert d["note"] == SPEC_NOTE
    assert d["legend"] == SPEC_LEGEND


@pytest.mark.parametrize("name", ["actions", "hazards"])
def test_page_note_renders_lead_and_body_constants(name):
    src = _read(ROUTES[name])
    assert src.count("<strong>{PROVISIONAL_NOTE_LEAD}</strong>{PROVISIONAL_NOTE_BODY}") == 1
    assert "<strong>Provisional:</strong>" not in src


def test_topology_legend_uses_constant():
    src = _read(ROUTES["topology"])
    assert '<p className="legend-coverage-note">{PROVISIONAL_HAZARD_LEGEND}</p>' in src


def test_no_inline_provisional_copy_outside_lib():
    hits = []
    for root, _dirs, files in os.walk(UI):
        if os.path.abspath(root).startswith(os.path.abspath(LIB)) or "node_modules" in root:
            continue
        for fn in files:
            if not fn.endswith((".tsx", ".ts")):
                continue
            p = os.path.join(root, fn)
            code = _strip_comments(_read(p))
            for frag in COPY_FRAGMENTS:
                if frag.lower() in code.lower():
                    hits.append((os.path.relpath(p, UI), frag))
    assert hits == [], hits


@pytest.mark.parametrize("name", ["actions", "hazards", "topology"])
def test_every_imported_provisional_name_is_used(name):
    src = _read(ROUTES[name])
    m = re.search(r'import\s*\{([^}]*)\}\s*from\s*"@/lib/provisional-disclosure";', src)
    assert m, "provisional-disclosure import missing"
    names = [n.strip().replace("type ", "") for n in m.group(1).split(",") if n.strip()]
    body = src[m.end():]
    unused = [n for n in names if not re.search(r"\b" + re.escape(n) + r"\b", body)]
    assert unused == [], f"unused imports in {name}.tsx: {unused}"


# ---------- (1) High Risk formatting ----------

def test_format_kpi_count_known_answers():
    d = _node_ts(FMT_TS, "[M.formatKpiCount(2932), M.formatKpiCount(0), M.formatKpiCount(999), "
                         "M.formatKpiCount(1000), M.formatKpiCount(12345)]")
    assert d == ["2,932", "0", "999", "1,000", "12,345"]


def test_high_risk_formatted_like_critical_under_flag():
    src = _read(HEADER)
    assert "const highRisk = v4Kpis ? formatKpiCount(summary.high_risk_count) : summary.high_risk_count;" in src
    assert "aria-label={`High Risk: ${highRisk}`}" in src
    assert '<div className="kpi-value">{highRisk}</div>' in src
    # The raw value must not render anywhere else in the header.
    code = _strip_comments(src)
    assert code.count("summary.high_risk_count") == 2, "only the highRisk ternary may read the raw count"


def test_high_risk_card_aria_and_value_agree():
    src = _read(HEADER)
    i = src.index('className="kpi-card high"')
    card = src[i:src.index('className="kpi-card warning"', i)]
    assert "${highRisk}" in card and "{highRisk}</div>" in card
    assert "summary.high_risk_count" not in card
