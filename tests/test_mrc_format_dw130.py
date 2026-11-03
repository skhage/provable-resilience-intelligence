"""BUG-DW-130: MRC Protected K/M formatter must never print $1000K (V4-KPI-COPY-SPEC §1/§6.4).

Known answers run the real .ts module under node --experimental-strip-types.
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
FMT_TS = os.path.join(UI, "lib", "v4-delta-format.ts")
TABLE_TSX = os.path.join(UI, "components", "actions", "action-queue-table.tsx")


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


CASES = [
    (999_499, "$999K", "$999 thousand"),
    (999_500, "$1.0M", "$1.0 million"),
    (999_999, "$1.0M", "$1.0 million"),
    (1_000_000, "$1.0M", "$1.0 million"),
    (72_767_771, "$72.8M", "$72.8 million"),
    (1_049_999, "$1.0M", "$1.0 million"),
    (1_050_000, "$1.1M", "$1.1 million"),
    (1_234_567_890, "$1,234.6M", "$1,234.6 million"),
    (500, "$1K", "$1 thousand"),
    (12_345, "$12K", "$12 thousand"),
]


@pytest.fixture(scope="module")
def results():
    vals = ",".join(str(c[0]) for c in CASES)
    return _node_ts(FMT_TS, f"[{vals}].map(v => M.formatMonthlyUsd(v))")


@pytest.mark.parametrize("i", range(len(CASES)))
def test_known_answers(results, i):
    usd, disp, spoken = CASES[i]
    assert results[i] == [disp, spoken], usd


def test_never_1000k_across_boundary():
    out = _node_ts(FMT_TS, "Array.from({length: 2001}, (_, i) => M.formatMonthlyUsd(998_500 + i)[0])")
    assert not any("1000K" in s or "1,000K" in s for s in out)
    assert out[0] == "$999K" and out[-1] == "$1.0M"


def test_spoken_matches_visible_digits(results):
    for disp, spoken in results:
        num = re.match(r"\$([\d,.]+)[KM]$", disp).group(1)
        unit = "million" if disp.endswith("M") else "thousand"
        assert spoken == f"${num} {unit}"


def test_table_uses_shared_formatter_and_no_local_copy():
    src = _read(TABLE_TSX)
    assert 'import { formatMonthlyUsd } from "@/lib/v4-delta-format";' in src
    assert "function formatMonthlyUsd" not in src
    assert "Math.round(usd / 1_000)" not in src
    # aria-label is built from the same spoken value as the visible card value
    assert "const [value, spoken] = formatMonthlyUsd(data.mrc_protected_usd);" in src
    assert "aria-label={`MRC Protected: ${spoken} per month" in src


def test_zero_or_null_renders_no_card():
    src = _read(TABLE_TSX)
    assert "!(data.mrc_protected_usd > 0)" in src
    assert "!data ||" in src


def test_no_other_k_formatter_in_ui():
    hits = []
    for dp, _, files in os.walk(UI):
        if "node_modules" in dp:
            continue
        for fn in files:
            if fn.endswith((".ts", ".tsx")):
                s = _read(os.path.join(dp, fn))
                if re.search(r"Math\.round\([^)]*/\s*1_?000\)", s):
                    hits.append(fn)
    assert hits == []


def test_no_brand_leak():
    for dp, _, files in os.walk(UI):
        if "node_modules" in dp:
            continue
        for fn in files:
            if fn.endswith((".ts", ".tsx", ".css")):
                assert "lumen" not in _read(os.path.join(dp, fn)).lower(), fn
