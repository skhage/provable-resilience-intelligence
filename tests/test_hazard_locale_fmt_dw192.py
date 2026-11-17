"""BUG-DW-192: /hazards KPI cards and crosswalk table pin counts to en-US (section 6.4).

Static checks on the 3 hazard components plus a Node known-answer test of the shared
formatCount helper run under a German process locale.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
HZ = os.path.join(UI, "components", "hazards")
FILES = {
    "hazard-kpi-row.tsx": ["active_hazards", "spans_at_risk", "services_impacted"],
    "hazard-crosswalk-kpis.tsx": ["total_intersections", "distinct_spans_exposed",
                                  "total_spans", "direct_impact_count"],
    "hazard-crosswalk-table.tsx": ["rows.length", "row.intersection_count", "row.distinct_spans",
                                   "totals.intersection_count", "totals.distinct_spans"],
}
_HELPER = os.path.join(UI, "lib", "bb-srlg-disclosure.ts")
_IMPORT = 'import { formatCount } from "@/lib/bb-srlg-disclosure";'
_BARE = re.compile(r"\.toLocaleString\(\s*\)")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _ui_sources():
    for root, _dirs, names in os.walk(UI):
        if "node_modules" in root:
            continue
        for n in names:
            if n.endswith((".ts", ".tsx")):
                yield os.path.join(root, n)


# ---------- static ----------

def test_no_bare_tolocalestring_anywhere_in_ui():
    hits = [f"{os.path.relpath(p, UI)}:{i}" for p in _ui_sources()
            for i, line in enumerate(_read(p).splitlines(), 1) if _BARE.search(line)]
    assert hits == [], hits


@pytest.mark.parametrize("name", sorted(FILES))
def test_hazard_file_has_no_tolocalestring_and_imports_shared_helper(name):
    src = _read(os.path.join(HZ, name))
    assert "toLocaleString(" not in src
    assert _IMPORT in src
    # no 4th local copy of a count formatter
    assert not re.search(r"function\s+(formatCount|fmtCount)\b", src)


@pytest.mark.parametrize("name,fields", sorted(FILES.items()))
def test_each_field_rendered_via_formatcount(name, fields):
    src = _read(os.path.join(HZ, name))
    for f in fields:
        expr = f if "." in f else "summary." + f
        assert f"formatCount({expr})" in src, expr


@pytest.mark.parametrize("name", ["hazard-kpi-row.tsx", "hazard-crosswalk-kpis.tsx"])
def test_kpi_aria_label_matches_visible_value(name):
    src = _read(os.path.join(HZ, name))
    pairs = 0
    for m in re.finditer(r"aria-label=\{`[^`]*\$\{formatCount\(([^)]+)\)\}[^`]*`\}(.*?)</div>\s*</div>",
                         src, re.S):
        expr, body = m.group(1), m.group(2)
        assert f"kpi-value\">{{formatCount({expr})}}" in body, expr
        pairs += 1
    assert pairs >= (3 if name == "hazard-kpi-row.tsx" else 2)


def test_branding_clean():
    banned = "lu" + "men"
    for name in FILES:
        assert banned not in _read(os.path.join(HZ, name)).lower()


# ---------- node known-answer under a German locale ----------

def _node(expr, lang="de_DE.UTF-8"):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(_HELPER, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    env = dict(os.environ, LANG=lang, LC_ALL=lang)
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20, env=env)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


@pytest.mark.parametrize("n,out", [(173323, "173,323"), (0, "0"), (10092, "10,092"), (31957, "31,957")])
def test_formatcount_known_answer_under_de_locale(n, out):
    assert _node(f"M.formatCount({n})") == out


def test_helper_differs_from_explicit_de_format():
    # Proves the pin matters: an explicit de-DE format would read as a decimal.
    d = _node("[M.formatCount(31957), (31957).toLocaleString('de-DE')]")
    assert d[0] == "31,957"
    assert d[1] != d[0]
