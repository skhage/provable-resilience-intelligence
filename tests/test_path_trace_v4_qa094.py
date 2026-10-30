"""BUG-QA-094: v4 /topology path trace remaps v3 backbone hops onto CDT-BBR-* route conduits.

With PRI_V4_KPIS=true the topology edges come from conduit_v4, where the 90 v3 BB-placeholder
conduits are INVENTORY_ONLY. service_path is still v3, so a traced BB hop used to pin the
placeholder edge with 'Inventory only: no span geometry' and no backbone caveat.

Known-answer approach: the real SQL constants run against a tiny SQLite fixture (both use
:name binding), then the UI edge rules (isInventoryOnly / hasBackboneSpans) are applied in
Python to the result. The v3 query on the same fixture is the negative control (shows the bug).
Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import hashlib
import os
import re
import sqlite3
import sys
from types import SimpleNamespace

import pytest

APP_SRC = os.path.join(os.path.dirname(__file__), "..", "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

# sha256 of _SERVICE_PATH_TRACE_SQL at d38bb04 (pre-fix). Flag-off UI must stay byte-identical.
V3_PATH_TRACE_SHA256 = "7e8251de2c00cf344a5366bdd6b51d1084244bcce8ce75438aad0a8d29a91a38"


def _select_aliases(sql: str) -> list[str]:
    body = sql.split("SELECT", 1)[1].split("\nFROM ", 1)[0]
    body = "\n".join(ln.split("--", 1)[0] for ln in body.splitlines())
    out = []
    for item in re.split(r",\s*\n", body.strip()):
        item = item.strip().rstrip(",")
        m = re.search(r"\bAS\s+(\w+)\s*$", item)
        out.append(m.group(1) if m else item.split(".")[-1])
    return out


# --- static contract -------------------------------------------------------------

def test_v3_path_trace_sql_byte_identical():
    assert hashlib.sha256(cs._SERVICE_PATH_TRACE_SQL.encode()).hexdigest() == V3_PATH_TRACE_SHA256
    assert "_v4_candidate" not in cs._SERVICE_PATH_TRACE_SQL


def test_v4_sql_same_contract_and_reads_shadow_tables():
    v3, v4 = cs._SERVICE_PATH_TRACE_SQL, cs._SERVICE_PATH_TRACE_V4_SQL
    assert _select_aliases(v4) == _select_aliases(v3)
    assert "FROM physical_resource_span_v4_candidate" in v4
    assert "parent_route_id" in v4
    assert "LEFT JOIN physical_resource_conduit_v4_candidate prc" in v4
    assert "WHERE sp.service_id = :service_id" in v4  # bound, never inlined (BUG-QA-077)
    assert v4.strip().endswith("ORDER BY sp.path_type, sp.hop_sequence")


# --- known-answer fixture --------------------------------------------------------

_DDL = """
CREATE TABLE geographic_site (site_id TEXT, site_name TEXT, region TEXT, tier TEXT, is_active BOOLEAN);
CREATE TABLE physical_resource_conduit (conduit_id TEXT, conduit_name TEXT, corridor TEXT, conduit_type TEXT,
  length_km REAL, site_a_id TEXT, site_z_id TEXT, is_active BOOLEAN);
CREATE TABLE physical_resource_conduit_v4_candidate (conduit_id TEXT, conduit_name TEXT, corridor TEXT,
  conduit_type TEXT, length_km REAL, site_a_id TEXT, site_z_id TEXT, is_active BOOLEAN, span_coverage_class TEXT);
CREATE TABLE physical_resource_span (span_id TEXT, conduit_id TEXT, site_a_id TEXT, site_z_id TEXT,
  length_km REAL, fiber_type TEXT, fiber_count INT, is_active BOOLEAN);
CREATE TABLE physical_resource_span_v4_candidate (span_id TEXT, conduit_id TEXT, site_a_id TEXT, site_z_id TEXT,
  length_km REAL, fiber_type TEXT, fiber_count INT, is_active BOOLEAN, parent_route_id TEXT);
