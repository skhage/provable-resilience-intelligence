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

P65-DEVOPS-RUNBOOK-PIN-GATES (DEC-PRI-V4-PIN-FINGERPRINT-GATES, id 40): Delta 7-day retention expires
the freeze VERSION AS OF pins before the 11-02 cutover, so NO freeze check in this runbook uses time
travel any more. Every v3 FROZEN live table and every v4-DRAFT candidate is gated by recomputing all 3
fingerprint components (fp_row_count, fp_sha2_v1_null_skip, fp_sha2_v2_null_token) plus the column
count against cdm_tmforum.provable_resilience_intelligence.freeze_pin_fingerprint_gate (@data-planner
P58). Any mismatch, missing baseline or PROVISIONAL baseline fails closed. Delta versions are printed
for information only.

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
# P65: pin-free equivalence gates (replace every VERSION AS OF freeze pin check).
FP_DECISION = "DEC-PRI-V4-PIN-FINGERPRINT-GATES"
FP_GATE_TABLE = "freeze_pin_fingerprint_gate"
FP_COMPONENTS = ("fp_row_count", "fp_sha2_v1_null_skip", "fp_sha2_v2_null_token", "fp_column_count")
FP_NULL_TOKEN = "<NULL>"

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
    # P63 / DEC-PRI-V4-SERVICE-PATH-PROMOTE-CONDITIONAL (id 39): runs ONLY if service_path_v4_candidate has
    # landed in UC and the P54-DE writer + P54-QA spec gates are completed. Default = SKIPPED_CONDITIONAL
    # (non-blocking, not a cutover gate per DEC-37 cond 4) and fk_path_span is skipped in pk_fk_plan().
    Item("b3", "service_path", _c("service_path"), "P54-DE-SERVICE-PATH-V4-WRITER; P54-QA-VERIFY-SERVICE-PATH-V4-SPEC",
         "conditional_promote"),
    # P51-QA matrix correction: BUG-QA-082 (kpi_delta) gates step (h), not (c).
    Item("c", "derived_srlg_shared_conduit", _c("derived_srlg_shared_conduit"), "P43-QA-RECHECK-SRLG-V4-GATES-POST-073"),
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

