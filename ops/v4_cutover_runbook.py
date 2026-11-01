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

P68-DEVOPS-RUNBOOK-PARTIAL-CUTOVER-B (DEC-PRI-V4-073-SECOND-MISS-PARTIAL-CUTOVER, id 41, option b): with
partial_cutover=True (DEFAULT OFF) the PARTIAL_KEEP_V3 v4 promotes/repoints are SKIPPED (P69 / DEC id 42
expanded the list from HSI, span_risk_predictions, resilience_score_snapshot to 11 objects; v4-only
objects with no v3 live are DEFERRED_V4_1, kept v3 views are not repointed). Their v3 live tables stay the source (PROVISIONAL), and
each one must pass the v3 fingerprint gate (fail closed). execute() also requires id 41 to be 'decided'.

P71-DEVOPS-RUNBOOK-B0-BRIDGE-DEC44 (DEC-PRI-V4-PARTIAL-SPAN-GRAIN-BRIDGE, id 44): in partial mode a b0 step runs
before (b). It verifies (read-only) span_bb_route_bridge and the FK gate consumer.span_id IN (span_v4 UNION
bridge.bb_span_id) for the 7 BRIDGE_FK_CONSUMERS (expected 0 orphans), and fails closed otherwise.
optical_anomaly_detection and span_risk_inference_log join PARTIAL_KEEP_V3 as non-runbook FK consumers.

P73-DEVOPS-FULL-MODE-BRIDGE-CONSUMERS (DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES, id 45): the bridge is kept in BOTH
modes. In FULL mode b0 also runs before (b). Its FK gate covers the v3 tables that still hold BB-* keys after a
full swap: optical_anomaly_detection and span_risk_inference_log (stay v3 PROVISIONAL behind the v3 fingerprint
gate; re-keying is v4.1 ML scope), plus service_path while its DEC-39 conditional promote is SKIPPED.
BUG-QA-102: a non-READY b0 makes every later promote/repoint WAITS_UPSTREAM (it no longer stays READY).

BUG-QA-106 (rollback readability): Delta measures time-travel retention from the TARGET version's own commit
timestamp. Once a version is no longer LATEST and its commit is >168h old, reads fail with
DELTA_UNSUPPORTED_TIME_TRAVEL_BEYOND_DELETED_FILE_RETENTION_DURATION. Every v3 live table's LATEST commit is already
>168h old, so a time-travel RESTORE to the pre-swap version would fail closed with no recovery path. ROLLBACK
therefore restores from a fingerprint-gated DEEP CLONE backup <live>__v3_rollback, taken immediately before each
swap (option A; DEC-43 keeps the 7-day retention). dry_run reports rollback_ready per promote item (non-READY is
blocking) and probes the gate-0 manifest restore_version readability (GATE0 unreadable fails closed).

P79-DEVOPS-PIN-COMMIT-FREEZE-GUARD (DP P71 probe): 39 of 52 manifest pins are readable ONLY because restore_version
is still the LATEST version and its commit is >168h old. ANY commit on such a table (COMMENT ON, ALTER TABLE ... SET
TAGS / TBLPROPERTIES / CHANGE COLUMN, OPTIMIZE, incl. Predictive Optimization auto-OPTIMIZE) makes the pin unreadable
at once (what happened to HSI v3 v23 and HSI v4 v33). pin_commit_guard(spark) classifies every pin read-only;
check_commit(sql, guard) / assert_commit_allowed(...) BLOCK any statement that commits to a PIN_LATEST_ONLY table
until its DEEP CLONE backup <name>__v3_rollback (DEC-46) exists. pin_backup_sql(guard) prints (never runs) those
backups. dry_run reports the guard (non-blocking for the cutover itself: backup_sql() runs before every swap).

Usage (notebook, read-only):
    import sys; sys.path.append('<project root>/ops')
    import v4_cutover_runbook as rb
    report = rb.dry_run(spark, lakebase_cursor)   # prints plan + verdict
    report = rb.dry_run(spark, lakebase_cursor, partial_cutover=True)   # DEC-41 option (b) preview
