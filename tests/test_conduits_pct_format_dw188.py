"""BUG-DW-188: /conduits coverage % formatted with 2 decimals everywhere (binding, @designer S137).

The map <title> used the raw double (`${c.coverage_pct}% segmented` -> "100% segmented") while the
table cell showed "100.00". Both now use fmtPct(n) from lib/conduits-status.ts.
Static source checks plus Node known-answer evaluation (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
ROUTE = os.path.join(UI, "routes", "conduits.tsx")
STATUS_TS = os.path.join(UI, "lib", "conduits-status.ts")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


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


@pytest.mark.parametrize("n,expected", [
    (100, "100.00"),
    (37.254, "37.25"),
    (37.2549019607843, "37.25"),
    (0, "0.00"),
    (99.995, "100.00"),
    (5.5, "5.50"),
])
def test_fmt_pct_two_decimals(n, expected):
    assert _node_ts(STATUS_TS, "M.fmtPct(" + str(n) + ")") == expected


def test_fmt_pct_is_en_us():
    ts = _read(STATUS_TS)
    assert "export function fmtPct(n: number): string" in ts
    assert 'toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })' in ts


def test_route_imports_fmt_pct():
    src = _read(ROUTE)
    assert "  fmtPct,\n" in src


def test_map_title_uses_fmt_pct():
    src = _read(ROUTE)
    assert "${c.coverage_pct}" not in src
    assert "${fmtPct(c.coverage_pct)}% segmented" in src


def test_table_cell_uses_fmt_pct():
    src = _read(ROUTE)
    assert "{fmtPct(c.coverage_pct)}</td>" in src
    assert "coverage_pct.toFixed(" not in src


def test_branding():
    assert "Lumen" not in _read(ROUTE) and "Lumen" not in _read(STATUS_TS)