# P55-DEVOPS-V4-CUTOVER-PR-PREP: ordered end-to-end checklist (DEC-PRI-V4-CUTOVER-TARGET-1030).
# (order, phase, owner, action, gate task codes that must be completed first).
# PRE = before any promotion, PROMOTE = RUNBOOK items a..i above, POST = after promotion.
CHECKLIST: list[tuple] = [
    (1, "PRE", "CEO", "Run the BUG-QA-073 HSI re-derive on BBS-* segments (interactive, dry run PASS QA S40)", ("BUG-QA-073",)),
    (2, "PRE", "CEO", "Run the P36 v4 shadow rescore write (dry run PASS P49-QA)", ("P36-ML-V4-RESCORE-CONDUIT-DIVERSITY",)),
    (3, "PRE", "@ml-engineer", "Rebuild span_risk_predictions_v4 at BBS grain + HSI-grain features", ("BUG-DP-073", "P44-ML-HSI-BBS-GRAIN-FEATURES", "BUG-QA-087")),
    (4, "PRE", "@data-engineer", "Build proactive_action_v4_candidate (ACT-RULE-v1)", ("P52-DE-V4-PROACTIVE-ACTION-CANDIDATE", "P52-QA-VERIFY-P52-DE-DRYRUN")),
    (5, "PRE", "@data-analyst", "Build diversity_coverage_v4 MV; finalize kpi_delta; HSI-grain KPI audit", ("P51-DA-V4-DIVERSITY-COVERAGE-MV", "P39-DA-V4-KPI-DELTA-FINALIZE", "BUG-QA-082", "P44-DA-HSI-BBS-KPI-GRAIN-AUDIT")),
    # P65: "re-pin" now means re-baseline the PROVISIONAL fingerprint rows; Delta versions are informational only.
    (6, "PRE", "@data-planner", "Re-baseline PROVISIONAL fingerprints in freeze_pin_fingerprint_gate (hazard_span_intersection_v4_candidate, span_risk_predictions_v4_candidate) after the CEO writes; HSI-dependent v4-DRAFT rows (non-HSI done in P37/P58)", ("P48-DP-V4-REPIN-HSI-DEPENDENT", "BUG-DP-071", "P65-DP-PIN-TO-FINGERPRINT-GATES", FP_DECISION)),
    (7, "PRE", "@qa", "QA gate (a) draft manifest verify + independent fingerprint-gate verify (fail closed)", ("P37-QA-VERIFY-V4-DRAFT-MANIFEST", "P65-QA-VERIFY-FINGERPRINT-GATES")),
    (8, "PRE", "@qa", "QA gate (b) HSI/prediction re-verify after the CEO writes", ("P51-QA-VERIFY-BUG-QA-087", "P38-QA-VERIFY-BUG-DP-071", "P36-QA-VERIFY-BUG-DP-070")),
    (9, "PRE", "@qa", "QA gate (c) SRLG data gates (CONDITIONAL PASS, P51-QA)", ("P51-QA-VERIFY-CUTOVER-READINESS",)),
    (10, "PRE", "@qa", "QA gate (d) band recalibration verify", ("P50-QA-VERIFY-V4-BAND-RECALIBRATION",)),
    (11, "PRE", "@pm", "Record DEC-PRI-V4-CUTOVER-GO (decided) and assign the execution task", ()),
    (12, "PROMOTE", "@pm-assigned", "Runbook items a..i in order (dry_run all READY = every fingerprint gate FP_PASS, then execute; re-check each candidate fingerprint right before its swap and the live fingerprint right after)", ()),
    # P60: capture the v4 column-comment snapshot IMMEDIATELY after the swap (mirrors freeze_v3_comment_snapshot),
    # before any other POST DDL. Manual step (no gate task) so it is never auto-DONE.
    (13, "POST", "@devops", "Capture freeze_v4_comment_snapshot for every promoted v4 table (v4_comment_snapshot_sql)", ()),
    (14, "POST", "@data-engineer", "Informational PK/FK constraints, AFTER_SWAP subset only: promoted v4 tables (DEC-PRI-UC-CONSTRAINTS), never v3; fk_path_span only if the service_path_v4 conditional promote ran, else SKIPPED", ("P43-DE-V4-PK-FK-CONSTRAINTS", "DEC-PRI-V4-SERVICE-PATH-PROMOTE-CONDITIONAL")),
    (15, "POST", "@data-analyst", "P30 Genie + exec dashboard repoint to MRC Protected; P51 diversity coverage repoint", ("P30-DA-GENIE-MRC-PROTECTED-CUTOVER",)),
    (16, "POST", "@app-developer", "Flip app flag PRI_V4_KPIS=true; @designer re-smoke", ("P36-APP-V4-CONDUIT-COVERAGE-FILTER", "P37-DESIGN-VERIFY-V4-KPI")),
    (17, "POST", "@devops", "Bundle pipeline sync (BUG-QA-070 6-step recipe) + guard snapshot refresh; CI green; merge PR", ("P43-DEVOPS-BUNDLE-PIPELINE-SYNC",)),
    (18, "POST", "@data-planner", "Capture PRI-DEMO-FREEZE-v4; mark v3 + v4-DRAFT rows SUPERSEDED", ()),
    # P60: PK/FK statements that touch a table still FROZEN in v3 (not promoted) wait until v3 is SUPERSEDED.
    (19, "POST", "@data-engineer", "Informational PK/FK constraints, DEFERRED subset (non-promoted tables) after v3 SUPERSEDED; fk_path_span stays SKIPPED if service_path_v4 was not promoted", ("DEC-PRI-V4-SERVICE-PATH-PROMOTE-CONDITIONAL",)),
]


def checklist_status(cur) -> list:
    """Read-only: status of every gate task in CHECKLIST from Lakebase agent_tasks."""
    codes = sorted({c for row in CHECKLIST for c in row[4] if not c.startswith("DEC-")})
    status = {}
    if cur is not None and codes:
        cur.execute("SELECT task_code, status FROM agent_tasks WHERE task_code = ANY(%s)", (codes,))
        status = dict(cur.fetchall())
    # P63: DEC-* gates are Lakebase decisions; 'completed' when decided.
    for d in sorted({c for row in CHECKLIST for c in row[4] if c.startswith("DEC-")}):
        status[d] = "completed" if _decided(cur, d) else "UNKNOWN"
    out = []
    for order, phase, owner, action, gates in CHECKLIST:
        g = {c: status.get(c, "UNKNOWN") for c in gates}
        if order == 11:  # GO is a Lakebase decision, not a task
            done = _decided(cur, GO_DECISION)
        else:  # no gate task = manual step, never auto-DONE (DEC-* gates alone do not count as a task)
            done = any(not c.startswith("DEC-") for c in g) and all(v == "completed" for v in g.values())
        out.append({"order": order, "phase": phase, "owner": owner, "action": action, "gates": g, "done": done})
    return out