"""
from __future__ import annotations

import os
import re
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
# BUG-QA-106: time-travel-free rollback (option A).
RETENTION_HOURS = 168  # default delta.deletedFileRetentionDuration (DEC-43: no TBLPROPERTIES change)
ROLLBACK_DECISION = "DEC-PRI-V4-ROLLBACK-DEEP-CLONE-BACKUP"  # id 46
ROLLBACK_BACKUP_SUFFIX = "__v3_rollback"
TAG_GATE_TASK = "P4-ADD-TAG-VALUE"
TAG_KEY, TAG_VALUE = "telco_project", "provable_resilience_intelligence"
ROLLBACK_OK = ("ROLLBACK_READY_CLONE", "ROLLBACK_DROP_NEW")
_TIME_TRAVEL_TOKENS = ("VERSION AS OF", "TIMESTAMP AS OF")  # tt-scan tokens

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
    backup_sql: list = field(default_factory=list)  # BUG-QA-106: pre-swap DEEP CLONE backup


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


def latest_commit_age_h(spark, name: str):
    """BUG-QA-106: hours since the LATEST commit (once superseded, that version expires at RETENTION_HOURS)."""
    try:
        r = spark.sql(f"DESCRIBE HISTORY {FQ}.`{name}` LIMIT 1").select("timestamp").first()
        n = spark.sql("SELECT current_timestamp() AS now").first().now
        return round((n - r.timestamp).total_seconds() / 3600, 1)
    except Exception:  # noqa: BLE001 - informational only
        return None


def version_readable(spark, name: str, version) -> dict:
    """BUG-QA-106: read-only probe that the Delta version can still be time-travelled (gate-0 restore target)."""
    if version is None:
        return {"readable": False, "error": "no restore_version"}
    try:
        spark.sql(f"SELECT 1 FROM {FQ}.`{name}` VERSION AS OF {int(version)} LIMIT 1").collect()  # readability probe
        return {"readable": True}
    except Exception as e:  # noqa: BLE001 - fail closed
        return {"readable": False, "error": str(e)[:200]}


def restore_version_audit(spark) -> dict:
    """BUG-QA-106 acceptance: probe every v3 manifest row that has a restore_version. Read-only."""
    out = {}
    for name, row in _manifest(spark, V3).items():
        if row.restore_version is not None:
            out[name] = {"restore_version": int(row.restore_version), **version_readable(spark, name, row.restore_version)}
    return out


# P79-DEVOPS-PIN-COMMIT-FREEZE-GUARD: block/warn on commits to latest-only pinned tables until DEC-46 backups exist.
PIN_GUARD_MANIFESTS = (V3, V4_DRAFT)
PIN_WARN_HOURS = 120  # DP P71: pins older than ~120h are "at risk"
PIN_BLOCK = "BLOCK"
PIN_WARN = "WARN"
PIN_ALLOW = "ALLOW"


def pin_risk(restore_version, latest_version, restore_age_h, backed_up: bool = False) -> dict:
    """Pure, fail-closed classification of ONE manifest pin.

    PIN_EXPIRED             - restore_version superseded and its commit >168h old: already unreadable
    PIN_LATEST_ONLY         - restore_version == LATEST and >168h old: the NEXT commit makes it unreadable at once
    PIN_SUPERSEDED_EXPIRING - superseded, still readable for (168 - age) hours
    PIN_OK                  - LATEST and <=168h old (becomes LATEST_ONLY after expires_in_h)
    PIN_UNKNOWN             - missing version/age (treated like LATEST_ONLY: commits are blocked)
    commit_guard: BLOCK (LATEST_ONLY/UNKNOWN without backup), WARN (backed up, expired, or age > PIN_WARN_HOURS), ALLOW.
    """
    if restore_version is None or latest_version is None or restore_age_h is None:
        status = "PIN_UNKNOWN"
        expires = None
    else:
        expires = round(RETENTION_HOURS - restore_age_h, 1)
        is_latest = int(restore_version) == int(latest_version)
        if restore_age_h > RETENTION_HOURS:
            status = "PIN_LATEST_ONLY" if is_latest else "PIN_EXPIRED"
        else:
            status = "PIN_OK" if is_latest else "PIN_SUPERSEDED_EXPIRING"
    if status in ("PIN_LATEST_ONLY", "PIN_UNKNOWN"):
        guard = PIN_WARN if backed_up else PIN_BLOCK
    elif status == "PIN_EXPIRED" or (restore_age_h is not None and restore_age_h > PIN_WARN_HOURS):
        guard = PIN_WARN
    else:
        guard = PIN_ALLOW
    return {"status": status, "commit_guard": guard, "expires_in_h": expires, "backed_up": bool(backed_up)}


def _po_status(spark, name: str):
    """Predictive Optimization (auto-OPTIMIZE/VACUUM commits) for one table; informational only."""
    try:
        for r in spark.sql(f"DESCRIBE TABLE EXTENDED {FQ}.`{name}`").collect():
            if (r.col_name or "").strip().lower() == "predictive optimization":
                return str(r.data_type)
    except Exception:  # noqa: BLE001 - informational only
        return None
    return None


def pin_commit_guard(spark, objs: dict | None = None, manifests=PIN_GUARD_MANIFESTS, check_po: bool = True) -> dict:
    """Read-only (DESCRIBE HISTORY / information_schema / manifest SELECT). Classifies every manifest pin."""
    objs = objs if objs is not None else _objects(spark)
    now = spark.sql("SELECT current_timestamp() AS now").first().now
    pins, by_object, po = {}, {}, {}
    rank = {PIN_ALLOW: 0, PIN_WARN: 1, PIN_BLOCK: 2}
    for mv in manifests:
        for name, row in _manifest(spark, mv).items():
            if row.restore_version is None:
                continue
            latest = age = None
            try:
                hist = spark.sql(f"DESCRIBE HISTORY {FQ}.`{name}`").select("version", "timestamp").collect()
                latest = max(h.version for h in hist)
                ts = {h.version: h.timestamp for h in hist}.get(int(row.restore_version))
                age = round((now - ts).total_seconds() / 3600, 1) if ts is not None else None
            except Exception:  # noqa: BLE001 - fail closed (PIN_UNKNOWN -> BLOCK)
                pass
            r = pin_risk(row.restore_version, latest, age, rollback_backup_name(name) in objs)
            r.update(manifest_version=mv, object_name=name, restore_version=int(row.restore_version),
                     latest_version=latest, restore_age_h=age)
            pins[(mv, name)] = r
            if name not in by_object or rank[r["commit_guard"]] > rank[by_object[name]["commit_guard"]]:
                by_object[name] = r
    if check_po:
        po = {n: _po_status(spark, n) for n in by_object}
    return {
        "pins": pins,
        "by_object": by_object,
        "latest_only": sorted(k[1] for k, v in pins.items() if v["status"] == "PIN_LATEST_ONLY"),
        "commit_blocked": sorted(n for n, v in by_object.items() if v["commit_guard"] == PIN_BLOCK),
        "expired": sorted(k[1] for k, v in pins.items() if v["status"] == "PIN_EXPIRED"),
        "predictive_optimization": po,
        "po_enabled": sorted(n for n, s in po.items() if s and s.upper().startswith("ENABLE")),
    }


# P79 commit-target parser lives in the plan-builders section (it names write verbs; read helpers stay write-free).


def _statements(sql: str) -> list:
    text = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


def commit_targets(sql: str) -> list:
    """Tables in THIS schema that the SQL would commit to (unqualified names resolve to this schema)."""
    out = []
    for stmt in _statements(sql):
        for rx, idx in _COMMIT_RES:
            m = rx.match(stmt)
            if not m:
                continue
            parts = [p.strip("`").lower() for p in re.findall(r"`[^`]+`|[\w$]+", m.group(1))]
            tbl = parts[:-1] if idx == -2 else parts
            qual = tbl[:-1]
            if tbl and (qual in ([], [SCHEMA], [CATALOG, SCHEMA])):
                out.append(tbl[-1])
            break
    return sorted(set(out))


def check_commit(sql: str, guard: dict) -> dict:
    """Pure. BLOCK if any target is a latest-only pin with no DEC-46 backup; WARN if at risk; else ALLOW."""
    targets = commit_targets(sql)
    hits = {t: guard["by_object"][t] for t in targets if t in guard.get("by_object", {})}
    verdicts = {v["commit_guard"] for v in hits.values()}
    verdict = PIN_BLOCK if PIN_BLOCK in verdicts else PIN_WARN if PIN_WARN in verdicts else PIN_ALLOW
    blocked = sorted(t for t, v in hits.items() if v["commit_guard"] == PIN_BLOCK)
    return {"verdict": verdict, "targets": targets, "blocked": blocked,
            "warned": sorted(t for t, v in hits.items() if v["commit_guard"] == PIN_WARN),
            "remedy": pin_backup_sql({"by_object": {t: hits[t] for t in blocked}})}


class PinCommitBlocked(RuntimeError):
    pass


def assert_commit_allowed(spark, sql: str, guard: dict | None = None) -> dict:
    """Call BEFORE any COMMENT ON / SET TAGS / ALTER / OPTIMIZE on this schema. Raises on BLOCK. Read-only."""
    guard = guard if guard is not None else pin_commit_guard(spark, check_po=False)
    res = check_commit(sql, guard)
    if res["verdict"] == PIN_BLOCK:
        raise PinCommitBlocked(f"P79 pin guard: commit to latest-only pinned {res['blocked']} needs DEC-46 DEEP CLONE "
                               f"backup first: {res['remedy']}")
    return res


def pin_backup_sql(guard: dict) -> list:
    """Text only (never executed here): DEC-46 DEEP CLONE backups that lift the guard for every BLOCKed object."""
    out = []
    for name, v in sorted(guard.get("by_object", {}).items()):
        if v["commit_guard"] != PIN_BLOCK:
            continue
        bak = f"{FQ}.`{rollback_backup_name(name)}`"
        out += [f"CREATE OR REPLACE TABLE {bak} DEEP CLONE {FQ}.`{name}`  -- P79/DEC-46 pre-commit backup "
                f"(pin v{v.get('restore_version')}, {v.get('restore_age_h')}h)",
                f"-- verify (fail closed): fingerprint(spark, '{rollback_backup_name(name)}') == {FP_GATE_TABLE} "
                f"'{v.get('manifest_version')}' baseline of {name}"]
    return out


def print_pin_guard(guard: dict) -> None:
    print(f"   PIN GUARD (P79): pins={len(guard['pins'])} latest_only={len(guard['latest_only'])} "
          f"commit_blocked={len(guard['commit_blocked'])} expired={len(guard['expired'])} "
          f"predictive_optimization_enabled={len(guard['po_enabled'])}")
    for n in guard["commit_blocked"]:
        v = guard["by_object"][n]
        print(f"      COMMIT BLOCKED: {n:<34} {v['manifest_version']} rv={v['restore_version']} "
              f"latest={v['latest_version']} age={v['restore_age_h']}h")


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


def rollback_backup_name(live: str) -> str:
    return live + ROLLBACK_BACKUP_SUFFIX


def backup_sql(item: Item, v3_pin) -> list:
    """BUG-QA-106 / DEC-46 option A: time-travel-free rollback source, taken right before the swap. Text only."""
    if v3_pin is None or item.action not in ("promote", "conditional_promote"):
        return []
    live, bak = f"{FQ}.`{item.live}`", f"{FQ}.`{rollback_backup_name(item.live)}`"
    return [
        "-- PRE-SWAP BACKUP (BUG-QA-106, fail closed): run after the FINGERPRINT GATE and before CREATE OR REPLACE",
        f"CREATE OR REPLACE TABLE {bak} DEEP CLONE {live}",
        f"-- tag (DEC-46: only once {TAG_GATE_TASK} lands): ALTER TABLE {bak} SET TAGS ('{TAG_KEY}' = '{TAG_VALUE}')",
        f"-- verify (fail closed): fingerprint(spark, '{rollback_backup_name(item.live)}') == {FP_GATE_TABLE} '{V3}' "
        f"baseline of {item.live}; else ABORT this swap (do not run CREATE OR REPLACE on {item.live})",
        f"-- keep {bak} until FREEZE-v4 capture; drop at v4.1 cleanup",
    ]


def rollback_sql(item: Item, v3_pin) -> list:
    live = f"{FQ}.`{item.live}`"
    if v3_pin is None:
        if item.action in ("promote", "conditional_promote"):
            return [f"DROP TABLE IF EXISTS {live}  -- new in v4, no v3 pin"]
        return [f"-- {live}: restore previous view definition from v3 (no data pin)"]
    if item.action not in ("promote", "conditional_promote"):
        return [f"-- {live}: restore previous view definition from v3 (no data pin)"]
    # BUG-QA-106: NO time travel. The pre-swap version becomes unreadable the moment the swap commits, because its
    # own commit is already >168h old. Restore from the fingerprint-verified DEEP CLONE taken by backup_sql().
    bak = f"{FQ}.`{rollback_backup_name(item.live)}`"
    return [
        f"CREATE OR REPLACE TABLE {live} DEEP CLONE {bak}  -- BUG-QA-106 clone rollback; manifest v{v3_pin} is "
        "informational only",
        f"-- verify (fail closed): fingerprint(spark, '{item.live}') == {FP_GATE_TABLE} '{V3}' baseline",
        f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
    ]


def uses_time_travel(statements: list) -> bool:
    return any(t in s.upper() for s in statements for t in _TIME_TRAVEL_TOKENS)


def rollback_readiness(item: Item, v3_pin, live_type, rollback: list, age_h=None) -> dict:
    """BUG-QA-106: pure, fail-closed readiness of the ROLLBACK plan for one promote item."""
    if item.action not in ("promote", "conditional_promote"):
        return {"status": "N/A"}
    info = {"live_latest_commit_age_h": age_h,
            "time_travel_rollback_would_fail": None if age_h is None else age_h > RETENTION_HOURS}
    if uses_time_travel(rollback):
        return {"status": "ROLLBACK_TIME_TRAVEL", **info}
    if v3_pin is None:
        return {"status": "ROLLBACK_DROP_NEW", **info}
    if live_type != "MANAGED":
        return {"status": "ROLLBACK_NO_LIVE", **info}
    return {"status": "ROLLBACK_READY_CLONE", "backup": rollback_backup_name(item.live), **info}


def gate0_restore_sql(item: Item, restore_version, readable=None, backup_exists: bool = False) -> list:
    """P67-DE-RUNBOOK-RESTORE-VERSION (BUG-QA-095): gate-0 restore of a v3 FROZEN live table whose fingerprint
    drifted BEFORE the swap (verdict V3_FP_*). Target = demo_freeze_manifest.restore_version (readable Delta version),
    never delta_version (data-lineage pin, may be past the 7-day retention). Text builder only; never executed here."""
    live = f"{FQ}.`{item.live}`"
    if restore_version is None:
        return [f"-- {live}: no manifest restore_version; gate 0 cannot restore, escalate to @pm (fail closed)"]
    if readable is False and backup_exists:  # P79: DEC-46 backup taken while the pin was still LATEST
        bak = f"{FQ}.`{rollback_backup_name(item.live)}`"
        return [
            f"CREATE OR REPLACE TABLE {live} DEEP CLONE {bak}  -- gate 0 (P79): restore_version "
            f"{int(restore_version)} not time-travelable; restore from DEC-46 backup",
            f"-- verify (fail closed): fingerprint(spark, '{item.live}') == {FP_GATE_TABLE} '{V3}' baseline",
            f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
        ]
    if readable is False:  # BUG-QA-106: probed and not time-travelable
        return [f"-- {live}: manifest restore_version {int(restore_version)} is NOT time-travelable (BUG-QA-106); "
                "gate 0 cannot restore, escalate to @pm (fail closed)"]
    return [
        f"RESTORE TABLE {live} TO VERSION AS OF {int(restore_version)}  -- gate 0: manifest restore_version (BUG-QA-095)",
        f"-- verify (fail closed): fingerprint(spark, '{item.live}') == {FP_GATE_TABLE} '{V3}' baseline",
        f"-- re-apply comments from freeze_v3_comment_snapshot WHERE table_name='{item.live}'",
    ]


# P79: statements that create a Delta commit on their target table (pure text parsing; nothing is executed).
_ID = r"((?:`[^`]+`|[\w$]+)(?:\s*\.\s*(?:`[^`]+`|[\w$]+))*)"
# (regex, which identifier part is the table: -1 = last, -2 = second-to-last for COLUMN targets)
_COMMIT_RES = (
    (re.compile(r"COMMENT\s+ON\s+COLUMN\s+" + _ID, re.I), -2),
    (re.compile(r"(?:UN)?SET\s+TAGS?\s+ON\s+COLUMN\s+" + _ID, re.I), -2),
    (re.compile(r"COMMENT\s+ON\s+TABLE\s+" + _ID, re.I), -1),
    (re.compile(r"(?:UN)?SET\s+TAGS?\s+ON\s+TABLE\s+" + _ID, re.I), -1),
    (re.compile(r"ALTER\s+TABLE\s+" + _ID, re.I), -1),
    (re.compile(r"(?:OPTIMIZE|VACUUM|REORG\s+TABLE|ANALYZE\s+TABLE|TRUNCATE\s+TABLE|DELETE\s+FROM|MERGE\s+INTO|UPDATE"
                r"|INSERT\s+(?:INTO|OVERWRITE)(?:\s+TABLE)?|RESTORE(?:\s+TABLE)?|CREATE\s+OR\s+REPLACE\s+TABLE"
                r"|REPLACE\s+TABLE)\s+" + _ID, re.I), -1),
)


# P60-DEVOPS-RUNBOOK-V4-COMMENT-SNAPSHOT: v4 comment snapshot + PK/FK placement. Text builders only.
V4_COMMENT_SNAPSHOT = "freeze_v4_comment_snapshot"
V3_COMMENT_SNAPSHOT = "freeze_v3_comment_snapshot"
COMMENT_SNAPSHOT_COLUMNS = ("manifest_version", "table_name", "column_name", "ordinal_position",
                            "comment_level", "comment", "reapply_sql", "snapshot_ts")
PK_FK_DDL_PATH = "runbooks/P43_v4_pk_fk_constraints.sql"  # @data-engineer P43-DE-V4-PK-FK-CONSTRAINTS


def promoted_tables(include_conditional: bool = False, partial_cutover: bool = False) -> list:
    """Managed live tables replaced by the swap (views/regenerated/report objects excluded).

    Conditional promotes (service_path, P63) count only when include_conditional=True, i.e. when
    service_path_condition() is met at cutover time. P68: partial_cutover=True drops PARTIAL_KEEP_V3
    (they stay v3 live, so no v4 comment snapshot and no AFTER_SWAP constraints for them).
    """
    acts = ("promote", "conditional_promote") if include_conditional else ("promote",)
    return [i.live for i in RUNBOOK if i.action in acts and not (partial_cutover and i.live in PARTIAL_KEEP_V3)]


# P68-DEVOPS-RUNBOOK-PARTIAL-CUTOVER-B: DEC-PRI-V4-073-SECOND-MISS-PARTIAL-CUTOVER (id 41) option (b).
# OFF by default. If the CEO has not run the BUG-QA-073 HSI re-derive + P36 rescore writes by 11-01 23:59Z,
# the 11-02 cutover promotes only the non-HSI v4 objects. These three keep the v3 live table as the source,
# labelled PROVISIONAL, and move to v4.1. Each kept table must pass the v3 fingerprint gate (fail closed).
PARTIAL_DECISION = "DEC-PRI-V4-073-SECOND-MISS-PARTIAL-CUTOVER"
PARTIAL_KEEP_V3_ITEMS = (  # RUNBOOK items whose v4 promote/repoint is skipped in partial mode
    "hazard_span_intersection", "span_risk_predictions", "resilience_score_snapshot",
    # P69-DEVOPS-PARTIAL-KEEP-V3-EXPAND (DEC-PRI-V4-PARTIAL-KEEP-V3-EXPAND, id 42): every object whose v4
    # build is gated on BUG-QA-073 or P36 stays on v3 in partial mode.
    "hazard_span_proximity", "span_hazard_features", "hazard_proximity_count",  # HSI-derived
    "proactive_action",        # moved to v4.1 by DEC-41
    "path_diversity_conduit",  # BUG-QA-084 is P36-gated
    "diversity_coverage",      # P51-DA is P36-gated
    "revenue_at_risk", "mv_mrc_protected",  # WAITS_UPSTREAM on the above
)
# P71-DEVOPS-RUNBOOK-B0-BRIDGE-DEC44 (DEC-PRI-V4-PARTIAL-SPAN-GRAIN-BRIDGE, id 44, item 3): v3 tables that are NOT
# runbook items but also orphan on the 92 BB-* span keys after step (b). They stay v3 (PROVISIONAL) behind the
# v3 fingerprint gate and are covered by the b0 bridge FK gate.
PARTIAL_KEEP_V3_FK_CONSUMERS = ("optical_anomaly_detection", "span_risk_inference_log")
PARTIAL_KEEP_V3 = PARTIAL_KEEP_V3_ITEMS + PARTIAL_KEEP_V3_FK_CONSUMERS
PARTIAL_EXPAND_DECISION = "DEC-PRI-V4-PARTIAL-KEEP-V3-EXPAND"
PARTIAL_VERDICT = "KEPT_V3_PROVISIONAL"
# P69: a kept object that is new in v4 (no v3 live object AND not in the v3 manifest) has nothing to keep;
# its v4 promote/repoint is simply deferred to v4.1. Non-blocking. A v3-manifest object whose live object is
# missing still fails closed (V3_FP_NO_LIVE).
PARTIAL_DEFERRED_VERDICT = "DEFERRED_V4_1"
PARTIAL_OK_VERDICTS = (PARTIAL_VERDICT, PARTIAL_DEFERRED_VERDICT)
_VIEW_TYPES = ("VIEW", "METRIC_VIEW", "MATERIALIZED_VIEW")


def partial_keep_verdict(item: Item, d: dict) -> str | None:
    """Pure: verdict for a PARTIAL_KEEP_V3 item in partial mode, else None. Only FP_PASS on the v3 live
    table yields KEPT_V3_PROVISIONAL; a missing live table, missing baseline or mismatch fails closed."""
    if item.live not in PARTIAL_KEEP_V3:
        return None
    live_type, in_v3 = d.get("live_type"), d.get("v3_status", "NOT_IN_V3") != "NOT_IN_V3"
    if live_type is None and not in_v3:
        return PARTIAL_DEFERRED_VERDICT  # P69: v4-only object, nothing live to keep
    if item.action == "repoint_view" and live_type in _VIEW_TYPES and in_v3:
        # P69: the v3 view is simply not repointed. Views carry no data fingerprint; their v3 sources are
        # themselves FP-gated (promoted-and-gated or kept-and-gated).
        return PARTIAL_VERDICT
    if live_type != "MANAGED" or not in_v3:
        return "V3_FP_NO_LIVE"
    st = d.get("live_fp", {}).get("status", "FP_NO_BASELINE")
    return PARTIAL_VERDICT if st == "FP_PASS" else "V3_FP_" + st[3:]


def partial_sql(item: Item, partial_cutover: bool = True) -> list:
    """Plan text for a kept v3 table (partial mode, or a P73 full-mode FK consumer). Comments only."""
    what = (f"{item.candidate} is NOT promoted" if item.candidate
            else f"no v4 candidate by design (FK consumer, {bridge_decision(partial_cutover)})")
    mode = f"PARTIAL CUTOVER ({PARTIAL_DECISION})" if partial_cutover else f"FULL CUTOVER KEEP_V3 ({BRIDGE_FULL_DECISION})"
    return [
        f"-- {mode}: {what}; v3 {item.live} stays live "
        "(PROVISIONAL in the v4 manifest and UI/Genie copy; promote in v4.1 after the CEO writes)",
        f"-- FINGERPRINT GATE ({FP_DECISION}, fail closed): fingerprint_gate(spark, '{item.live}', '{V3}') "
        "must be FP_PASS before the swap window and again after it",
    ]


# P71-DEVOPS-RUNBOOK-B0-BRIDGE-DEC44: DEC-PRI-V4-PARTIAL-SPAN-GRAIN-BRIDGE (id 44, option E).
# Partial mode only. Step (b) swaps physical_resource_span in place, so the 92 v3 BB-* parents disappear and the
# KEEP_V3 consumers (plus service_path, DEC-39 SKIPPED_CONDITIONAL) would orphan 32,502 rows. Step b0 runs BEFORE (b):
# it verifies (never writes) @data-engineer's span_bb_route_bridge and the FK gate
#   consumer.span_id IN (span_v4 UNION bridge.bb_span_id)  -> expected 0 orphans.
# Fails closed if the bridge is missing, lacks a key column, breaks integrity, or any consumer has an orphan.
# The same gate is re-run against the live physical_resource_span right after the swap. Retired in v4.1.
BRIDGE_DECISION = "DEC-PRI-V4-PARTIAL-SPAN-GRAIN-BRIDGE"
BRIDGE_TABLE = "span_bb_route_bridge"
BRIDGE_STEP = "b0"
BRIDGE_GATES = "P70-DE-SPAN-BB-ROUTE-BRIDGE; P70-QA-VERIFY-PARTIAL-FK-BRIDGE"
BRIDGE_COLUMNS = ("bb_span_id", "bbs_span_id")
SPAN_V4 = _c("physical_resource_span")  # pre-swap source; post-swap use the live physical_resource_span
# Every v3 table that keeps span_id rows after step (b) in partial mode (DP P68 spec section C: 7 tables).
BRIDGE_FK_CONSUMERS = (
    "hazard_span_intersection", "hazard_span_proximity", "span_risk_predictions", "proactive_action",
    "optical_anomaly_detection", "span_risk_inference_log",
    "service_path",  # stays v3 (DEC-39 SKIPPED_CONDITIONAL); 30,769 BB-hop rows
)
# Integrity counters that must all be 0.
BRIDGE_INTEGRITY_ZERO = ("null_keys", "bbs_unmapped", "bb_still_in_span", "parent_route_unbridged")
BRIDGE_ITEM = Item(BRIDGE_STEP, BRIDGE_TABLE, None, BRIDGE_GATES, "bridge_verify")
KEEP_V3_CONSUMER_ITEMS = [Item("keep", t, None, BRIDGE_DECISION, "keep_v3") for t in PARTIAL_KEEP_V3_FK_CONSUMERS]

# P73-DEVOPS-FULL-MODE-BRIDGE-CONSUMERS: DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES (id 45). Full mode keeps the bridge too.
# The 2 historical ML output/log tables are not re-keyed in v4 (v4.1 ML scope, P36/P44-ML); they stay v3, labelled
# PROVISIONAL in the manifest, and their FK gate is measured against span_v4 UNION bridge.
BRIDGE_FULL_DECISION = "DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES"
FULL_KEEP_V3_FK_CONSUMERS = PARTIAL_KEEP_V3_FK_CONSUMERS
FULL_MODE_PROVISIONAL = FULL_KEEP_V3_FK_CONSUMERS  # mirrored by the app's provisional_objects.py (sync test)


def bridge_consumers(partial_cutover: bool = False, service_path_promoted: bool = False) -> tuple:
    """FK consumers the b0 gate must cover. Partial: the 7 DP P68 tables. Full: the 2 kept FK consumers, plus
    service_path while it stays v3 (DEC-39 conditional promote not met; fail closed)."""
    if partial_cutover:
        return BRIDGE_FK_CONSUMERS
    return FULL_KEEP_V3_FK_CONSUMERS + (() if service_path_promoted else ("service_path",))


def bridge_decision(partial_cutover: bool = False) -> str:
    return BRIDGE_DECISION if partial_cutover else BRIDGE_FULL_DECISION


def runbook_items(partial_cutover: bool = False) -> list:
    """RUNBOOK as evaluated by dry_run. Both modes (P73, DEC id 45): b0 right before (b), and the non-runbook
    KEEP_V3 FK consumers appended (v3 fingerprint gate only)."""
    out = []
    for it in RUNBOOK:
        if it.step == "b":
            out.append(BRIDGE_ITEM)
        out.append(it)
    return out + list(KEEP_V3_CONSUMER_ITEMS)


def bridge_orphan_sql(consumer: str, span_source: str = SPAN_V4) -> str:
    """Read-only FK gate for one consumer: rows whose span_id is in neither span_v4 nor bridge.bb_span_id."""
    return (f"SELECT count(*) AS n, count(DISTINCT c.span_id) AS k FROM {FQ}.`{consumer}` c LEFT ANTI JOIN "
            f"(SELECT span_id AS key FROM {FQ}.`{span_source}` UNION SELECT bb_span_id AS key FROM {FQ}.`{BRIDGE_TABLE}`) p "
            "ON c.span_id = p.key WHERE c.span_id IS NOT NULL")


def bridge_integrity_sql(span_source: str = SPAN_V4) -> dict:
    """Read-only bridge integrity checks. Every BRIDGE_INTEGRITY_ZERO counter must be 0."""
    b, s = f"{FQ}.`{BRIDGE_TABLE}`", f"{FQ}.`{span_source}`"
    return {
        "rows": f"SELECT count(*) FROM {b}",
        "bb_keys": f"SELECT count(DISTINCT bb_span_id) FROM {b}",
        "null_keys": f"SELECT count(*) FROM {b} WHERE bb_span_id IS NULL OR bbs_span_id IS NULL",
        "bbs_unmapped": f"SELECT count(*) FROM {b} x LEFT ANTI JOIN {s} y ON x.bbs_span_id = y.span_id",
        "bb_still_in_span": f"SELECT count(DISTINCT x.bb_span_id) FROM {b} x LEFT SEMI JOIN {s} y ON x.bb_span_id = y.span_id",
        "parent_route_unbridged": (f"SELECT count(DISTINCT y.parent_route_id) FROM {s} y LEFT ANTI JOIN {b} x "
                                   "ON y.parent_route_id = x.bb_span_id WHERE y.parent_route_id IS NOT NULL"),
    }


def bridge_check(spark, objs: dict, span_source: str = SPAN_V4, consumers=None) -> dict:
    """Read-only: evaluate the bridge and the FK gate for every consumer table. Never raises.

    consumers=None means the partial-mode set (BRIDGE_FK_CONSUMERS, drift-checked against PARTIAL_KEEP_V3).
    P73 full mode passes bridge_consumers(False, ...); only those tables are watched."""
    partial_set = consumers is None
    consumers = tuple(BRIDGE_FK_CONSUMERS if partial_set else consumers)
    out = {"table": BRIDGE_TABLE, "span_source": span_source, "exists": objs.get(BRIDGE_TABLE) == "MANAGED",
           "consumers": list(consumers),
           "missing_columns": list(BRIDGE_COLUMNS), "missing_consumers": [], "unlisted_consumers": [],
           "integrity": {}, "orphans": {}, "scanned": {}, "scan_exempt": []}
    try:
        watch = sorted((set(PARTIAL_KEEP_V3) if partial_set else set()) | set(consumers) | {BRIDGE_TABLE})
        in_list = ", ".join(f"'{t}'" for t in watch)
        rows = spark.sql(
            f"SELECT c.table_name, c.column_name FROM {CATALOG}.information_schema.columns c "
            f"JOIN {CATALOG}.information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            f"WHERE c.table_schema = '{SCHEMA}' AND t.table_type = 'MANAGED' AND c.table_name IN ({in_list})"
        ).collect()
        cols: dict = {}
        for r in rows:
            cols.setdefault(r.table_name, set()).add(r.column_name.lower())
        out["missing_consumers"] = sorted(t for t in consumers if "span_id" not in cols.get(t, set()))
        # fail-safe: a kept MANAGED v3 table with span_id that the gate does not list
        out["unlisted_consumers"] = sorted(t for t, cs in cols.items() if t != BRIDGE_TABLE and "span_id" in cs
                                           and t not in consumers)
        if not out["exists"]:
            return out
        out["missing_columns"] = [c for c in BRIDGE_COLUMNS if c not in cols.get(BRIDGE_TABLE, set())]
        if out["missing_columns"]:
            return out
        for k, q in bridge_integrity_sql(span_source).items():
            out["integrity"][k] = int(spark.sql(q).first()[0])
        for t in consumers:
            if t in out["missing_consumers"]:
                continue
            r = spark.sql(bridge_orphan_sql(t, span_source)).first()
            out["orphans"][t] = {"rows": int(r.n), "keys": int(r.k)}
        # BUG-QA-104 (b): schema-wide unlisted-consumer scan. The watch list above only covers tables the gate
        # already knows, so in FULL mode the drift check was vacuous. Scan EVERY managed table in the schema with a
        # span_id column that is not a listed consumer, not replaced by the swap (promoted), not the span/bridge
        # itself and not staging (BRIDGE_SCAN_EXEMPT / *_candidate). Any such table with an FK orphan against
        # span_source UNION bridge is a consumer the gate does not list -> BRIDGE_CONSUMER_SET_DRIFT (fail closed).
        skip = (set(consumers) | set(promoted_tables(include_conditional=True, partial_cutover=partial_set))
                | {BRIDGE_TABLE, "physical_resource_span", SPAN_V4} | set(out["unlisted_consumers"]))
        scan = spark.sql(
            f"SELECT c.table_name, c.column_name FROM {CATALOG}.information_schema.columns c "
            f"JOIN {CATALOG}.information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            f"WHERE c.table_schema = '{SCHEMA}' AND t.table_type = 'MANAGED' AND lower(c.column_name) = 'span_id'"
        ).collect()
        for t in sorted({r.table_name for r in scan if r.column_name.lower() == "span_id"} - skip):
            if t in BRIDGE_SCAN_EXEMPT or t.endswith(BRIDGE_SCAN_EXEMPT_SUFFIXES):
                out["scan_exempt"].append(t)
                continue
            r = spark.sql(bridge_orphan_sql(t, span_source)).first()
            out["scanned"][t] = {"rows": int(r.n), "keys": int(r.k)}
            if int(r.n) != 0:
                out["unlisted_consumers"].append(t)
    except Exception as e:  # noqa: BLE001 - fail closed on any read error
        out["error"] = str(e)[:200]
    return out


def bridge_verdict(b: dict | None, decided: bool, gates_open=()) -> str:
    """Pure, fail closed. Only READY lets step (b) proceed in partial mode."""
    if b is None:
        return "BRIDGE_NOT_CHECKED"
    if not decided:
        return "BRIDGE_NOT_DECIDED"
    if not b.get("exists"):
        return "BRIDGE_MISSING"
    if b.get("error"):
        return "BRIDGE_UNREADABLE"
    if b.get("missing_columns"):
        return "BRIDGE_COLUMNS_MISSING"
    if b.get("missing_consumers") or b.get("unlisted_consumers"):
        return "BRIDGE_CONSUMER_SET_DRIFT"
    integ = b.get("integrity", {})
    if any(integ.get(k) is None or integ.get(k) != 0 for k in BRIDGE_INTEGRITY_ZERO):
        return "BRIDGE_INTEGRITY"
    orph = b.get("orphans", {})
    if set(orph) != set(b.get("consumers") or BRIDGE_FK_CONSUMERS):
        return "BRIDGE_FK_UNCHECKED"
    if any(v.get("rows", 1) != 0 for v in orph.values()):
        return "BRIDGE_FK_ORPHANS"
    if gates_open:
        return "GATE_OPEN"
    return "READY"


def bridge_plan_sql(consumers=None, decision: str = BRIDGE_DECISION) -> list:
    """Plan text for b0. Read-only checks only: the runbook never creates or writes the bridge."""
    consumers = tuple(BRIDGE_FK_CONSUMERS if consumers is None else consumers)
    return ([f"-- b0 ({decision}): verify {BRIDGE_TABLE} (built by @data-engineer P70-DE; never written here) "
             "BEFORE step (b); fail closed if missing / integrity != 0 / any FK orphan"]
            + [f"-- integrity {k}: {q}" for k, q in bridge_integrity_sql().items()]
            + [bridge_orphan_sql(t) for t in consumers]
            + ["-- POST-SWAP re-check right after (b): bridge_check(spark, objs, span_source='physical_resource_span') "
               "must give bridge_verdict == READY; else roll back (b)"])


# BUG-QA-104 (b): tables the schema-wide b0 scan does not treat as live FK consumers (listed in scan_exempt).
# *_candidate tables are staging; the promote candidates among them are covered by the (a) candidate FK gate.
BRIDGE_SCAN_EXEMPT = {
    # BUG-DP-072 staging span SOURCE (span_id is its own key; ACC-* legs are not in physical_resource_span yet).
    # It needs its own runbook item before service_path_regen_candidate can be promoted.
    "access_span_regen": "BUG-DP-072 staging span source (ACC-* access legs)",
}
BRIDGE_SCAN_EXEMPT_SUFFIXES = ("_candidate", ROLLBACK_BACKUP_SUFFIX)  # DEC-46: rollback backups are staging


# BUG-QA-104 (a): candidate-side FK gate. In FULL mode a promote candidate whose span_id rows are missing from
# physical_resource_span_v4_candidate would go READY once its pin/FP gates clear and orphan those rows right after
# step (b) (srp_v4: 92 BB-* rows; HSI_v4: 18,495). Every promote candidate with a span_id column must have 0 rows
# outside span_v4 (UNION the bridge only if the live table stays PROVISIONAL, i.e. FULL_MODE_PROVISIONAL).
# Verdict CAND_FK_ORPHANS / CAND_FK_UNREADABLE, fail closed. The span candidate itself is the parent, never checked.
CAND_FK_VERDICTS = ("CAND_FK_ORPHANS", "CAND_FK_UNREADABLE")


def cand_fk_orphan_sql(candidate: str, span_source: str = SPAN_V4, allow_bridge: bool = False) -> str:
    """Read-only: candidate rows whose span_id is not in span_source (UNION bridge.bb_span_id only if allow_bridge)."""
    parent = f"SELECT span_id AS key FROM {FQ}.`{span_source}`"
    if allow_bridge:
        parent += f" UNION SELECT bb_span_id AS key FROM {FQ}.`{BRIDGE_TABLE}`"
    return (f"SELECT count(*) AS n, count(DISTINCT c.span_id) AS k FROM {FQ}.`{candidate}` c LEFT ANTI JOIN "
            f"({parent}) p ON c.span_id = p.key WHERE c.span_id IS NOT NULL")


def cand_fk_targets(items, objs: dict, partial_cutover: bool = False) -> dict:
    """Pure: {candidate: allow_bridge} for every promoted (not kept) candidate that EXISTS in UC, whatever its
    table_type (MANAGED/EXTERNAL/VIEW/MATERIALIZED_VIEW/METRIC_VIEW/...). Span candidate excluded.
    BUG-QA-107: filtering on MANAGED let a VIEW/MV candidate skip the gate (fail-open). A candidate that cannot
    be scanned now fails closed per table (CAND_FK_UNREADABLE). Missing candidates stay MISSING_CANDIDATE."""
    return {it.candidate: it.live in FULL_MODE_PROVISIONAL for it in items
            if it.action in ("promote", "conditional_promote") and it.candidate and it.candidate != SPAN_V4
            and objs.get(it.candidate) is not None and not (partial_cutover and it.live in PARTIAL_KEEP_V3)}


def cand_fk_check(spark, targets: dict, span_source: str = SPAN_V4) -> dict:
    """Read-only: which targets have span_id, and their orphan counts. Never raises (error -> fail closed)."""
    out = {"span_source": span_source, "span_cols": [], "orphans": {}}
    if not targets:
        return out
    try:
        in_list = ", ".join(f"'{t}'" for t in sorted(targets))
        rows = spark.sql(
            f"SELECT c.table_name, c.column_name FROM {CATALOG}.information_schema.columns c "
            f"WHERE c.table_schema = '{SCHEMA}' AND c.table_name IN ({in_list})"
        ).collect()
        out["span_cols"] = sorted({r.table_name for r in rows if r.column_name.lower() == "span_id"} & set(targets))
        for t in out["span_cols"]:
            try:  # BUG-QA-107: per-table, so one unscannable VIEW/MV fails closed without masking the others
                r = spark.sql(cand_fk_orphan_sql(t, span_source, targets[t])).first()
                out["orphans"][t] = {"rows": int(r.n), "keys": int(r.k), "allow_bridge": bool(targets[t])}
            except Exception as e:  # noqa: BLE001 - fail closed for this table
                out["orphans"][t] = {"error": str(e)[:200], "allow_bridge": bool(targets[t])}
    except Exception as e:  # noqa: BLE001 - fail closed on any read error
        out["error"] = str(e)[:200]
    return out


def cand_fk_verdict(c: dict | None, candidate: str) -> str | None:
    """Pure, fail closed. None = no candidate FK issue (no span_id column, or 0 orphans)."""
    if c is None or c.get("error"):
        return "CAND_FK_UNREADABLE"
    if candidate not in c.get("span_cols", ()):
        return None
    o = c.get("orphans", {}).get(candidate)
    if o is None or o.get("error") or "rows" not in o:
        return "CAND_FK_UNREADABLE"
    return "CAND_FK_ORPHANS" if o.get("rows", 1) != 0 else None


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


def pk_fk_plan(text: str | None = None, root: str | None = None, service_path_promoted: bool = False,
               partial_cutover: bool = False) -> dict:
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
    promoted = set(promoted_tables(include_conditional=service_path_promoted, partial_cutover=partial_cutover))
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
def dry_run(spark, cur=None, verbose: bool = True, partial_cutover: bool = False, pin_guard: bool = True) -> list:
    """Read-only evaluation of every runbook item. Executes NO plan SQL.

    partial_cutover=True (P68, DEC-41 option b; default OFF) keeps PARTIAL_KEEP_V3 on v3 behind the v3 fingerprint gate.
    """
    objs, v3, draft, ccount = _objects(spark), _manifest(spark, V3), _manifest(spark, V4_DRAFT), _comment_counts(spark)
    fp_base = _fp_baselines(spark)
    guard = pin_commit_guard(spark, objs) if pin_guard else None  # P79 (informational, non-blocking)
    open_tasks = _open_tasks(cur)
    sp_status = {}
    if cur is not None:
        cur.execute("SELECT task_code, status FROM agent_tasks WHERE task_code = ANY(%s)", (list(SERVICE_PATH_GATES),))
        sp_status = dict(cur.fetchall())
    sp_cond = service_path_condition(objs, sp_status)
    # P71/P73: b0 runs in both modes (DEC id 45); the consumer set depends on the mode.
    bridge = (bridge_check(spark, objs) if partial_cutover
              else bridge_check(spark, objs, consumers=bridge_consumers(False, sp_cond["met"])))
    items = runbook_items(partial_cutover)
    cand_fk = cand_fk_check(spark, cand_fk_targets(items, objs, partial_cutover))  # BUG-QA-104 (a)
    out = []
    upstream_ok = True  # every promote item so far is READY
    bridge_ok = True  # BUG-QA-102: False once b0 is evaluated non-READY
    for it in items:
        d = {"live_type": objs.get(it.live), "cand_type": objs.get(it.candidate) if it.candidate else None}
        v3row = v3.get(it.live)
        d["v3_status"] = v3row.freeze_status if v3row else "NOT_IN_V3"
        d["v3_pin"] = v3row.delta_version if v3row else None  # data-lineage label only
        d["v3_restore"] = v3row.restore_version if v3row else None  # P67: gate-0 restore target
        d["v3_comment_rows"] = ccount.get(it.live, 0)
        d["partial_cutover"] = bool(partial_cutover)
        if guard is not None and it.live in guard["by_object"]:
            d["pin_guard"] = guard["by_object"][it.live]  # P79
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
        # P73: full-mode keep_v3 FK consumers use the same v3 fingerprint gate as partial mode.
        pv = partial_keep_verdict(it, d) if (partial_cutover or it.action == "keep_v3") else None
        if it.action == "bridge_verify":
            d["bridge"] = bridge
            verdict = bridge_verdict(bridge, _decided(cur, bridge_decision(partial_cutover)), gates_open)  # fail closed
        elif pv is not None:
            verdict = pv  # P68: KEPT_V3_PROVISIONAL or V3_FP_* (fail closed)
        elif it.action == "conditional_promote" and not sp_cond["met"]:
            verdict = "SKIPPED_CONDITIONAL"  # non-blocking; upstream_ok unchanged
        elif it.action == "regenerate":
            verdict = "POST_CUTOVER"
        elif it.action == "report_only":
            verdict = "REPORT_ONLY"
        elif d["cand_type"] is None:
            verdict = "MISSING_CANDIDATE"
        elif d.get("live_drift"):
            verdict = "V3_FP_" + d["live_fp"]["status"][3:]  # e.g. V3_FP_MISMATCH (fail closed)
        elif (it.action in ("promote", "conditional_promote") and it.candidate != SPAN_V4
              and (cv := cand_fk_verdict(cand_fk, it.candidate)) is not None):
            d["cand_fk"] = cand_fk.get("orphans", {}).get(it.candidate) or {"error": cand_fk.get("error")}
            verdict = cv  # BUG-QA-104 (a): CAND_FK_ORPHANS / CAND_FK_UNREADABLE (fail closed)
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
        # BUG-QA-106: every promote item needs a time-travel-free rollback (non-READY rollback is blocking).
        rb_plan = rollback_sql(it, d["v3_pin"])
        if it.action in ("promote", "conditional_promote") and pv is None:
            age = latest_commit_age_h(spark, it.live) if d["live_type"] == "MANAGED" else None
            d["rollback_ready"] = rollback_readiness(it, d["v3_pin"], d["live_type"], rb_plan, age)
            if verdict == "READY" and d["rollback_ready"]["status"] not in ROLLBACK_OK:
                verdict = d["rollback_ready"]["status"]
        # BUG-QA-102: nothing after a non-READY b0 may report READY (an operator running READY items one by one
        # would otherwise swap span with no bridge).
        if it.action == "bridge_verify":
            bridge_ok = verdict == "READY"
        elif (not bridge_ok and verdict == "READY"
              and it.action in ("promote", "conditional_promote", "repoint_view")):
            verdict = "WAITS_UPSTREAM"
        if it.action in ("promote", "conditional_promote", "bridge_verify") and verdict not in ("READY", "SKIPPED_CONDITIONAL", *PARTIAL_OK_VERDICTS):
            upstream_ok = False
        if d["live_type"] == "MANAGED" and d["v3_restore"] is not None:
            d["gate0_readable"] = version_readable(spark, it.live, d["v3_restore"])  # BUG-QA-106
        if d.get("live_drift"):
            d["gate0_restore_sql"] = gate0_restore_sql(it, d["v3_restore"], d.get("gate0_readable", {}).get("readable"),
                                                       rollback_backup_name(it.live) in objs)
        if it.action == "bridge_verify":  # P71: read-only verification, nothing to roll back
            f = Finding(it, verdict, d, bridge_plan_sql(bridge.get("consumers"), bridge_decision(partial_cutover)), [])
        elif pv is not None:  # kept on v3: no promote, nothing to roll back
            f = Finding(it, verdict, d, partial_sql(it, partial_cutover), [])
        else:
            f = Finding(it, verdict, d, promote_sql(it, d.get("cand_fp", {}).get("status")), rb_plan,
                        backup_sql(it, d["v3_pin"]))
        out.append(f)
    if verbose:
        print_report(out, cur)
        if guard is not None:
            print_pin_guard(guard)
    return out


def summary(findings: list, cur=None) -> dict:
    blocking = [f for f in findings if f.verdict not in ("READY", "POST_CUTOVER", "REPORT_ONLY", "SKIPPED_CONDITIONAL",
                                                         *PARTIAL_OK_VERDICTS)]
    partial = any(f.details.get("partial_cutover") for f in findings)
    return {
        "items": len(findings),
        "partial_cutover": partial,
        "partial_decision": _decided(cur, PARTIAL_DECISION) if partial else None,
        "kept_v3_provisional": [f.item.live for f in findings if f.verdict == PARTIAL_VERDICT],
        "deferred_v4_1": [f.item.live for f in findings if f.verdict == PARTIAL_DEFERRED_VERDICT],
        "conditional_skips": [f.item.live for f in findings if f.verdict == "SKIPPED_CONDITIONAL"],
        "bridge": next((f.verdict for f in findings if f.item.action == "bridge_verify"), None),
        "bridge_orphans": next((sum(v.get("rows", 0) for v in (f.details.get("bridge") or {}).get("orphans", {}).values())
                                for f in findings if f.item.action == "bridge_verify"), None),
        "ready": sum(f.verdict == "READY" for f in findings),
        "blocking": len(blocking),
        "go_decision": _decided(cur, GO_DECISION),
        "v3_drift": [f.item.live for f in findings if f.details.get("live_drift")],
        "rollback_ready": sum(f.details.get("rollback_ready", {}).get("status") in ROLLBACK_OK for f in findings),
        "rollback_not_ready": [f.item.live for f in findings
                               if f.details.get("rollback_ready", {}).get("status", "N/A") not in (*ROLLBACK_OK, "N/A")],
        "gate0_unreadable": [f.item.live for f in findings if f.details.get("gate0_readable", {}).get("readable") is False],
        # P79: informational (non-blocking for the cutover; backup_sql() precedes every swap)
        "pin_commit_blocked": [f.item.live for f in findings
                               if f.details.get("pin_guard", {}).get("commit_guard") == PIN_BLOCK],
        "cutover_ready": not blocking and _decided(cur, GO_DECISION) and (not partial or _decided(cur, PARTIAL_DECISION)),
    }


def print_report(findings: list, cur=None) -> None:
    partial = any(f.details.get("partial_cutover") for f in findings)
    print(f"PRI v4 cutover DRY RUN (write-disabled) - {len(findings)} items"
          + (f" - PARTIAL ({PARTIAL_DECISION}, option b)" if partial else ""))
    for f in findings:
        d = f.details
        print(f"[{f.item.step}] {f.item.live:<30} {f.verdict:<18} v3_pin={d.get('v3_pin')} v3_restore={d.get('v3_restore')} "
              f"live_dv={d.get('live_data_ver')} "
              f"draft_pin={d.get('draft_pin')}({d.get('draft_status')}) cand_dv={d.get('cand_data_ver')} "
              f"comments={d.get('v3_comment_rows')} gates={d.get('open_gate_tasks')} "
              f"live_fp={d.get('live_fp', {}).get('status')} cand_fp={d.get('cand_fp', {}).get('status')} "
              f"rollback={d.get('rollback_ready', {}).get('status')} "
              f"gate0_readable={d.get('gate0_readable', {}).get('readable')}")
        for s in f.backup_sql:
            print("      BACKUP   :", s)
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
    for s in v4_comment_snapshot_sql(promoted_tables(include_conditional=sp_met, partial_cutover=partial)):
        print("   V4 COMMENT SNAPSHOT WOULD RUN:", s[:200] + ("..." if len(s) > 200 else ""))
    if sp is not None and not sp_met:
        print("   LOG:", sp.details.get("condition", {}).get("log"))
    pk = pk_fk_plan(service_path_promoted=sp_met, partial_cutover=partial)
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


def execute(spark, cur, write_enabled: bool = False, partial_cutover: bool = False):
    """Refuses unless explicitly enabled, env-armed, GO-decided and fully READY.

    P68: partial_cutover=True (default OFF) additionally requires a decided DEC-41 (PARTIAL_DECISION).
    """
    if not write_enabled or os.environ.get("PRI_V4_CUTOVER_WRITE") != "1":
        raise CutoverRefused("write-disabled: pass write_enabled=True AND set PRI_V4_CUTOVER_WRITE=1")
    if not _decided(cur, GO_DECISION):
        raise CutoverRefused(f"no decided {GO_DECISION} row in Lakebase decisions")
    if partial_cutover and not _decided(cur, PARTIAL_DECISION):
        raise CutoverRefused(f"partial cutover needs a decided {PARTIAL_DECISION} row in Lakebase decisions")
    findings = dry_run(spark, cur, verbose=False, partial_cutover=partial_cutover)
    s = summary(findings, cur)
    if not s["cutover_ready"]:
        raise CutoverRefused(f"dry run not READY: {s}")
    raise CutoverRefused("execution intentionally not implemented in P51; @pm must assign the cutover task")