CREATE TABLE service_path (service_id TEXT, hop_sequence INT, span_id TEXT, path_type TEXT);
"""

_SITES = [(f"S{i}", f"Site {i}", "Central", "tier_1", 1) for i in range(1, 5)]
# v3: CDT-BB-0362 is a BB placeholder (carries only BB-1); CDT-MT-2 is mixed (SPAN-2 + BB-2).
_V3_CONDUITS = [
    ("CDT-MT-1", "MT1", "I-35", "underground", 10.0, "S2", "S3", 1),
    ("CDT-BB-0362", "BB placeholder", "BB", "placeholder", 50.0, "S1", "S2", 1),
    ("CDT-MT-2", "MT2", "I-70", "aerial", 12.0, "S3", "S4", 1),
]
_V4_CONDUITS = [
    ("CDT-MT-1", "MT1", "I-35", "underground", 10.0, "S2", "S3", 1, "REAL_SEGMENTED"),
    ("CDT-BB-0362", "BB placeholder", "BB", "placeholder", 50.0, "S1", "S2", 1, "INVENTORY_ONLY"),
    ("CDT-MT-2", "MT2", "I-70", "aerial", 12.0, "S3", "S4", 1, "REAL_SEGMENTED"),
    ("CDT-BBR-1", "BB route 1", "BB", "underground", 48.4, "S1", "S2", 1, "BB_SEGMENTED"),
    ("CDT-BBR-2", "BB route 2", "BB", "underground", 11.6, "S3", "S4", 1, "BB_SEGMENTED"),
    ("CDT-BBR-X", "retired", "BB", "underground", 1.0, "S1", "S2", 1, "BB_SEGMENTED"),
]
_V3_SPANS = [
    ("SPAN-1", "CDT-MT-1", "S2", "S3", 10.0, "SMF", 144, 1),
    ("BB-1", "CDT-BB-0362", "S1", "S2", 48.4, "SMF", 288, 1),
    ("BB-2", "CDT-MT-2", "S3", "S4", 11.6, "SMF", 288, 1),
    ("SPAN-2", "CDT-MT-2", "S3", "S4", 12.0, "SMF", 96, 1),
]
_V4_SPANS = [
    ("SPAN-1", "CDT-MT-1", "S2", "S3", 10.0, "SMF", 144, 1, None),
    ("SPAN-2", "CDT-MT-2", "S3", "S4", 12.0, "SMF", 96, 1, None),
    ("BBS-1-1", "CDT-BBR-1", "S1", "SX", 20.0, "SMF", 288, 1, "BB-1"),
    ("BBS-1-2", "CDT-BBR-1", "SX", "S2", 28.4, "SMF", 288, 1, "BB-1"),
    ("BBS-2-1", "CDT-BBR-2", "S3", "S4", 11.6, "SMF", 288, 1, "BB-2"),
    # inactive child pointing at another route: must be ignored (is_active filter)
    ("BBS-9", "CDT-BBR-X", "S1", "S2", 1.0, "SMF", 288, 0, "BB-1"),
]
_PATH = [
    ("SVC-A", 1, "SPAN-1", "working"),
    ("SVC-A", 2, "BB-1", "working"),
    ("SVC-A", 3, "BB-2", "working"),
    ("SVC-A", 1, "SPAN-2", "protect"),
]


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(_DDL)
    con.executemany("INSERT INTO geographic_site VALUES (?,?,?,?,?)", _SITES)
    con.executemany("INSERT INTO physical_resource_conduit VALUES (?,?,?,?,?,?,?,?)", _V3_CONDUITS)
    con.executemany("INSERT INTO physical_resource_conduit_v4_candidate VALUES (?,?,?,?,?,?,?,?,?)", _V4_CONDUITS)
    con.executemany("INSERT INTO physical_resource_span VALUES (?,?,?,?,?,?,?,?)", _V3_SPANS)
    con.executemany("INSERT INTO physical_resource_span_v4_candidate VALUES (?,?,?,?,?,?,?,?,?)", _V4_SPANS)
    con.executemany("INSERT INTO service_path VALUES (?,?,?,?)", _PATH)
    yield con
    con.close()


def _run(con, sql, **params):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def _hops(con, sql):
    return [(h["path_type"], h["hop_index"], h["span_id"], h["conduit_id"])
            for h in _run(con, sql, service_id="SVC-A")]


def test_v4_remaps_bb_hops_known_answer(db):
    assert _hops(db, cs._SERVICE_PATH_TRACE_V4_SQL) == [
        ("protect", 1, "SPAN-2", "CDT-MT-2"),
        ("working", 1, "SPAN-1", "CDT-MT-1"),
        ("working", 2, "BB-1", "CDT-BBR-1"),   # placeholder -> route (2 child spans, no fan-out)
        ("working", 3, "BB-2", "CDT-BBR-2"),   # BB span in a mixed v3 conduit -> route
    ]
    bb1 = [h for h in _run(db, cs._SERVICE_PATH_TRACE_V4_SQL, service_id="SVC-A") if h["span_id"] == "BB-1"][0]
    # conduit metadata follows the remapped v4 conduit; span geometry stays the traced v3 span
    assert (bb1["conduit_type"], bb1["conduit_length_km"]) == ("underground", 48.4)
    assert (bb1["span_site_a_id"], bb1["span_site_z_id"], bb1["span_length_km"]) == ("S1", "S2", 48.4)


def test_v3_query_unchanged_on_fixture(db):
    # Negative control: the frozen v3 query still points BB-1 at the placeholder.
    assert _hops(db, cs._SERVICE_PATH_TRACE_SQL) == [
        ("protect", 1, "SPAN-2", "CDT-MT-2"),
        ("working", 1, "SPAN-1", "CDT-MT-1"),
        ("working", 2, "BB-1", "CDT-BB-0362"),
        ("working", 3, "BB-2", "CDT-MT-2"),
    ]


def _on_path_edges(con, path_sql):
    """Mirror topology.tsx: isOnPath = pathConduitIds.has(id); invOnly = isInventoryOnly(c);
    BB caveat = bbCoverage 'partial' && hasBackboneSpans(c) (backbone_span_count > 0)."""
    edges = _run(con, cs._TOPOLOGY_CONDUITS_V4_SQL, region="Central")
    ids = {h["conduit_id"] for h in _run(con, path_sql, service_id="SVC-A") if h["conduit_id"]}
    return {e["conduit_id"]: {"inventory_text": e["span_coverage_class"] == "INVENTORY_ONLY",
                              "bb_caveat": int(e["backbone_span_count"] or 0) > 0}
            for e in edges if e["conduit_id"] in ids}


def test_acceptance_no_inventory_text_on_path_and_bb_caveat_kept(db):
    on_path = _on_path_edges(db, cs._SERVICE_PATH_TRACE_V4_SQL)
    assert set(on_path) == {"CDT-MT-1", "CDT-MT-2", "CDT-BBR-1", "CDT-BBR-2"}
    assert not any(e["inventory_text"] for e in on_path.values())
    assert on_path["CDT-BBR-1"]["bb_caveat"] and on_path["CDT-BBR-2"]["bb_caveat"]
    assert "CDT-BB-0362" not in on_path and "CDT-BBR-X" not in on_path


def test_bug_reproduces_with_v3_trace_on_v4_edges(db):
    on_path = _on_path_edges(db, cs._SERVICE_PATH_TRACE_SQL)
    assert on_path["CDT-BB-0362"] == {"inventory_text": True, "bb_caveat": False}
    assert "CDT-BBR-1" not in on_path


# --- service + router wiring -----------------------------------------------------

def test_service_selects_sql_by_flag():
    svc = object.__new__(cs.CatalogSqlService)
    seen = []
    svc._execute = lambda sql, row_limit=None, params=None: (seen.append((sql, row_limit, params)) or [
        {"hop_index": "2", "span_length_km": "1.5", "conduit_length_km": None, "strand_count": None}])
    rows = svc.get_service_path_trace("SVC-A", v4=True)
    svc.get_service_path_trace("SVC-A")
    assert seen[0] == (cs._SERVICE_PATH_TRACE_V4_SQL, 500, {"service_id": "SVC-A"})
    assert seen[1] == (cs._SERVICE_PATH_TRACE_SQL, 500, {"service_id": "SVC-A"})
    assert rows[0]["hop_index"] == 2 and rows[0]["conduit_length_km"] == 0.0 and rows[0]["strand_count"] == 0


class _FakeCsql:
    is_available = True

    def __init__(self):
        self.calls = []

    def get_service_path_trace(self, service_id, **kw):
        self.calls.append((service_id, kw))
        return [{"conduit_id": "CDT-BBR-1"}]


@pytest.mark.parametrize("flag,expected_kw", [(False, {}), (True, {"v4": True})])
def test_router_passes_flag(flag, expected_kw):
    pytest.importorskip("fastapi")
    from fastapi import Response

    from resilience_scorecard.backend import router as rt

    fake, resp = _FakeCsql(), Response()
    out = rt.get_service_path_trace("SVC-A", fake, resp, SimpleNamespace(v4_kpis=flag))
    assert out == [{"conduit_id": "CDT-BBR-1"}]
    assert fake.calls == [("SVC-A", expected_kw)]
    assert resp.headers[rt.DATA_SOURCE_HEADER] == "live"