# P57-DEVOPS-CUTOVER-SLIP-CONTINGENCY: dated schedule for both paths (DEC-PRI-V4-CUTOVER-TARGET-1030, id 33).
# Path A: the CEO runs both writers (CHECKLIST 1+2) by APPROVAL_DEADLINE EOD -> cutover on BASE_TARGET.
# Path B: no approval by the deadline -> cutover slips to PLAN_B_TARGET (PM R57). DEC-33 rule is
# +48h per missed day; PLAN_B_TARGET must never be earlier than the rule-derived date.
# Read-only: nothing here writes to Lakebase, UC or any v4/v3 table. Freeze guards are unchanged.
import datetime as _dt  # noqa: E402

TARGET_DECISION = "DEC-PRI-V4-CUTOVER-TARGET-1030"  # SUPERSEDED by DEC id 38 (PM R63)
APPROVAL_DEADLINE = _dt.date(2026, 10, 29)
BASE_TARGET = _dt.date(2026, 10, 30)
PLAN_B_TARGET = _dt.date(2026, 11, 2)
# P63-DEVOPS-RUNBOOK-RETARGET-1102: DEC-PRI-V4-CUTOVER-SLIP-1102 (id 38) DECIDED at PM R63 2026-10-30 01:05Z.
# Path B is now the ACTIVE plan: target fixed at 2026-11-02 and the new CEO deadline for the BUG-QA-073 +
# P36 writes is 2026-11-01 23:59Z. Missing it again does NOT auto-slip: path B_MISSED proposes a date
# (DEC-33 +48h/day rule from the new deadline) and needs a new @pm decision.
SLIP_DECISION = "DEC-PRI-V4-CUTOVER-SLIP-1102"
SLIP_APPROVAL_DEADLINE = _dt.date(2026, 11, 1)
ACTIVE_TARGET = PLAN_B_TARGET
CEO_GATES = ("BUG-QA-073", "P36-ML-V4-RESCORE-CONDUIT-DIVERSITY")
# Day offset of each CHECKLIST step relative to cutover day T (CEO writes due EOD T-1).
STEP_OFFSET_DAYS = {1: -1, 2: -1, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0,
                    11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 1, 19: 1}
AUDIT_HOLD_DAYS = 2  # POST P5: drop *_v4_candidate only after QA sign-off + 48h


def rule_target(missed_days: int) -> _dt.date:
    """DEC-33: the cutover target rolls +48h for every day the CEO approval is missed."""
    return BASE_TARGET + _dt.timedelta(days=2 * max(0, missed_days))


def dated_checklist(target: _dt.date) -> list:
    """CHECKLIST rows with due dates for a given cutover day T."""
    return [{"order": o, "phase": ph, "owner": ow, "action": a,
             "due": target + _dt.timedelta(days=STEP_OFFSET_DAYS[o])}
            for o, ph, ow, a, _g in CHECKLIST]


def contingency_plan(cur, today: _dt.date | None = None, slip_decided: bool | None = None) -> dict:
    """Read-only: decide which path applies and return the dated checklist for it (and for the other path).

    slip_decided=None reads DEC-PRI-V4-CUTOVER-SLIP-1102 from Lakebase decisions (P63). Once it is decided,
    path B is locked to 2026-11-02 with the 2026-11-01 CEO deadline.
    """
    today = today or _dt.date.today()
    status = {}
    if cur is not None:
        cur.execute("SELECT task_code, status FROM agent_tasks WHERE task_code = ANY(%s)", (list(CEO_GATES),))
        status = dict(cur.fetchall())
    if slip_decided is None:
        slip_decided = _decided(cur, SLIP_DECISION)
    ceo_done = all(status.get(c) == "completed" for c in CEO_GATES)
    missed = max(0, (today - APPROVAL_DEADLINE).days)
    needs_pm_decision = False
    if slip_decided:
        missed2 = max(0, (today - SLIP_APPROVAL_DEADLINE).days)
        if ceo_done or missed2 == 0:
            path, target = "B", ACTIVE_TARGET
        else:  # new deadline missed: propose (never auto-apply) the next date per the DEC-33 rule
            path, target, needs_pm_decision = "B_MISSED", ACTIVE_TARGET + _dt.timedelta(days=2 * missed2), True
    elif ceo_done and missed == 0:
        path, target = "A", BASE_TARGET
    elif missed == 0:
        path, target = "PENDING", BASE_TARGET  # still inside the approval window; stage both
    else:
        path, target = "B", max(PLAN_B_TARGET, rule_target(missed))
    return {
        "path": path, "today": today, "ceo_gates": {c: status.get(c, "UNKNOWN") for c in CEO_GATES},
        "slip_decided": bool(slip_decided), "needs_pm_decision": needs_pm_decision,
        "ceo_deadline": SLIP_APPROVAL_DEADLINE if slip_decided else APPROVAL_DEADLINE,
        "missed_days": missed, "target": target,
        "candidate_drop_earliest": target + _dt.timedelta(days=AUDIT_HOLD_DAYS),
        "plan_a": dated_checklist(BASE_TARGET), "plan_b": dated_checklist(max(PLAN_B_TARGET, rule_target(1))),
    }


