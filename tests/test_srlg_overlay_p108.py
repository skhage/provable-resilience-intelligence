"""P108-APP-SRLG-OVERLAY-LIMIT-TRUNCATION: /api/topology/srlgs returns one row per
(conduit_id, srlg_id) and is complete. Before, it returned one row per span member with LIMIT 500
and a tied ORDER BY, so every region was cut (Central 3,382 / West 3,455 / East 4,722 /
Southeast 2,114 member rows) and which SRLGs reached the conduit badges and panel was arbitrary.

Known answer: the real SQL constants run on SQLite fixtures. The reference is the full member-level
join with no LIMIT; the UI's per-conduit facts (srlg_id set, srlg_type set, worst severity) must
match it exactly. Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import os
import random
import re
import sqlite3
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


def _run(db, sql, region="Central"):
    return [dict(r) for r in db.execute(sql.replace("TRUE", "1"), {"region": region}).fetchall()]


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


def test_one_row_per_conduit_srlg_with_worst_member():
    rows = _run(_db(SMALL_SPANS, SMALL_MEMBERS), cs._SRLG_BY_REGION_SQL)
    key = [(r["conduit_id"], r["srlg_id"]) for r in rows]
    assert key == [("CDT-1", "SRLG-X"), ("CDT-2", "SRLG-X"), ("CDT-1", "SRLG-N")]
    x1, x2, n1 = rows
    # Worst active member on CDT-1 is the critical SPAN-3 (inactive critical SPAN-5 is excluded).
    assert (x1["severity"], x1["span_id"], x1["member_span_count"], x1["span_length_km"]) == (
        "critical", "SPAN-3", 3, 5.0)
    assert (x2["severity"], x2["span_id"], x2["member_span_count"]) == ("high", "SPAN-4", 1)
    # 'low' outranks a NULL severity.
    assert (n1["severity"], n1["span_id"], n1["member_span_count"]) == ("low", "SPAN-2", 2)
    assert x1["description"] == "Elm St bridge" and x1["site_a_name"] == "Lakelink Fiber A CO"


def test_output_columns_superset_of_old_contract():
    rows = _run(_db(SMALL_SPANS, SMALL_MEMBERS), cs._SRLG_BY_REGION_SQL)
    old_cols = list(_run(_db(SMALL_SPANS, SMALL_MEMBERS), OLD_SQL)[0].keys())
    assert list(rows[0].keys()) == old_cols + ["member_span_count"]
    assert "sev_rank" not in rows[0] and "rn" not in rows[0]


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
    assert len(_run(db, OLD_SQL)) == 500
    assert _facts(_run(db, OLD_SQL)) != _facts(ref)  # old query loses SRLGs on some conduits


def test_complete_and_facts_match_full_reference():
    spans, mem = _big()
    db = _db(spans, mem)
    ref = _run(db, REF_SQL)
    rows = _run(db, cs._SRLG_BY_REGION_SQL)
    pairs = {(r["conduit_id"], r["srlg_id"]) for r in ref}
    assert len(pairs) > 500  # more pairs than the old LIMIT
    assert len(rows) == len(pairs)
    assert {(r["conduit_id"], r["srlg_id"]) for r in rows} == pairs
    assert _facts(rows) == _facts(ref)
    # member_span_count sums back to the member rows.
    assert sum(r["member_span_count"] for r in rows) == len(ref)


def test_order_is_deterministic_under_insert_order():
    spans, mem = _big()
    a = _run(_db(spans, mem), cs._SRLG_BY_REGION_SQL)
    rnd = random.Random(7)
    spans2, mem2 = spans[:], mem[:]
    rnd.shuffle(spans2)
    rnd.shuffle(mem2)
    b = _run(_db(spans2, mem2), cs._SRLG_BY_REGION_SQL)
    assert a == b


def test_first_row_per_conduit_is_worst_severity():
    """The map badge uses srlgs.find(conduit) as the representative; it must carry the max severity."""
    spans, mem = _big()
    rows = _run(_db(spans, mem), cs._SRLG_BY_REGION_SQL)
    facts, first = _facts(rows), {}
    for r in rows:
        first.setdefault(r["conduit_id"], r)
    for cid, r in first.items():
        assert r["severity"] == facts[cid]["sev"], cid


def test_v4_variant_same_grain():
    v4 = cs._SRLG_BY_REGION_V4_SQL
    assert "PARTITION BY m.conduit_id, m.srlg_id" in v4
    assert v4.replace("physical_resource_span_v4_candidate", "physical_resource_span") == cs._SRLG_BY_REGION_SQL


def test_limit_is_the_shared_cap():
    sql = cs._SRLG_BY_REGION_SQL
    assert sql.rstrip().endswith(f"LIMIT {cs.SRLG_REGION_ROW_CAP}")
    assert re.findall(r"LIMIT\s+(\d+)", sql) == [str(cs.SRLG_REGION_ROW_CAP)]
    assert "ORDER BY sev_rank, srlg_type, conduit_id, srlg_id" in sql


# --- service + router ----------------------------------------------------------------

def test_service_coerces_member_span_count_and_cap():
    svc = object.__new__(cs.CatalogSqlService)
    seen = {}

    def _exec(sql, row_limit=None, params=None):
        seen["row_limit"] = row_limit
        return [{"span_length_km": "1.5", "member_span_count": "3"}, {"span_length_km": None}]

    svc._execute = _exec
    rows = svc.get_srlgs_by_region("Central")
    assert seen["row_limit"] == cs.SRLG_REGION_ROW_CAP
    assert rows[0]["member_span_count"] == 3 and rows[1]["member_span_count"] == 1


# getattr keeps collection working on pre-P108 sources (negative check); the cap test pins the value.
@pytest.mark.parametrize("n,flag", [(3, None), (getattr(cs, "SRLG_REGION_ROW_CAP", 5000), "true")])
def test_router_flags_capped_result(n, flag):
    pytest.importorskip("fastapi")
    from fastapi import Response

    from resilience_scorecard.backend import router as r

    class _Fake:
        is_available = True

        def get_srlgs_by_region(self, region, **kw):
            return [{}] * n

    resp = Response()
    out = r.list_topology_srlgs(_Fake(), resp, SimpleNamespace(v4_kpis=False), region="Central")
    assert len(out) == n
    assert resp.headers.get(r.TRUNCATED_HEADER) == flag
    assert resp.headers[r.DATA_SOURCE_HEADER] == "live"


def test_model_accepts_member_span_count():
    pytest.importorskip("pydantic")
    from resilience_scorecard.backend.models import SrlgMemberOut

    m = SrlgMemberOut(srlg_id="S", srlg_type="bridge", span_id="SPAN-1", site_a_id="A", site_z_id="Z",
                      member_span_count=4)
    assert m.member_span_count == 4
    assert SrlgMemberOut(srlg_id="S", srlg_type="bridge", span_id="SPAN-1", site_a_id="A",
                         site_z_id="Z").member_span_count == 1
