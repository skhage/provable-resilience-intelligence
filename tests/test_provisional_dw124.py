"""BUG-DW-124: the scorecard_header PROVISIONAL sources must be exactly the objects the header cards read.

V4-KPI-COPY-SPEC §7.1 (status per object, so each surface clears independently), §7.2 (header source =
resilience_score_snapshot) and §7.3 Removal (the badge goes away once its object is promoted).
These checks run the real provisional-disclosure.ts module in Node using --experimental-strip-types.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "apps" / "resilience-scorecard" / "src"
PKG = APP_SRC / "resilience_scorecard"
PROV_TS = PKG / "ui" / "lib" / "provisional-disclosure.ts"
CATALOG_SQL = PKG / "backend" / "services" / "catalog_sql.py"
sys.path.insert(0, str(APP_SRC))

from resilience_scorecard.backend import provisional_objects as po  # noqa: E402

DEFAULT = list(po.DEFAULT_PROVISIONAL_OBJECTS)
RSS = "resilience_score_snapshot"


def _node_ts(expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(PROV_TS, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _variants(objs, report_status="INTERIM"):
    o = json.dumps(objs)
    rs = json.dumps(report_status)
    return _node_ts(
        "{header: M.badgeVariant(true, " + rs + ", " + o + ", 'scorecard_header'), "
        "table: M.badgeVariant(true, " + rs + ", " + o + ", 'service_table')}"
    )


# ---------------------------------------------------------------- designer's mandated cases

def test_rss_promoted_mvs_kept_header_not_provisional():
    v = _variants(["revenue_at_risk", "diversity_coverage"])
    assert v["header"] != "provisional"
    assert v == {"header": "interim", "table": "interim"}


def test_only_rss_kept_header_equals_table_provisional():
    v = _variants([RSS])
    assert v["header"] == v["table"] == "provisional"


def test_only_diversity_coverage_kept_no_header_badge_change():
    v = _variants(["diversity_coverage"])
    assert v["header"] == "interim"


def test_partial_today_default_list_still_provisional_everywhere():
    # With the 10-object default list, every header surface still reads PROVISIONAL (no regression).
    assert RSS in DEFAULT
    assert _variants(DEFAULT) == {"header": "provisional", "table": "provisional"}


def test_v41_staged_promotion_header_and_table_agree_for_every_subset_of_one():
    # Drop each object from the default list one at a time. The header and the table read the
    # same rss scores, so their badge must never differ (this was the visible DW-124 symptom).
    expr = ("(" + json.dumps(DEFAULT) + ").map(x => { const o = (" + json.dumps(DEFAULT) +
            ").filter(y => y !== x); return [x, M.badgeVariant(true,'INTERIM',o,'scorecard_header'), "
            "M.badgeVariant(true,'INTERIM',o,'service_table')]; })")
    for name, header, table in _node_ts(expr):
        assert header == table, (name, header, table)


def test_flag_off_unchanged():
    assert _node_ts("M.badgeVariant(false, 'INTERIM', [" + json.dumps(RSS) + "], 'scorecard_header')") is None


# ---------------------------------------------------------------- mapping is data-derived, not asserted

def _sources_from_text():
    text = PROV_TS.read_text()
    block = re.search(r"const SURFACE_SOURCES[^=]*=\s*\{(.*?)\n\};", text, re.S).group(1)
    block = re.sub(r"^\s*//.*$", "", block, flags=re.M)
    return {k: re.findall(r'"([a-z0-9_]+)"', v) for k, v in re.findall(r"(\w+):\s*\[([^\]]*)\]", block)}


def _summary_sql_tables():
    src = CATALOG_SQL.read_text()
    sql = re.search(r'^_SUMMARY_SQL\s*=\s*"""(.*?)"""', src, re.S | re.M).group(1)
    return set(re.findall(r"\b(?:FROM|JOIN)\s+(?:[\w]+\.)*([a-z_][a-z0-9_]*)", sql, re.I))


def test_header_sources_equal_summary_sql_tables_that_are_keep_v3():
    # Header sources must be exactly the KEEP_V3 objects that _SUMMARY_SQL reads (§7.2).
    expected = _summary_sql_tables() & set(DEFAULT)
    assert expected == {RSS}  # known answer from the live SQL constant
    assert set(_sources_from_text()["scorecard_header"]) == expected


def test_header_and_service_table_share_source():
    s = _sources_from_text()
    assert s["scorecard_header"] == s["service_table"] == [RSS]


def test_no_ui_surface_lists_an_object_without_a_ui_consumer():
    s = _sources_from_text()
    for surface, objs in s.items():
        assert "diversity_coverage" not in objs, surface
        assert "revenue_at_risk" not in objs, surface


def test_stale_comment_removed():
    text = PROV_TS.read_text()
    assert "card reads revenue_at_risk" not in text
    assert "BUG-DW-124" in text


def test_backend_ten_object_list_untouched():
    # The designer's fix is UI mapping only; Genie/DEC-42 still labels all 10 objects.
    assert len(DEFAULT) == 10
    assert {"revenue_at_risk", "diversity_coverage"} <= set(DEFAULT)
