"""BUG-DW-114: the per-conduit BB SRLG caveat follows UNCOVERED backbone spans.

After BUG-QA-083, global 'partial' also covers a partial backfill where some BB/BBS spans have
SRLG rows. The conduit caveat / caveat-only panel / suppressed badge must key off the conduit's
own uncovered backbone spans (backbone_uncovered_span_count, v4 API), not all backbone spans.

Known answers: (1) the real v4 SQL constant runs on a SQLite fixture; (2) the real .ts helpers run
under node --experimental-strip-types. Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
PKG = os.path.join(APP_SRC, "resilience_scorecard")
TS = os.path.join(PKG, "ui", "lib", "bb-srlg-disclosure.ts")
TOPO = os.path.join(PKG, "ui", "routes", "topology.tsx")
CORE = os.path.join(PKG, "backend", "core.py")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

# sha256 of _TOPOLOGY_CONDUITS_SQL at 62f712a (pre-fix). The flag-off freeze query is untouched.
V3_CONDUITS_SHA256 = "fe835516814554a77b466ce9210d5e487e743ec7aaa554fb6420ca743a652d81"

BB_EDGE_CAVEAT = "Backbone span: shared-risk data not available"


# --- static contract ---------------------------------------------------------------

def test_v3_conduits_sql_byte_identical():
    assert hashlib.sha256(cs._TOPOLOGY_CONDUITS_SQL.encode()).hexdigest() == V3_CONDUITS_SHA256
    assert "backbone_uncovered_span_count" not in cs._TOPOLOGY_CONDUITS_SQL


def test_v4_sql_uses_same_anti_join_as_global_coverage():
    v4 = cs._TOPOLOGY_CONDUITS_V4_SQL
    assert "AS backbone_uncovered_span_count" in v4
    anti = "SELECT DISTINCT span_id FROM shared_risk_group WHERE span_id LIKE 'BB%'"
    assert anti in v4 and anti in cs._BB_SRLG_COVERAGE_SQL
    assert "FROM physical_resource_span_v4_candidate s" in v4


def test_model_field_optional_default_none():
    from resilience_scorecard.backend.models import TopologyConduitOut
    c = TopologyConduitOut(conduit_id="X", conduit_type="underground", length_km=1,
                           site_a_id="A", site_z_id="Z", span_count=1)
    assert c.backbone_uncovered_span_count is None
    c2 = TopologyConduitOut(conduit_id="X", conduit_type="underground", length_km=1, site_a_id="A",
                            site_z_id="Z", span_count=2, backbone_span_count=2,
                            backbone_uncovered_span_count=0)
    assert c2.backbone_uncovered_span_count == 0


def test_core_comment_matches_qa083_rule():
    src = open(CORE).read()
    assert "any BB-*/BBS-* span rows -> complete" not in src
    assert "0 BB spans lack an" in src


def test_topology_reads_backbone_only_via_helpers():
    src = open(TOPO).read()
    body = re.sub(r"^\s*(/\*\*|\*).*$", "", src, flags=re.M)  # drop type doc comments
    reads = re.findall(r"\.backbone_(?:uncovered_)?span_count", body)
    assert reads == [], f"route reads backbone counts directly: {reads}"
    for h in ("hasBackboneSpans(", "isBackboneOnly(", "panelSrlgMode("):
        assert h in src


def test_no_brand_leak():
    for p in (TS, TOPO, CORE, os.path.join(PKG, "backend", "services", "catalog_sql.py"),
              os.path.join(PKG, "backend", "models.py"), __file__):
        txt = open(p).read().lower()
        assert txt.count("lu" + "men") == 0, p


# --- SQL known answer ----------------------------------------------------------------

_DDL = """
CREATE TABLE geographic_site (site_id TEXT, region TEXT, tier TEXT);
CREATE TABLE physical_resource_conduit_v4_candidate (conduit_id TEXT, conduit_name TEXT, corridor TEXT,
  conduit_type TEXT, length_km REAL, site_a_id TEXT, site_z_id TEXT, is_active BOOLEAN, span_coverage_class TEXT);
