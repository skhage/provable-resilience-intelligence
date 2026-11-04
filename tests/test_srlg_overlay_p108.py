"""P108-APP-SRLG-OVERLAY-LIMIT-TRUNCATION (designer ruling S91 option a, PM R98).

The /topology map and panel read /api/topology/srlgs: one row per span member, LIMIT 500, tied
ORDER BY. Every region was cut (live Central 3,382 / West 3,455 / East 4,722 / Southeast 2,114
member rows). Now the map reads the complete per-(conduit, srlg_type) summary
(_SRLG_CONDUIT_SUMMARY_SQL) and the panel lazily reads one conduit's list (_CONDUIT_SRLGS_SQL).
The v3 _SRLG_BY_REGION_SQL stays byte-identical (freeze sha c24ace6c).

Known answer: the real SQL constants run on SQLite fixtures. The reference is the full member-level
join with no LIMIT. Per conduit, the srlg_id set, srlg_type set, worst severity and M must match it
exactly. The designer's known answers have fixture equivalents: CDT-BB-0015 = 77 and CDT-BB-0053 = 134.
Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}  # mirrors UI SRLG_SEVERITY_RANK order

# The pre-P108 per-member query (ed72998), kept only as a negative-check reference.
OLD_SQL = """
SELECT srg.srlg_id, srg.srlg_type, srg.severity, srg.span_id, srg.srlg_name AS description,
  prs.site_a_id, prs.site_z_id, prs.conduit_id, ROUND(prs.length_km, 1) AS span_length_km,
  sa.site_name AS site_a_name, sz.site_name AS site_z_name
FROM shared_risk_group srg
JOIN physical_resource_span prs ON srg.span_id = prs.span_id AND prs.is_active = TRUE
JOIN geographic_site sa ON prs.site_a_id = sa.site_id
JOIN geographic_site sz ON prs.site_z_id = sz.site_id
WHERE (sa.region = :region OR sz.region = :region)
  AND sa.tier IN ('tier_1', 'tier_2') AND sz.tier IN ('tier_1', 'tier_2')
ORDER BY CASE srg.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
  srg.srlg_type
LIMIT 500
"""

# Full reference: same joins/filters, member grain, no LIMIT.
REF_SQL = OLD_SQL.split("ORDER BY")[0]

SCHEMA = """
CREATE TABLE geographic_site (site_id TEXT, site_name TEXT, region TEXT, tier TEXT);
CREATE TABLE shared_risk_group (srlg_id TEXT, srlg_type TEXT, severity TEXT, span_id TEXT, srlg_name TEXT);
CREATE TABLE physical_resource_span (span_id TEXT, site_a_id TEXT, site_z_id TEXT, conduit_id TEXT,
                                     length_km REAL, is_active INT);
INSERT INTO geographic_site VALUES ('A','Lakelink Fiber A CO','Central','tier_1'),
                                   ('Z','Lakelink Fiber Z DC','Central','tier_2'),
                                   ('W','Lakelink Fiber W CO','West','tier_1'),
                                   ('E','Lakelink Fiber edge','Central','tier_3');