POST_STEPS = [
    "P0 @devops captures freeze_v4_comment_snapshot right after the swap (v4_comment_snapshot_sql; same 8 columns as freeze_v3_comment_snapshot).",
    "P1 Apply informational PK/FK constraints: AFTER_SWAP subset on promoted v4 tables now, DEFERRED subset only after v3 SUPERSEDED (pk_fk_plan; DEC-PRI-UC-CONSTRAINTS, P43-DE-V4-PK-FK-CONSTRAINTS). NEVER on v3 FROZEN.",
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
        f"SELECT object_name, delta_version, restore_version, row_count, freeze_status FROM {FQ}.demo_freeze_manifest "
        "WHERE manifest_version = :v", args={"v": version}
    ).collect()
    return {r.object_name: r for r in rows}


def _comment_counts(spark) -> dict:
    rows = spark.sql(
        f"SELECT table_name, count(*) n FROM {FQ}.freeze_v3_comment_snapshot "
        "WHERE manifest_version = :v AND reapply_sql IS NOT NULL GROUP BY table_name", args={"v": V3}
    ).collect()
    return {r.table_name: r.n for r in rows}


def fingerprint_sql(name: str, columns: list) -> str:
    """P65: the DP P58 / DE S60 fingerprint as ONE read-only SELECT (no time travel).

    v1 = SUM(CONV(SUBSTR(SHA2(CONCAT_WS('|', every column cast to string, ordinal order), 256), 1, 15), 16, 10))
    as DECIMAL(38,0). v2 = same with COALESCE(col, '<NULL>') so NULL-position shifts are detected.
    """
    if not columns:
        raise ValueError(f"no columns for {name}")
    v1 = ", ".join(f"CAST(`{c}` AS STRING)" for c in columns)
    v2 = ", ".join(f"COALESCE(CAST(`{c}` AS STRING), '{FP_NULL_TOKEN}')" for c in columns)

    def h(e):
        return f"CAST(SUM(CAST(CONV(SUBSTR(SHA2(CONCAT_WS('|', {e}), 256), 1, 15), 16, 10) AS DECIMAL(38,0))) AS STRING)"
    return (f"SELECT COUNT(*) AS fp_row_count, {h(v1)} AS fp_sha2_v1_null_skip, {h(v2)} AS fp_sha2_v2_null_token, "
            f"{len(columns)} AS fp_column_count FROM {FQ}.`{name}`")


def _columns(spark, name: str) -> list:
    rows = spark.sql(
        f"SELECT column_name FROM {CATALOG}.information_schema.columns "
        f"WHERE table_schema = '{SCHEMA}' AND table_name = :t ORDER BY ordinal_position", args={"t": name}
    ).collect()
    return [r.column_name for r in rows]


def fingerprint(spark, name: str) -> dict:
    """Recompute all fingerprint components on the CURRENT table (read-only)."""
    r = spark.sql(fingerprint_sql(name, _columns(spark, name))).first()
    return {"fp_row_count": int(r.fp_row_count), "fp_sha2_v1_null_skip": str(r.fp_sha2_v1_null_skip),
            "fp_sha2_v2_null_token": str(r.fp_sha2_v2_null_token), "fp_column_count": int(r.fp_column_count)}


def _fp_baselines(spark) -> dict:
    rows = spark.sql(
        f"SELECT manifest_version, object_name, gate_status, {', '.join(FP_COMPONENTS)} FROM {FQ}.{FP_GATE_TABLE}"
    ).collect()
    return {(r.manifest_version, r.object_name): r.asDict() for r in rows}


def compare_fingerprint(actual, baseline) -> dict:
    """Pure, fail-closed comparison. Only FP_PASS is non-blocking.

    FP_NO_BASELINE  - no freeze_pin_fingerprint_gate row for this object/manifest
    FP_UNREADABLE   - the fingerprint could not be computed
    FP_MISMATCH     - any of row count / v1 / v2 / column count differs
    FP_PROVISIONAL  - baseline is PROVISIONAL (expected to change; re-baseline after the CEO writes)
    FP_PASS         - all 4 components equal a PASS baseline
    """
    if not baseline:
        return {"status": "FP_NO_BASELINE", "mismatched": []}
    if not actual:
        return {"status": "FP_UNREADABLE", "mismatched": list(FP_COMPONENTS)}
    bad = [k for k in FP_COMPONENTS if baseline.get(k) is None or str(actual.get(k)) != str(baseline.get(k))]
    if (baseline.get("gate_status") or "").upper() == "PROVISIONAL":
        return {"status": "FP_PROVISIONAL", "mismatched": bad}
    if bad:
        return {"status": "FP_MISMATCH", "mismatched": bad}
    if (baseline.get("gate_status") or "").upper() != "PASS":
        return {"status": "FP_NO_BASELINE", "mismatched": []}
    return {"status": "FP_PASS", "mismatched": []}