CREATE TABLE physical_resource_span_v4_candidate (span_id TEXT, conduit_id TEXT, is_active BOOLEAN);
CREATE TABLE shared_risk_group (srlg_id TEXT, span_id TEXT);
"""
_CONDUITS = [  # id, length (ORDER BY length DESC)
    ("C-COV", 50.0),    # 2 BB spans, both covered
    ("C-HALF", 40.0),   # 2 BB spans, 1 covered
    ("C-UNC", 30.0),    # 2 BB spans, none covered (today's live state)
    ("C-MIX", 20.0),    # 1 metro + 1 uncovered BB
    ("C-MT", 10.0),     # metro only
]
_SPANS = [
    ("BBS-1", "C-COV", 1), ("BBS-2", "C-COV", 1),
    ("BBS-3", "C-HALF", 1), ("BBS-4", "C-HALF", 1),
    ("BB-5", "C-UNC", 1), ("BB-6", "C-UNC", 1),
    ("SPAN-7", "C-MIX", 1), ("BB-8", "C-MIX", 1),
    ("SPAN-9", "C-MT", 1),
    ("BB-10", "C-MT", 0),  # inactive uncovered BB span: ignored
]
_SRLG = [
    ("G1", "BBS-1"), ("G2", "BBS-1"),  # two groups on one span: DISTINCT, no double count
    ("G3", "BBS-2"), ("G4", "BBS-3"), ("G5", "SPAN-7"),
]


@pytest.fixture()
def rows():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(_DDL)
    con.executemany("INSERT INTO geographic_site VALUES (?,?,?)",
                    [("A", "Central", "tier_1"), ("Z", "Central", "tier_2")])
    con.executemany("INSERT INTO physical_resource_conduit_v4_candidate VALUES (?,?,?,?,?,?,?,?,?)",
                    [(cid, cid, None, "underground", km, "A", "Z", 1, "REAL_SEGMENTED") for cid, km in _CONDUITS])
    con.executemany("INSERT INTO physical_resource_span_v4_candidate VALUES (?,?,?)", _SPANS)
    con.executemany("INSERT INTO shared_risk_group VALUES (?,?)", _SRLG)
    out = {r["conduit_id"]: dict(r) for r in con.execute(cs._TOPOLOGY_CONDUITS_V4_SQL, {"region": "Central"})}
    con.close()
    return out


def test_v4_sql_per_conduit_uncovered_known_answer(rows):
    got = {k: (v["span_count"], v["backbone_span_count"], v["backbone_uncovered_span_count"])
           for k, v in rows.items()}
    assert got == {
        "C-COV": (2, 2, 0),
        "C-HALF": (2, 2, 1),
        "C-UNC": (2, 2, 2),
        "C-MIX": (2, 1, 1),
        "C-MT": (1, 0, 0),
    }


def test_get_topology_conduits_coerces_uncovered_only_when_present():
    svc = object.__new__(cs.CatalogSqlService)
    v4row = {"span_count": "2", "backbone_span_count": "2", "backbone_uncovered_span_count": "0", "length_km": "1"}
    v3row = {"span_count": "2", "backbone_span_count": "2", "length_km": "1"}
    svc._execute = lambda sql, params=None, **k: [dict(v4row)] if "uncovered" in sql else [dict(v3row)]
    assert svc.get_topology_conduits("Central", v4=True)[0]["backbone_uncovered_span_count"] == 0
    assert "backbone_uncovered_span_count" not in svc.get_topology_conduits("Central")[0]


# --- UI helpers known answer (real .ts under node) ------------------------------------

def _node(expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(TS, os.path.join(d, "m.ts"))
    with open(os.path.join(d, "main.ts"), "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", os.path.join(d, "main.ts")],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


_EDGE_FN = ("((cov, c) => { const bb = cov === 'partial' && M.hasBackboneSpans(c); return {"
            "mode: M.panelSrlgMode(cov, c), name: M.conduitEdgeName('Conduit X', bb), "
            "noBadge: cov === 'partial' && M.isBackboneOnly(c), desc: M.conduitEdgeDescribedBy('X', bb)}; })")


def _edge(cov, c):
    return _node(f"{_EDGE_FN}({json.dumps(cov)}, {json.dumps(c)})")


def test_a_covered_backbone_conduit_under_partial_shows_list_no_caveat():
    e = _edge("partial", {"span_count": 2, "backbone_span_count": 2, "backbone_uncovered_span_count": 0})
    assert e["mode"] in ("list", "qualified")
    assert BB_EDGE_CAVEAT not in e["name"]
    assert e["noBadge"] is False and e["desc"] == "conduit-desc-X"


def test_b_one_uncovered_backbone_span_keeps_caveat():
    e = _edge("partial", {"span_count": 2, "backbone_span_count": 2, "backbone_uncovered_span_count": 1})
    assert BB_EDGE_CAVEAT in e["name"] and e["mode"] == "qualified" and e["noBadge"] is False
    e2 = _edge("partial", {"span_count": 2, "backbone_span_count": 2, "backbone_uncovered_span_count": 2})
    assert BB_EDGE_CAVEAT in e2["name"] and e2["mode"] == "caveat-only" and e2["noBadge"] is True


def test_c_flag_off_v3_strings_unchanged():
    for c in ({"span_count": 2, "backbone_span_count": 2},
              {"span_count": 2, "backbone_span_count": 2, "backbone_uncovered_span_count": 0},
              {"span_count": 1}):
        e = _edge(None, c)
        assert e == {"mode": "list", "name": "Conduit X. Press Enter for details.",
                     "noBadge": False, "desc": "conduit-desc-X"}


def _old_rule(cov, c):
    """Pre-DW-114 rule (keys on all backbone spans), mirrored from 62f712a."""
    bb = c.get("backbone_span_count") or 0
    has, only = bb > 0, bb > 0 and bb >= c["span_count"]
    mode = "list" if cov != "partial" else ("caveat-only" if only else ("qualified" if has else "list"))
    part = cov == "partial" and has
    return {"mode": mode, "name": f"Conduit X.{' ' + BB_EDGE_CAVEAT + '.' if part else ''} Press Enter for details.",
            "noBadge": cov == "partial" and only, "desc": None if part else "conduit-desc-X"}


def test_d_live_state_all_uncovered_identical_to_today():
    # Live v3/v4 today: 92/92 BB spans uncovered, so uncovered == backbone_span_count everywhere.
    # Also covers the field being absent (v3 freeze query).
    cases = [{"span_count": n, "backbone_span_count": b, "backbone_uncovered_span_count": b}
             for n in (1, 2, 3) for b in range(0, n + 1)]
    cases += [{"span_count": n, "backbone_span_count": b} for n in (1, 2) for b in range(0, n + 1)]
    got = _node("[" + ",".join(f"{_EDGE_FN}('partial', {json.dumps(c)})" for c in cases) + "]")
    for c, g in zip(cases, got):
        exp = _old_rule("partial", c)
        g = {**g, "desc": g.get("desc")}
        assert g == exp, c