"""


def _db(spans, members):
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO physical_resource_span VALUES (?,?,?,?,?,?)", spans)
    db.executemany("INSERT INTO shared_risk_group VALUES (?,?,?,?,?)", members)
    db.row_factory = sqlite3.Row
    return db


def _run(db, sql, region="Central", **params):
    return [dict(r) for r in db.execute(sql.replace("TRUE", "1"), {"region": region, **params}).fetchall()]


def _summary(db, region="Central", sql=None):
    """Fold summary rows to per-conduit facts the same way the UI does."""
    out = {}
    for r in _run(db, sql or cs._SRLG_CONDUIT_SUMMARY_SQL, region):
        f = out.setdefault(r["conduit_id"], {"m": 0, "types": set(), "sev": None})
        f["m"] += r["srlg_count"]
        f["types"].add(r["srlg_type"])
        if r["max_severity"] and SEV_RANK[r["max_severity"]] > SEV_RANK.get(f["sev"], 0):
            f["sev"] = r["max_severity"]
    return out


def _list(db, conduit_id, region="Central", sql=None):
    return _run(db, sql or cs._CONDUIT_SRLGS_SQL, region, conduit_id=conduit_id)


def _facts(rows):
    """Per-conduit facts the UI derives (srlgByConduit, SRLG type letters, srlgSevByConduit)."""
    out = {}
    for r in rows:
        f = out.setdefault(r["conduit_id"], {"ids": set(), "types": set(), "sev": None})
        f["ids"].add(r["srlg_id"])
        f["types"].add(r["srlg_type"])
        s = r["severity"]
        if s and SEV_RANK.get(s, 0) > SEV_RANK.get(f["sev"], 0):
            f["sev"] = s
    return out


# --- small known answer -------------------------------------------------------------

SMALL_SPANS = [
    ("SPAN-1", "A", "Z", "CDT-1", 3.04, 1),
    ("SPAN-2", "A", "Z", "CDT-1", 2.0, 1),
    ("SPAN-3", "A", "Z", "CDT-1", 5.0, 1),
    ("SPAN-4", "Z", "A", "CDT-2", 7.0, 1),
    ("SPAN-5", "A", "Z", "CDT-1", 1.0, 0),   # inactive
    ("SPAN-6", "A", "E", "CDT-9", 1.0, 1),   # tier_3 endpoint
    ("SPAN-7", "W", "W", "CDT-W", 1.0, 1),   # other region
]
SMALL_MEMBERS = [
    ("SRLG-X", "bridge", "low", "SPAN-1", "Elm St bridge"),
    ("SRLG-X", "bridge", "critical", "SPAN-3", "Elm St bridge"),
    ("SRLG-X", "bridge", "medium", "SPAN-2", "Elm St bridge"),
    ("SRLG-X", "bridge", "high", "SPAN-4", "Elm St bridge"),
    ("SRLG-X", "bridge", "critical", "SPAN-5", "Elm St bridge"),  # inactive: ignored
    ("SRLG-N", "tunnel", None, "SPAN-1", "Tunnel 4"),
    ("SRLG-N", "tunnel", "low", "SPAN-2", "Tunnel 4"),
    ("SRLG-T3", "rail_crossing", "critical", "SPAN-6", "t3"),
    ("SRLG-W", "power_feed", "critical", "SPAN-7", "w"),
]


def test_v3_region_sql_byte_identical():
    # PM R98 / designer item 1: the freeze query is untouched; the new queries are separate.
    assert hashlib.sha256(cs._SRLG_BY_REGION_SQL.encode()).hexdigest().startswith("c24ace6c")


def test_conduit_list_one_row_per_srlg_with_worst_member():
    db = _db(SMALL_SPANS, SMALL_MEMBERS)
    rows = _list(db, "CDT-1")
    assert [r["srlg_id"] for r in rows] == ["SRLG-X", "SRLG-N"]
    x1, n1 = rows
    # Worst active member on CDT-1 is the critical SPAN-3 (inactive critical SPAN-5 is excluded).
    assert (x1["severity"], x1["span_id"], x1["member_span_count"], x1["span_length_km"]) == (
        "critical", "SPAN-3", 3, 5.0)
    # 'low' outranks a NULL severity.
    assert (n1["severity"], n1["span_id"], n1["member_span_count"]) == ("low", "SPAN-2", 2)
    assert x1["description"] == "Elm St bridge" and x1["site_a_name"] == "Lakelink Fiber A CO"
    # Same SRLG on CDT-2 is scoped to that conduit's own member.
    (x2,) = _list(db, "CDT-2")
    assert (x2["srlg_id"], x2["severity"], x2["span_id"], x2["member_span_count"]) == ("SRLG-X", "high", "SPAN-4", 1)
    assert _list(db, "CDT-9") == [] and _list(db, "CDT-W") == []  # tier_3 / other region


def test_conduit_list_columns_superset_of_old_contract():
    rows = _list(_db(SMALL_SPANS, SMALL_MEMBERS), "CDT-1")
    old_cols = list(_run(_db(SMALL_SPANS, SMALL_MEMBERS), OLD_SQL)[0].keys())
    assert list(rows[0].keys()) == old_cols + ["member_span_count"]


def test_summary_small_known_answer():
    rows = _run(_db(SMALL_SPANS, SMALL_MEMBERS), cs._SRLG_CONDUIT_SUMMARY_SQL)
    got = [(r["conduit_id"], r["srlg_type"], r["srlg_count"], r["member_span_count"], r["max_severity"]) for r in rows]
    assert got == [
        ("CDT-1", "bridge", 1, 3, "critical"),
        ("CDT-1", "tunnel", 1, 2, "low"),
        ("CDT-2", "bridge", 1, 1, "high"),
    ]


# --- large randomized: completeness + UI fact parity ---------------------------------

def _big(seed=108, conduits=40, srlgs=60, members=4000):
    rnd = random.Random(seed)
    spans = []
    for c in range(conduits):
        for k in range(8):
            spans.append((f"SPAN-{c:03d}-{k}", "A", "Z", f"CDT-{c:03d}", rnd.uniform(0.5, 20), int(rnd.random() > 0.05)))
    types = ["bridge", "tunnel", "rail_crossing", "power_feed", "shared_conduit", "central_office"]
    sevs = ["critical", "high", "medium", "low", None]
    ids = [(f"SRLG-{i:03d}", rnd.choice(types)) for i in range(srlgs)]
    seen, mem = set(), []
    while len(mem) < members:
        sid, typ = rnd.choice(ids)
        span = rnd.choice(spans)[0]
        if (sid, span) in seen:
            continue
        seen.add((sid, span))
        mem.append((sid, typ, rnd.choice(sevs), span, f"name {sid}"))
    return spans, mem


def test_fixture_reproduces_the_truncation_bug():
    spans, mem = _big()
    db = _db(spans, mem)
    ref = _run(db, REF_SQL)
    assert len(ref) > 500
    old = _run(db, cs._SRLG_BY_REGION_SQL)  # the (unchanged) v3 region list
    assert len(old) == 500
    assert _facts(old) != _facts(ref)  # it loses SRLGs on some conduits


def _known_answer_fixture():
    """Fixture equivalents of the designer's live answers: CDT-BB-0015 = 77, CDT-BB-0053 = 134."""
    rnd = random.Random(15053)
    spans, mem = [], []
    for cid, m in (("CDT-BB-0015", 77), ("CDT-BB-0053", 134)):
        for k in range(6):
            spans.append((f"SPAN-{cid}-{k}", "A", "Z", cid, 4.0, 1))
        for i in range(m):
            typ = ["bridge", "tunnel", "rail_crossing", "power_feed"][i % 4]
            for k in rnd.sample(range(6), 3):  # 3 member spans each -> 633 member rows
                mem.append((f"SRLG-{cid}-{i:03d}", typ, rnd.choice(["critical", "high", "medium", "low"]),
                            f"SPAN-{cid}-{k}", f"n{i}"))
    return _db(spans, mem)


