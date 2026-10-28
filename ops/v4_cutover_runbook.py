"""Lakelink Fiber Provable Resilience Intelligence - PRI-DEMO-FREEZE-v4 cutover runbook.

Task: P51-DEVOPS-V4-CUTOVER-RUNBOOK-DRYRUN (@devops, assigned by @pm).
Sources: P36-DP-V4-MANIFEST-RECAPTURE (promotion order a..i), P34-DP-V4-MANIFEST-PLAN,
P51-DP-V4-CUTOVER-GATE-READINESS (readiness matrix), DEC-PRI-FREEZE-V4-SCOPE,
DEC-PRI-FREEZE-COMMENTS, DEC-PRI-UC-CONSTRAINTS, DEC-PRI-V4-TELEMETRY-IN-CUTOVER (id 32:
resource_alarm / resource_performance_measure promote after span (b), before predictions (f)).

WRITE-DISABLED BY DESIGN. `dry_run()` is read-only: it reads information_schema,
DESCRIBE HISTORY, demo_freeze_manifest, freeze_v3_comment_snapshot and Lakebase
`decisions`/`agent_tasks`, then prints the SQL it WOULD run. It never executes any
statement from the plan. `execute()` refuses unless ALL of these hold:
  * write_enabled=True is passed explicitly, AND
  * env PRI_V4_CUTOVER_WRITE == "1", AND
  * Lakebase decisions has DEC-PRI-V4-CUTOVER-GO with status 'decided', AND
  * the dry-run report shows every promotable step READY (no BLOCKED / MISSING / DRIFT).
Until @pm records the GO decision, nothing in this file can write to a v3 FROZEN object.

Usage (notebook, read-only):
    import sys; sys.path.append('<project root>/ops')
    import v4_cutover_runbook as rb
    report = rb.dry_run(spark, lakebase_cursor)   # prints plan + verdict
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

CATALOG = "cdm_tmforum"
SCHEMA = "provable_resilience_intelligence"
FQ = f"{CATALOG}.{SCHEMA}"
SUFFIX = "_v4_candidate"
V3 = "PRI-DEMO-FREEZE-v3"
V4_DRAFT = "PRI-DEMO-FREEZE-v4-DRAFT"
V4 = "PRI-DEMO-FREEZE-v4"
GO_DECISION = "DEC-PRI-V4-CUTOVER-GO"

# Operations that do NOT change data (manifest delta_version rule since v3).
_NON_DATA_PREFIXES = (
    "OPTIMIZE", "VACUUM", "SET TBLPROPERTIES", "UNSET TBLPROPERTIES", "ANALYZE",
    "CHANGE COLUMN", "ALTER COLUMN", "RENAME COLUMN", "ADD COLUMNS", "ADD CONSTRAINT",
    "DROP CONSTRAINT", "SET TAGS", "UNSET TAGS", "REORG", "CLUSTER BY", "UPGRADE PROTOCOL",
    "COMMENT", "SET COLUMN", "UPDATE SCHEMA", "ENABLE", "DISABLE", "ROW TRACKING",
    "DOMAIN METADATA", "ALTER TABLE",
)


@dataclass
class Item:
    step: str
    live: str               # live object name (promotion target)
    candidate: str | None   # *_v4_candidate source; None = no candidate exists by design
    owner_gate: str = ""    # open task / gate that must close first
    action: str = "promote" # promote | repoint_view | regenerate | report_only


@dataclass
class Finding:
    item: Item
    verdict: str
    details: dict = field(default_factory=dict)
    sql: list = field(default_factory=list)
    rollback_sql: list = field(default_factory=list)


def _c(name: str) -> str:
    return name + SUFFIX


# Promotion order from P36-DP-V4-MANIFEST-RECAPTURE step 2, (a)..(i).
RUNBOOK: list[Item] = [
    Item("a", "physical_resource_conduit", _c("physical_resource_conduit"), "P37 re-pin; P43-QA SRLG recheck"),
    Item("b", "physical_resource_span", _c("physical_resource_span"), "pin in v4-DRAFT"),
    # DEC-PRI-V4-TELEMETRY-IN-CUTOVER: 63,196 BB->BBS span_id remaps; must follow (b).
    Item("b2", "resource_alarm", _c("resource_alarm"), "DEC-PRI-V4-TELEMETRY-IN-CUTOVER"),
    Item("b2", "resource_performance_measure", _c("resource_performance_measure"), "DEC-PRI-V4-TELEMETRY-IN-CUTOVER"),
    Item("c", "derived_srlg_shared_conduit", _c("derived_srlg_shared_conduit"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073; BUG-QA-082"),
    Item("c", "derived_srlg_common_site", _c("derived_srlg_common_site"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073"),
    Item("c", "derived_srlg_shared_route", _c("derived_srlg_shared_route"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073"),
    Item("c", "derived_srlg_geo_proximity", _c("derived_srlg_geo_proximity"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073"),
    Item("c", "derived_shared_risk_group", _c("derived_shared_risk_group"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073"),
    Item("c", "unified_shared_risk_group", _c("unified_shared_risk_group"), "after (c) tables", "repoint_view"),
    Item("d", "path_diversity_conduit", _c("path_diversity_conduit"), "BUG-QA-084; P46-QA verify"),
    Item("e", "hazard_span_intersection", _c("hazard_span_intersection"), "BUG-QA-073 write (CEO esc #34/#35); P38-QA"),
    Item("e", "hazard_span_proximity", _c("hazard_span_proximity"), "BUG-QA-073 (CEO)"),
    Item("e", "span_hazard_features", _c("span_hazard_features"), "after HSP", "repoint_view"),
    Item("f", "span_risk_predictions", _c("span_risk_predictions"), "P44-ML-HSI-BBS-GRAIN-FEATURES; BUG-QA-087"),
    Item("g", "resilience_score_snapshot", _c("resilience_score_snapshot"), "P36-ML rescore; P50-ML band recalibration; BUG-QA-087"),
    Item("g", "proactive_action", _c("proactive_action"), "P52-DE-V4-PROACTIVE-ACTION-CANDIDATE"),
    Item("h", "revenue_at_risk", _c("revenue_at_risk"), "pin", "repoint_view"),
    Item("h", "mv_mrc_protected", _c("mv_mrc_protected"), "P30-DA Genie cutover", "repoint_view"),
    Item("h", "hazard_proximity_count", _c("hazard_proximity_count"), "P44-DA grain audit", "repoint_view"),
    Item("h", "diversity_coverage", _c("diversity_coverage"), "P51-DA-V4-DIVERSITY-COVERAGE-MV", "repoint_view"),
    Item("h", "kpi_delta_attribution", _c("kpi_delta_attribution"), "P39-DA; BUG-QA-082", "report_only"),
    Item("i", "schema_health_scorecard", None, "post-cutover regenerate", "regenerate"),
]

POST_STEPS = [
    "P1 Apply informational PK/FK constraints on promoted v4 core tables (DEC-PRI-UC-CONSTRAINTS, @data-engineer P43-DE-V4-PK-FK-CONSTRAINTS). NEVER on v3.",
    "P2 Verify fk_integrity_report = 0 orphans; KPI deltas vs v3 (61.55 / 848 / $48.45M) within the B9 tolerance (@data-analyst reconcile).",
    f"P3 @data-planner captures {V4} (data-changing rule); mark {V3} and {V4_DRAFT} rows SUPERSEDED.",
    "P4 @devops refreshes tests/frozen_v3_objects.json -> frozen_v4 snapshot and tests/v4_candidate_objects.json.",
    "P5 Drop *_v4_candidate objects only after @qa v4 sign-off + 48h audit hold; drop optical_anomaly_detection_pre_bugfix (BUG-QA-056).",
    "P6 @app-developer/@designer re-smoke; @data-analyst runs P30-DA Genie cutover (SA space).",
]


# ---------------------------------------------------------------- read helpers
def _is_data_change(op: str) -> bool:
    op = (op or "").upper()
    return not any(op.startswith(p) for p in _NON_DATA_PREFIXES)


def latest_data_version(spark, name: str):
    rows = spark.sql(f"DESCRIBE HISTORY {FQ}.`{name}`").select("version", "operation").collect()
    data = [r.version for r in rows if _is_data_change(r.operation)]
    return max(data) if data else None


def _objects(spark) -> dict:
    rows = spark.sql(
        f"SELECT table_name, table_type FROM {CATALOG}.information_schema.tables "
        f"WHERE table_schema = '{SCHEMA}'"
    ).collect()
    return {r.table_name: r.table_type for r in rows}


def _manifest(spark, version: str) -> dict:
    rows = spark.sql(
        f"SELECT object_name, delta_version, row_count, freeze_status FROM {FQ}.demo_freeze_manifest "
        "WHERE manifest_version = :v", args={"v": version}
    ).collect()
    return {r.object_name: r for r in rows}


def _comment_counts(spark) -> dict:
    rows = spark.sql(
        f"SELECT table_name, count(*) n FROM {FQ}.freeze_v3_comment_snapshot "
        "WHERE manifest_version = :v AND reapply_sql IS NOT NULL GROUP BY table_name", args={"v": V3}
    ).collect()
    return {r.table_name: r.n for r in rows}


def _decided(cur, code: str) -> bool:
    if cur is None:
        return False
    cur.execute("SELECT 1 FROM decisions WHERE decision_code = %s AND status = 'decided'", (code,))
    return cur.fetchone() is not None


def _open_tasks(cur) -> set:
    if cur is None:
        return set()
    cur.execute("SELECT task_code FROM agent_tasks WHERE status IN ('open','in_progress','blocked')")
    return {r[0] for r in cur.fetchall()}


# ---------------------------------------------------------------- plan builders
def promote_sql(item: Item, pin) -> list:
    live, cand = f"{FQ}.`{item.live}`", f"{FQ}.`{item.candidate}`"
    if item.action == "promote":
        return [
            f"CREATE OR REPLACE TABLE {live} AS SELECT * FROM {cand} VERSION AS OF {pin}",
            f"-- re-apply v3 comments: SELECT reapply_sql FROM {FQ}.freeze_v3_comment_snapshot "
            f"WHERE manifest_version='{V3}' AND table_name='{item.live}' ORDER BY ordinal_position",
            f"-- then apply new v4 column comments copied from {item.candidate} (DEC-PRI-FREEZE-COMMENTS)",
        ]
    if item.action == "repoint_view":
        return [f"-- re-create {live} from the {item.candidate} definition with *{SUFFIX} references "
                "rewritten to live names (SHOW CREATE TABLE); re-apply comments"]
    if item.action == "regenerate":
        return [f"-- regenerate {live} from promoted v4 objects (no candidate by design)"]
    return [f"-- {item.candidate} is an audit report; not promoted"]


def rollback_sql(item: Item, v3_pin) -> list:
    live = f"{FQ}.`{item.live}`"
    if v3_pin is None:
        if item.action == "promote":
            return [f"DROP TABLE IF EXISTS {live}  -- new in v4, no v3 pin"]
        return [f"-- {live}: restore previous view definition from v3 (no data pin)"]
    return [
        f"RESTORE TABLE {live} TO VERSION AS OF <pre-cutover live version>  -- v3 data pin = v{v3_pin}",
        f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
    ]


# ---------------------------------------------------------------- dry run
def dry_run(spark, cur=None, verbose: bool = True) -> list:
    """Read-only evaluation of every runbook item. Executes NO plan SQL."""
    objs, v3, draft, ccount = _objects(spark), _manifest(spark, V3), _manifest(spark, V4_DRAFT), _comment_counts(spark)
    open_tasks = _open_tasks(cur)
    out = []
    upstream_ok = True  # every promote item so far is READY
    for it in RUNBOOK:
        d = {"live_type": objs.get(it.live), "cand_type": objs.get(it.candidate) if it.candidate else None}
        v3row = v3.get(it.live)
        d["v3_status"] = v3row.freeze_status if v3row else "NOT_IN_V3"
        d["v3_pin"] = v3row.delta_version if v3row else None
        d["v3_comment_rows"] = ccount.get(it.live, 0)
        if d["live_type"] == "MANAGED" and d["v3_pin"] is not None:
            d["live_data_ver"] = latest_data_version(spark, it.live)
            d["live_drift"] = d["live_data_ver"] != d["v3_pin"]
        drow = draft.get(it.candidate) if it.candidate else None
        d["draft_pin"] = drow.delta_version if drow else None
        d["draft_status"] = drow.freeze_status if drow else "UNPINNED"
        if d["cand_type"] == "MANAGED":
            d["cand_data_ver"] = latest_data_version(spark, it.candidate)
        gates_open = sorted(t for t in open_tasks if t in it.owner_gate)
        d["open_gate_tasks"] = gates_open
        if it.action == "regenerate":
            verdict = "POST_CUTOVER"
        elif it.action == "report_only":
            verdict = "REPORT_ONLY"
        elif d["cand_type"] is None:
            verdict = "MISSING_CANDIDATE"
        elif d.get("live_drift"):
            verdict = "V3_DRIFT"
        elif it.action == "repoint_view" and gates_open:
            verdict = "GATE_OPEN"
        elif it.action == "repoint_view":
            verdict = "READY" if upstream_ok else "WAITS_UPSTREAM"
        elif d["draft_pin"] is None:
            verdict = "UNPINNED"
        elif d["draft_status"] == "V4_CANDIDATE_WIP":
            verdict = "WIP_PIN"
        elif d.get("cand_data_ver") is not None and d["draft_pin"] is not None and d["cand_data_ver"] != d["draft_pin"]:
            verdict = "PIN_DRIFT"
        elif gates_open:
            verdict = "GATE_OPEN"
        else:
            verdict = "READY"
        if it.action == "promote" and verdict != "READY":
            upstream_ok = False
        f = Finding(it, verdict, d, promote_sql(it, d["draft_pin"] if d["draft_pin"] is not None else "<pin>"),
                    rollback_sql(it, d["v3_pin"]))
        out.append(f)
    if verbose:
        print_report(out, cur)
    return out


def summary(findings: list, cur=None) -> dict:
    blocking = [f for f in findings if f.verdict not in ("READY", "POST_CUTOVER", "REPORT_ONLY")]
    return {
        "items": len(findings),
        "ready": sum(f.verdict == "READY" for f in findings),
        "blocking": len(blocking),
        "go_decision": _decided(cur, GO_DECISION),
        "v3_drift": [f.item.live for f in findings if f.details.get("live_drift")],
        "cutover_ready": not blocking and _decided(cur, GO_DECISION),
    }


def print_report(findings: list, cur=None) -> None:
    print(f"PRI v4 cutover DRY RUN (write-disabled) - {len(findings)} items")
    for f in findings:
        d = f.details
        print(f"[{f.item.step}] {f.item.live:<30} {f.verdict:<18} v3_pin={d.get('v3_pin')} live_dv={d.get('live_data_ver')} "
              f"draft_pin={d.get('draft_pin')}({d.get('draft_status')}) cand_dv={d.get('cand_data_ver')} "
              f"comments={d.get('v3_comment_rows')} gates={d.get('open_gate_tasks')}")
        for s in f.sql:
            print("      WOULD RUN:", s)
        for s in f.rollback_sql:
            print("      ROLLBACK :", s)
    for p in POST_STEPS:
        print("   POST:", p)
    print("SUMMARY:", summary(findings, cur))


# ---------------------------------------------------------------- guarded execute
class CutoverRefused(RuntimeError):
    pass


def execute(spark, cur, write_enabled: bool = False):
    """Refuses unless explicitly enabled, env-armed, GO-decided and fully READY."""
    if not write_enabled or os.environ.get("PRI_V4_CUTOVER_WRITE") != "1":
        raise CutoverRefused("write-disabled: pass write_enabled=True AND set PRI_V4_CUTOVER_WRITE=1")
    if not _decided(cur, GO_DECISION):
        raise CutoverRefused(f"no decided {GO_DECISION} row in Lakebase decisions")
    findings = dry_run(spark, cur, verbose=False)
    s = summary(findings, cur)
    if not s["cutover_ready"]:
        raise CutoverRefused(f"dry run not READY: {s}")
    raise CutoverRefused("execution intentionally not implemented in P51; @pm must assign the cutover task")