def fingerprint_gate(spark, name: str, manifest_version: str, baselines: dict | None = None) -> dict:
    """Recompute + compare one object. Any exception while computing counts as FP_UNREADABLE (fail closed)."""
    baselines = baselines if baselines is not None else _fp_baselines(spark)
    base = baselines.get((manifest_version, name))
    try:
        actual = fingerprint(spark, name) if base else None
    except Exception as e:  # noqa: BLE001 - fail closed on any read error
        return {"status": "FP_UNREADABLE", "mismatched": list(FP_COMPONENTS), "error": str(e)[:200]}
    return compare_fingerprint(actual, base)


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
def promote_sql(item: Item, fp_status=None) -> list:
    """P65: pin-free. The candidate is read at its CURRENT version, guarded by the fingerprint gate."""
    live, cand = f"{FQ}.`{item.live}`", f"{FQ}.`{item.candidate}`"
    if item.action in ("promote", "conditional_promote"):
        pre = ([f"-- CONDITIONAL ({SERVICE_PATH_DECISION}): run only if service_path_condition() is met; "
                f"else log SKIPPED and skip {SERVICE_PATH_FK}"] if item.action == "conditional_promote" else [])
        return pre + [
            f"-- FINGERPRINT GATE ({FP_DECISION}, fail closed; dry-run status={fp_status or '<not computed>'}): "
            f"fingerprint_gate(spark, '{item.candidate}', '{V4_DRAFT}') must be FP_PASS immediately before the swap",
            f"CREATE OR REPLACE TABLE {live} AS SELECT * FROM {cand}",
            f"-- POST-SWAP CHECK (fail closed): fingerprint(spark, '{item.live}') must equal the {FP_GATE_TABLE} "
            f"'{V4_DRAFT}' baseline of {item.candidate}; else run ROLLBACK",
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
        if item.action in ("promote", "conditional_promote"):
            return [f"DROP TABLE IF EXISTS {live}  -- new in v4, no v3 pin"]
        return [f"-- {live}: restore previous view definition from v3 (no data pin)"]
    # P65: <pre-cutover live version> is captured from DESCRIBE HISTORY at swap time (minutes old, well inside
    # retention); it is NOT a freeze pin. The v3 manifest delta_version is informational only.
    return [
        f"RESTORE TABLE {live} TO VERSION AS OF <pre-cutover live version captured immediately before the swap>"
        f"  -- manifest v{v3_pin} is informational only",
        f"-- verify (fail closed): fingerprint(spark, '{item.live}') == {FP_GATE_TABLE} '{V3}' baseline",
        f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
    ]


def gate0_restore_sql(item: Item, restore_version) -> list:
    """P67-DE-RUNBOOK-RESTORE-VERSION (BUG-QA-095): gate-0 restore of a v3 FROZEN live table whose fingerprint
    drifted BEFORE the swap (verdict V3_FP_*). Target = demo_freeze_manifest.restore_version (readable Delta version),
    never delta_version (data-lineage pin, may be past the 7-day retention). Text builder only; never executed here."""
    live = f"{FQ}.`{item.live}`"
    if restore_version is None:
        return [f"-- {live}: no manifest restore_version; gate 0 cannot restore, escalate to @pm (fail closed)"]
    return [
        f"RESTORE TABLE {live} TO VERSION AS OF {int(restore_version)}  -- gate 0: manifest restore_version (BUG-QA-095)",
        f"-- verify (fail closed): fingerprint(spark, '{item.live}') == {FP_GATE_TABLE} '{V3}' baseline",
        f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
    ]


# P60-DEVOPS-RUNBOOK-V4-COMMENT-SNAPSHOT: v4 comment snapshot + PK/FK placement. Text builders only.
V4_COMMENT_SNAPSHOT = "freeze_v4_comment_snapshot"
V3_COMMENT_SNAPSHOT = "freeze_v3_comment_snapshot"
COMMENT_SNAPSHOT_COLUMNS = ("manifest_version", "table_name", "column_name", "ordinal_position",
                            "comment_level", "comment", "reapply_sql", "snapshot_ts")
PK_FK_DDL_PATH = "runbooks/P43_v4_pk_fk_constraints.sql"  # @data-engineer P43-DE-V4-PK-FK-CONSTRAINTS


def promoted_tables(include_conditional: bool = False) -> list:
    """Managed live tables replaced by the swap (views/regenerated/report objects excluded).

    Conditional promotes (service_path, P63) count only when include_conditional=True, i.e. when
    service_path_condition() is met at cutover time.
    """
    acts = ("promote", "conditional_promote") if include_conditional else ("promote",)
    return [i.live for i in RUNBOOK if i.action in acts]


# P63: DEC-PRI-V4-SERVICE-PATH-PROMOTE-CONDITIONAL inputs.
SERVICE_PATH_DECISION = "DEC-PRI-V4-SERVICE-PATH-PROMOTE-CONDITIONAL"
SERVICE_PATH_GATES = ("P54-DE-SERVICE-PATH-V4-WRITER", "P54-QA-VERIFY-SERVICE-PATH-V4-SPEC")
SERVICE_PATH_FK = "fk_path_span"


def service_path_condition(objs: dict, task_status: dict) -> dict:
    """Pure check: met only if service_path_v4_candidate is a MANAGED table in UC AND both P54 gates are completed."""
    landed = objs.get(_c("service_path")) == "MANAGED"
    gates = {c: task_status.get(c, "UNKNOWN") for c in SERVICE_PATH_GATES}
    met = landed and all(v == "completed" for v in gates.values())
    return {"met": met, "candidate_landed": landed, "gates": gates,
            "log": None if met else (f"SKIPPED service_path_v4 promote + {SERVICE_PATH_FK} "
                                     f"({SERVICE_PATH_DECISION}): candidate_landed={landed} gates={gates}")}


def v4_comment_snapshot_sql(tables=None) -> list:
    """SQL (NOT executed here) that captures freeze_v4_comment_snapshot right after the swap.

    Same 8 columns as freeze_v3_comment_snapshot. Idempotent: CREATE IF NOT EXISTS, then
    DELETE + INSERT for manifest_version = PRI-DEMO-FREEZE-v4 only. Never touches the v3 snapshot.
    Unchanged v3 objects stay covered by freeze_v3_comment_snapshot.
    """
    tables = list(tables or promoted_tables())
    tgt = f"{FQ}.{V4_COMMENT_SNAPSHOT}"
    in_list = ", ".join(f"'{t}'" for t in tables)
    esc = "replace(replace({x}, '\\\\', '\\\\\\\\'), '\\'', '\\\\\\'')"
    return [
        f"CREATE TABLE IF NOT EXISTS {tgt} ("
        "manifest_version STRING COMMENT 'Freeze manifest this snapshot belongs to (PRI-DEMO-FREEZE-v4)', "
        "table_name STRING COMMENT 'Promoted v4 managed table in cdm_tmforum.provable_resilience_intelligence', "
        "column_name STRING COMMENT 'Column name; NULL for the table-level comment row', "
        "ordinal_position INT COMMENT 'Column ordinal position; 0 for the table-level comment row. Use it to order reapply_sql', "
        "comment_level STRING COMMENT 'TABLE or COLUMN', "
        "comment STRING COMMENT 'Authoritative comment text at snapshot time (DEC-PRI-FREEZE-COMMENTS)', "
        "reapply_sql STRING COMMENT 'Ready-to-run COMMENT ON TABLE / ALTER COLUMN COMMENT statement. Metadata-only', "
        "snapshot_ts TIMESTAMP COMMENT 'UTC timestamp when the snapshot was captured') "
        "COMMENT 'Lakelink Fiber PRI: column-comment snapshot of promoted v4 tables, captured right after the v4 swap. Mirrors freeze_v3_comment_snapshot.'",
        f"DELETE FROM {tgt} WHERE manifest_version = '{V4}'",
        f"INSERT INTO {tgt} "
        f"SELECT '{V4}', t.table_name, NULL, 0, 'TABLE', t.comment, "
        f"concat('COMMENT ON TABLE {FQ}.`', t.table_name, '` IS \\'', {esc.format(x='t.comment')}, '\\';'), current_timestamp() "
        f"FROM {CATALOG}.information_schema.tables t "
        f"WHERE t.table_schema = '{SCHEMA}' AND t.table_name IN ({in_list}) AND t.comment IS NOT NULL "
        f"UNION ALL SELECT '{V4}', c.table_name, c.column_name, c.ordinal_position, 'COLUMN', c.comment, "
        f"concat('ALTER TABLE {FQ}.`', c.table_name, '` ALTER COLUMN `', c.column_name, '` COMMENT \\'', "
        f"{esc.format(x='c.comment')}, '\\';'), current_timestamp() "
        f"FROM {CATALOG}.information_schema.columns c "
        f"WHERE c.table_schema = '{SCHEMA}' AND c.table_name IN ({in_list}) AND c.comment IS NOT NULL",
        f"-- verify: every promoted table has a TABLE row and COLUMN rows = commented columns in information_schema "
        f"(SELECT table_name, count(*) FROM {tgt} WHERE manifest_version = '{V4}' GROUP BY table_name)",
    ]


def _ddl_statements(text: str) -> list:
    body = "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())
    return [" ".join(s.split()) for s in body.split(";") if s.strip()]


def pk_fk_plan(text: str | None = None, root: str | None = None, service_path_promoted: bool = False) -> dict:
    """Split the P43-DE constraint DDL into AFTER_SWAP (step 14) and DEFERRED (step 19).

    A statement is AFTER_SWAP only if its ALTER target AND any REFERENCES parent are promoted
    v4 tables. Anything touching a table that stays v3 FROZEN until PRI-DEMO-FREEZE-v4 is captured
    is DEFERRED (DEC-PRI-UC-CONSTRAINTS: never ALTER v3 FROZEN). Reads a file only; executes nothing.
    P63: fk_path_span is SKIPPED (own bucket, never run) unless the service_path_v4 conditional promote ran.
    """
    import re
    if text is None:
        base = root or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        path = os.path.join(base, PK_FK_DDL_PATH)
        if not os.path.exists(path):
            return {"source": None, "after_swap": [], "deferred": [], "deferred_tables": [], "skipped": []}
        with open(path) as fh:
            text = fh.read()
    promoted = set(promoted_tables(include_conditional=service_path_promoted))
    after, deferred, dtables, skipped = [], [], set(), []
    for s in _ddl_statements(text):
        m = re.match(r"(?i)ALTER TABLE\s+`?([\w.]+?)`?\s", s + " ")
        if not m:
            continue  # USE / pre-flight SELECT / verify SELECT
        if not service_path_promoted and re.search(rf"(?i)CONSTRAINT\s+`?{SERVICE_PATH_FK}`?\s", s):
            skipped.append(s)
            continue
        tbl = m.group(1).split(".")[-1]
        ref = re.search(r"(?i)REFERENCES\s+`?([\w.]+?)`?\s*\(", s)
        touched = {tbl} | ({ref.group(1).split(".")[-1]} if ref else set())
        if touched <= promoted:
            after.append(s)
        else:
            deferred.append(s)
            dtables |= touched - promoted
    return {"source": PK_FK_DDL_PATH, "after_swap": after, "deferred": deferred,
            "deferred_tables": sorted(dtables), "skipped": skipped}


# ---------------------------------------------------------------- dry run
def dry_run(spark, cur=None, verbose: bool = True) -> list:
    """Read-only evaluation of every runbook item. Executes NO plan SQL."""
    objs, v3, draft, ccount = _objects(spark), _manifest(spark, V3), _manifest(spark, V4_DRAFT), _comment_counts(spark)
    fp_base = _fp_baselines(spark)
    open_tasks = _open_tasks(cur)
    sp_status = {}
    if cur is not None:
        cur.execute("SELECT task_code, status FROM agent_tasks WHERE task_code = ANY(%s)", (list(SERVICE_PATH_GATES),))
        sp_status = dict(cur.fetchall())
    sp_cond = service_path_condition(objs, sp_status)
    out = []
    upstream_ok = True  # every promote item so far is READY
    for it in RUNBOOK:
        d = {"live_type": objs.get(it.live), "cand_type": objs.get(it.candidate) if it.candidate else None}
        v3row = v3.get(it.live)
        d["v3_status"] = v3row.freeze_status if v3row else "NOT_IN_V3"
        d["v3_pin"] = v3row.delta_version if v3row else None  # data-lineage label only
        d["v3_restore"] = v3row.restore_version if v3row else None  # P67: gate-0 restore target
        d["v3_comment_rows"] = ccount.get(it.live, 0)
        if d["live_type"] == "MANAGED" and v3row is not None:
            d["live_data_ver"] = latest_data_version(spark, it.live)  # informational only (P65)
            d["live_fp"] = fingerprint_gate(spark, it.live, V3, fp_base)
            d["live_drift"] = d["live_fp"]["status"] != "FP_PASS"
        drow = draft.get(it.candidate) if it.candidate else None
        d["draft_pin"] = drow.delta_version if drow else None
        d["draft_status"] = drow.freeze_status if drow else "UNPINNED"
        if d["cand_type"] == "MANAGED":
            d["cand_data_ver"] = latest_data_version(spark, it.candidate)  # informational only (P65)
            if drow is not None and it.action in ("promote", "conditional_promote"):
                d["cand_fp"] = fingerprint_gate(spark, it.candidate, V4_DRAFT, fp_base)
        gates_open = sorted(t for t in open_tasks if t in it.owner_gate)
        d["open_gate_tasks"] = gates_open
        if it.action == "conditional_promote":
            d["condition"] = sp_cond
        if it.action == "conditional_promote" and not sp_cond["met"]:
            verdict = "SKIPPED_CONDITIONAL"  # non-blocking; upstream_ok unchanged
        elif it.action == "regenerate":
            verdict = "POST_CUTOVER"
        elif it.action == "report_only":
            verdict = "REPORT_ONLY"
        elif d["cand_type"] is None:
            verdict = "MISSING_CANDIDATE"
        elif d.get("live_drift"):
            verdict = "V3_FP_" + d["live_fp"]["status"][3:]  # e.g. V3_FP_MISMATCH (fail closed)
        elif it.action == "repoint_view" and gates_open:
            verdict = "GATE_OPEN"
        elif it.action == "repoint_view":
            verdict = "READY" if upstream_ok else "WAITS_UPSTREAM"
        elif d["draft_pin"] is None:
            verdict = "UNPINNED"
        elif d["draft_status"] == "V4_CANDIDATE_WIP":
            verdict = "WIP_PIN"
        # P65: drift is decided by the fingerprint gate, not by comparing Delta versions to a pin.
        elif d.get("cand_fp", {}).get("status", "FP_NO_BASELINE") != "FP_PASS":
            verdict = d.get("cand_fp", {}).get("status", "FP_NO_BASELINE")
        elif gates_open:
            verdict = "GATE_OPEN"
        else:
            verdict = "READY"
        if it.action in ("promote", "conditional_promote") and verdict not in ("READY", "SKIPPED_CONDITIONAL"):
            upstream_ok = False
        if d.get("live_drift"):
            d["gate0_restore_sql"] = gate0_restore_sql(it, d["v3_restore"])
        f = Finding(it, verdict, d, promote_sql(it, d.get("cand_fp", {}).get("status")),
                    rollback_sql(it, d["v3_pin"]))
        out.append(f)
    if verbose:
        print_report(out, cur)
    return out


def summary(findings: list, cur=None) -> dict:
    blocking = [f for f in findings if f.verdict not in ("READY", "POST_CUTOVER", "REPORT_ONLY", "SKIPPED_CONDITIONAL")]
    return {
        "items": len(findings),
        "conditional_skips": [f.item.live for f in findings if f.verdict == "SKIPPED_CONDITIONAL"],
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
        print(f"[{f.item.step}] {f.item.live:<30} {f.verdict:<18} v3_pin={d.get('v3_pin')} v3_restore={d.get('v3_restore')} "
              f"live_dv={d.get('live_data_ver')} "
              f"draft_pin={d.get('draft_pin')}({d.get('draft_status')}) cand_dv={d.get('cand_data_ver')} "
              f"comments={d.get('v3_comment_rows')} gates={d.get('open_gate_tasks')} "
              f"live_fp={d.get('live_fp', {}).get('status')} cand_fp={d.get('cand_fp', {}).get('status')}")
        for s in f.sql:
            print("      WOULD RUN:", s)
        for s in f.rollback_sql:
            print("      ROLLBACK :", s)
        for s in d.get("gate0_restore_sql", []):
            print("      GATE-0   :", s)
    for p in POST_STEPS:
        print("   POST:", p)
    sp = next((f for f in findings if f.item.action == "conditional_promote"), None)
    sp_met = bool(sp and sp.verdict != "SKIPPED_CONDITIONAL")
    for s in v4_comment_snapshot_sql(promoted_tables(include_conditional=sp_met)):
        print("   V4 COMMENT SNAPSHOT WOULD RUN:", s[:200] + ("..." if len(s) > 200 else ""))
    if sp is not None and not sp_met:
        print("   LOG:", sp.details.get("condition", {}).get("log"))
    pk = pk_fk_plan(service_path_promoted=sp_met)
    print(f"   PK/FK ({pk['source']}): after_swap={len(pk['after_swap'])} deferred={len(pk['deferred'])} "
          f"skipped={len(pk['skipped'])} deferred_tables={pk['deferred_tables']}")
    for c in checklist_status(cur):
        open_g = [k for k, v in c["gates"].items() if v != "completed"]
        print(f"   CHECK {c['order']:>2} {c['phase']:<7} {c['owner']:<15} {'DONE' if c['done'] else 'OPEN'}  "
              f"{c['action']}  open_gates={open_g}")
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