def test_designer_known_answers_77_and_134():
    db = _known_answer_fixture()
    assert len(_run(db, REF_SQL)) == 3 * (77 + 134)
    s = _summary(db)
    assert s["CDT-BB-0015"]["m"] == 77 and s["CDT-BB-0053"]["m"] == 134
    assert len(_list(db, "CDT-BB-0015")) == 77 and len(_list(db, "CDT-BB-0053")) == 134
    # The old region list under-counts at least one of them.
    old = _facts(_run(db, cs._SRLG_BY_REGION_SQL))
    assert (len(old["CDT-BB-0015"]["ids"]), len(old["CDT-BB-0053"]["ids"])) != (77, 134)


@pytest.mark.parametrize("v4", [False, True])
def test_summary_and_lists_match_full_reference(v4):
    spans, mem = _big()
    db = _db(spans, mem)
    if v4:  # v4 candidate span table with identical rows: same answers
        db.execute("CREATE TABLE physical_resource_span_v4_candidate AS SELECT * FROM physical_resource_span")
    summ_sql = cs._SRLG_CONDUIT_SUMMARY_V4_SQL if v4 else cs._SRLG_CONDUIT_SUMMARY_SQL
    list_sql = cs._CONDUIT_SRLGS_V4_SQL if v4 else cs._CONDUIT_SRLGS_SQL
    ref = _run(db, REF_SQL)
    fr = _facts(ref)
    s = _summary(db, sql=summ_sql)
    assert sum(len(f["ids"]) for f in fr.values()) > 500  # more pairs than the old LIMIT
    assert set(s) == set(fr)
    for cid, f in fr.items():
        assert (s[cid]["m"], s[cid]["types"], s[cid]["sev"]) == (len(f["ids"]), f["types"], f["sev"]), cid
        lst = _list(db, cid, sql=list_sql)
        assert [r["srlg_id"] for r in lst] and {r["srlg_id"] for r in lst} == f["ids"], cid
        assert len(lst) == s[cid]["m"]
    summ_rows = _run(db, summ_sql)
    assert sum(r["member_span_count"] for r in summ_rows) == len(ref)


