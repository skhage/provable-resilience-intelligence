"""BUG-DW-179: /conduits number-format consistency (binding, @designer S131).

(a) Length/Segmented km cells always show one decimal (372 -> "372.0", 1791.176 -> "1,791.2").
(b) Every number on the route uses en-US (no bare toLocaleString()).
(c) "conduit(s)" copy replaced by noCoordsMessage(n) with subject-verb agreement + grouping.
(d) Map <title> km is formatted with fmtKm.
Static source checks plus Node known-answer evaluation (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
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


# ---------- known-answer: fmtKm / fmtCount / noCoordsMessage ----------

@pytest.mark.parametrize("n,expected", [
    (0, "0.0"),
    (1, "1.0"),
    (372, "372.0"),
    (1791.2, "1,791.2"),
    (1791.176, "1,791.2"),
    (1914, "1,914.0"),
])
def test_fmt_km_one_decimal(n, expected):
    assert _node_ts(STATUS_TS, "M.fmtKm(" + str(n) + ")") == expected


@pytest.mark.parametrize("n,expected", [(0, "0"), (1, "1"), (372, "372"), (1914, "1,914"), (10801, "10,801")])
def test_fmt_count_grouped(n, expected):
    assert _node_ts(STATUS_TS, "M.fmtCount(" + str(n) + ")") == expected


@pytest.mark.parametrize("n,expected", [
    (1, "1 conduit has no site coordinates and is listed in the table only."),
    (0, "0 conduits have no site coordinates and are listed in the table only."),
    (2, "2 conduits have no site coordinates and are listed in the table only."),
    (1914, "1,914 conduits have no site coordinates and are listed in the table only."),
])
def test_no_coords_message(n, expected):
    assert _node_ts(STATUS_TS, "M.noCoordsMessage(" + str(n) + ")") == expected


def test_result_message_still_grouped():
    out = _node_ts(STATUS_TS, 'M.conduitResultMessage(1914, "All", null)')
    assert out == "1,914 conduits match. Coverage: All. Region: All regions."


# ---------- static: route source ----------

def test_no_bare_to_locale_string_in_route():
    assert _read(ROUTE).count("toLocaleString()") == 0


def test_no_conduit_s_copy_in_route():
    assert "conduit(s)" not in _read(ROUTE)


def test_km_cells_use_fmt_km():
    src = _read(ROUTE)
    assert '<td className="mono num">{fmtKm(c.length_km)}</td>' in src
    assert '<td className="mono num">{fmtKm(c.segmented_km)}</td>' in src


def test_map_title_uses_fmt_km():
    src = _read(ROUTE)
    assert "${fmtKm(c.length_km)} km" in src
    assert "${c.length_km} km" not in src


def test_legend_km_rounded_and_grouped():
    assert "fmtCount(Math.round(c.length_km))" in _read(ROUTE)


def test_no_coords_message_used():
    assert "noCoordsMessage(conduits.length - drawable.length)" in _read(ROUTE)


def test_coverage_pct_two_decimals():
    # BUG-DW-188 superseded toFixed(2) with fmtPct (same 2-decimal output, en-US); see test_conduits_pct_format_dw188.py
    assert "{fmtPct(c.coverage_pct)}</td>" in _read(ROUTE)


def test_helpers_are_en_us():
    ts = _read(STATUS_TS)
    assert re.search(r"function fmtCount\(n: number\): string \{\s*return n\.toLocaleString\(\"en-US\"\);", ts)
    assert 'minimumFractionDigits: 1, maximumFractionDigits: 1' in ts
    assert "Lumen" not in ts and "Lumen" not in _read(ROUTE)