def test_order_is_deterministic_under_insert_order():
    spans, mem = _big()
    db_a = _db(spans, mem)
    rnd = random.Random(7)
    spans2, mem2 = spans[:], mem[:]
    rnd.shuffle(spans2)
    rnd.shuffle(mem2)
    db_b = _db(spans2, mem2)
    assert _run(db_a, cs._SRLG_CONDUIT_SUMMARY_SQL) == _run(db_b, cs._SRLG_CONDUIT_SUMMARY_SQL)
    for cid in ("CDT-000", "CDT-017", "CDT-039"):
        assert _list(db_a, cid) == _list(db_b, cid)


def test_v4_variants_swap_only_the_span_table():
    for v3, v4 in ((cs._SRLG_CONDUIT_SUMMARY_SQL, cs._SRLG_CONDUIT_SUMMARY_V4_SQL),
                   (cs._CONDUIT_SRLGS_SQL, cs._CONDUIT_SRLGS_V4_SQL)):
        assert v4.count("JOIN physical_resource_span_v4_candidate prs ON") == 1
        assert v4.replace("physical_resource_span_v4_candidate", "physical_resource_span") == v3


def test_limits_and_order():
    assert re.findall(r"LIMIT\s+(\d+)", cs._SRLG_CONDUIT_SUMMARY_SQL) == []  # summary: no LIMIT
    assert re.findall(r"LIMIT\s+(\d+)", cs._CONDUIT_SRLGS_SQL) == [str(cs.CONDUIT_SRLG_LIST_CAP)]
    assert "ORDER BY sev_rank, srlg_type, srlg_id, span_id" in cs._CONDUIT_SRLGS_SQL
    assert "ORDER BY conduit_id, max_severity_rank, srlg_type" in cs._SRLG_CONDUIT_SUMMARY_SQL
    for sql in (cs._SRLG_CONDUIT_SUMMARY_SQL, cs._CONDUIT_SRLGS_SQL):
        assert ":region" in sql
    assert ":conduit_id" in cs._CONDUIT_SRLGS_SQL


# --- service + router ----------------------------------------------------------------

class _Exec:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def __call__(self, sql, row_limit=None, params=None):
        self.calls.append((sql, row_limit, params))
        return self.rows


def _svc(rows):
    svc = object.__new__(cs.CatalogSqlService)
    svc._execute = _Exec(rows)
    return svc


@pytest.mark.parametrize("v4", [False, True])
def test_service_summary(v4):
    svc = _svc([{"conduit_id": "C", "srlg_type": "bridge", "srlg_count": "3", "member_span_count": "7",
                 "max_severity_rank": 1, "max_severity": "critical"}])
    rows = svc.get_srlg_conduit_summary("Central", v4=v4)
    sql, _limit, params = svc._execute.calls[0]
    assert sql is (cs._SRLG_CONDUIT_SUMMARY_V4_SQL if v4 else cs._SRLG_CONDUIT_SUMMARY_SQL)
    assert params == {"region": "Central"}
    assert rows == [{"conduit_id": "C", "srlg_type": "bridge", "srlg_count": 3, "member_span_count": 7,
                     "max_severity": "critical"}]
    assert _svc(None).get_srlg_conduit_summary("Central") is None


@pytest.mark.parametrize("v4", [False, True])
def test_service_conduit_list(v4):
    svc = _svc([{"span_length_km": "1.5", "member_span_count": "3"}, {"span_length_km": None}])
    rows = svc.get_conduit_srlgs("CDT-1", "Central", v4=v4)
    sql, limit, params = svc._execute.calls[0]
    assert sql is (cs._CONDUIT_SRLGS_V4_SQL if v4 else cs._CONDUIT_SRLGS_SQL)
    assert limit == cs.CONDUIT_SRLG_LIST_CAP and params == {"region": "Central", "conduit_id": "CDT-1"}
    assert rows[0]["member_span_count"] == 3 and rows[1]["member_span_count"] == 1
    assert rows[0]["span_length_km"] == 1.5 and rows[1]["span_length_km"] == 0.0


class _FakeCsql:
    is_available = True

    def __init__(self, result=None, boom=False):
        self.result, self.boom, self.calls = result, boom, []

    def _r(self, *a, **kw):
        self.calls.append((a, kw))
        if self.boom:
            raise RuntimeError("warehouse down")
        return self.result

    get_srlg_conduit_summary = _r
    get_conduit_srlgs = _r


@pytest.mark.parametrize("flag", [False, True])
def test_router_new_endpoints_live_and_flag(flag):
    pytest.importorskip("fastapi")
    from fastapi import Response

    from resilience_scorecard.backend import router as r

    cfg = SimpleNamespace(v4_kpis=flag)
    fake, resp = _FakeCsql([{"x": 1}]), Response()
    assert r.list_topology_srlg_summary(fake, resp, cfg, region="Central") == [{"x": 1}]
    assert resp.headers[r.DATA_SOURCE_HEADER] == "live"
    assert fake.calls[-1] == (("Central",), {"v4": flag})
    resp = Response()
    assert r.list_conduit_srlgs(fake, resp, cfg, conduit_id="CDT-1", region="Central") == [{"x": 1}]
    assert resp.headers[r.DATA_SOURCE_HEADER] == "live"
    assert fake.calls[-1] == (("CDT-1", "Central"), {"v4": flag})


@pytest.mark.parametrize("fake", [_FakeCsql(None), _FakeCsql(boom=True)])
def test_router_new_endpoints_unavailable_never_silent(fake):
    pytest.importorskip("fastapi")
    from fastapi import Response

    from resilience_scorecard.backend import router as r

    cfg = SimpleNamespace(v4_kpis=False)
    for call in (lambda resp: r.list_topology_srlg_summary(fake, resp, cfg, region="West"),
                 lambda resp: r.list_conduit_srlgs(fake, resp, cfg, conduit_id="CDT-1", region="West")):
        resp = Response()
        assert call(resp) == []
        assert resp.headers[r.DATA_SOURCE_HEADER] == "unavailable"


def test_router_routes_registered():
    pytest.importorskip("fastapi")
    from resilience_scorecard.backend import router as r

    paths = {getattr(rt, "path", "") for rt in r.router.routes}
    assert any(p.endswith("/topology/srlg-summary") for p in paths)
    assert any(p.endswith("/topology/conduits/{conduit_id}/srlgs") for p in paths)
    assert any(p.endswith("/topology/srlgs") for p in paths)  # kept for API compatibility


def test_summary_model():
    pytest.importorskip("pydantic")
    from resilience_scorecard.backend.models import SrlgConduitSummaryOut

    m = SrlgConduitSummaryOut(conduit_id="C", srlg_type="bridge", srlg_count=3, member_span_count=7,
                              max_severity="critical")
    assert m.srlg_count == 3 and m.max_severity == "critical"


def test_model_accepts_member_span_count():
    pytest.importorskip("pydantic")
    from resilience_scorecard.backend.models import SrlgMemberOut

    m = SrlgMemberOut(srlg_id="S", srlg_type="bridge", span_id="SPAN-1", site_a_id="A", site_z_id="Z",
                      member_span_count=4)
    assert m.member_span_count == 4
    assert SrlgMemberOut(srlg_id="S", srlg_type="bridge", span_id="SPAN-1", site_a_id="A",
                         site_z_id="Z").member_span_count == 1


# --- UI: pure module (Node) + topology.tsx wiring ------------------------------------

UI = os.path.join(APP_SRC, "resilience_scorecard", "ui")
LIB = os.path.join(UI, "lib", "srlg-summary.ts")
TOPO = os.path.join(UI, "routes", "topology.tsx")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not available")


def _node(expr):
    script = f"import * as m from {json.dumps(LIB)}; console.log(JSON.stringify({expr}));"
    out = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _src():
    with open(TOPO) as f:
        return f.read()


@needs_node
def test_build_summary_matches_sql_fold_and_old_first_row_rule():
    """UI fold of real summary SQL rows == full reference; primaryType == old first-row rule."""
    spans, mem = _big()
    db = _db(spans, mem)
    rows = _run(db, cs._SRLG_CONDUIT_SUMMARY_SQL)
    got = _node(f"[...m.buildSrlgSummary({json.dumps(rows)}).values()]")
    ref = _run(db, REF_SQL)
    fr = _facts(ref)
    # Old rule: first row in ORDER BY (severity rank, srlg_type) over that conduit's members.
    old_rank = {"critical": 1, "high": 2, "medium": 3}
    first = {}
    for r in sorted(ref, key=lambda r: (old_rank.get(r["severity"], 4), r["srlg_type"])):
        first.setdefault(r["conduit_id"], r["srlg_type"])
    assert {g["conduitId"] for g in got} == set(fr)
    for g in got:
        f = fr[g["conduitId"]]
        assert g["srlgCount"] == len(f["ids"]) and set(g["types"]) == f["types"] and g["maxSeverity"] == f["sev"]
        assert g["primaryType"] == g["types"][0]
        if f["sev"] != "low":  # old rank lumped low and NULL together; compare where it was well-defined
            assert g["primaryType"] == first[g["conduitId"]], g["conduitId"]


@needs_node
def test_copy_and_disclosure_helpers():
    assert _node("m.srlgPanelHeading(134)") == "Shared Risk Groups (134)"
    assert _node("m.srlgShowingNote(25, 134)") == "Showing 25 of 134 shared risk groups"
    assert _node("m.srlgShowingNote(134, 134)") is None
    assert _node("m.srlgShowAllLabel(1340)") == "Show all 1,340"
    assert _node("m.PANEL_SRLG_INITIAL") == 25
    assert _node("[m.canShowAllSrlgs(26, false), m.canShowAllSrlgs(25, false), m.canShowAllSrlgs(26, true)]") == [True, False, False]
    assert _node("m.visibleSrlgRows([...Array(30).keys()], false).length") == 25
    assert _node("m.visibleSrlgRows([...Array(30).keys()], true).length") == 30
    # never an empty or zero section: live-but-empty is unavailable
    assert _node("[m.panelSrlgListMode(null, 0), m.panelSrlgListMode('live', 0), m.panelSrlgListMode('live', 2), m.panelSrlgListMode('unavailable', 0), m.panelSrlgListMode('auth_expired', 0)]") == [
        "loading", "unavailable", "list", "unavailable", "unavailable"]
    assert _node("m.conduitSrlgsUrl('CDT-BB/1', 'Central West')") == "/api/topology/conduits/CDT-BB%2F1/srlgs?region=Central%20West"
    assert _node("m.srlgSummaryUrl('West')") == "/api/topology/srlg-summary?region=West"


def test_topology_no_longer_reads_the_capped_region_list():
    src = _src()
    assert "/api/topology/srlgs" not in src
    assert "srlgs.filter(" not in src and "srlgs.find(" not in src
    assert "fetchWithState<SrlgConduitTypeRow[]>(srlgSummaryUrl(selectedRegion))" in src
    assert "srlgSummary={srlgSummary}" in src
    assert "srlgSummary={srlgSummary.get(selectedConduit.conduit_id)}" in src


def test_map_badge_ring_and_label_come_from_summary():
    src = _src()
    assert "const srlgByConduit = srlgSummary;" in src
    assert "maxSrlgSeverity([{ severity: s.maxSeverity }])" in src
    assert "srlgSummary.get(c.conduit_id)?.primaryType" in src
    assert "(srlgSummary.get(c.conduit_id)?.types ?? []).map(" in src
    assert "const extra = summary.types.length - 1;" in src


def test_panel_heading_true_m_lazy_list_and_disclosure():
    src = _src()
    i = src.index("function EdgeDetailPanel(")
    panel = src[i:src.index("\n}\n", i)]
    assert "const srlgTotal = srlgSummary?.srlgCount ?? 0;" in panel
    assert "{srlgPanelHeading(srlgTotal)}" in panel and "srlgGroups.length})" not in panel
    assert "fetchWithState<SrlgMember[]>(conduitSrlgsUrl(conduit.conduit_id, region))" in panel
    assert "{SRLG_LIST_LOADING_MSG}" in panel
    assert "{srlgUnavailableMsg(conduit.conduit_id, srlgListState)}" in panel
    assert "aria-expanded={srlgExpanded}" in panel and "aria-controls={srlgListId}" in panel
    assert 'className="site-cap-toggle"' in panel and 'className="site-cap-note"' in panel  # 44px / 12px iron
    assert "srlgShowingNote(srlgRows.length, srlgTotal)" in panel


def test_panel_css_rules_present():
    with open(os.path.join(UI, "styles", "lakelink-theme.css")) as f:
        css = f.read()
    assert re.search(r"(?m)^\.panel-srlg-status \{[^}]*color: var\(--lf-iron\)", css)
    assert re.search(r"(?m)^\.site-cap-toggle \{[^}]*min-height: 44px", css)


def test_no_brand_leak():
    for p in (LIB, TOPO, __file__, os.path.join(APP_SRC, "resilience_scorecard", "backend", "router.py"),
              os.path.join(APP_SRC, "resilience_scorecard", "backend", "services", "catalog_sql.py")):
        with open(p) as f:
            assert not re.search("lu" + "men", f.read(), re.I), p
