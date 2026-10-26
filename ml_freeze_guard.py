"""Lakelink Fiber Provable Resilience Intelligence - ML demo write-freeze guard.

Task: P24-ML-FREEZE-WRITE-GUARD (decision DEC-PRI-DEMO-FREEZE-V2).
Prevents scheduled @ml-engineer inference / monitoring runs from writing to
tables that are FROZEN in the latest demo_freeze_manifest version.

Usage (first cell of any ML write step):
    from ml_freeze_guard import assert_writable
    assert_writable(spark, "span_risk_predictions")          # raises if frozen
    assert_writable(spark, "span_risk_predictions", lift_task="P30-ML-...")  # approved re-run

Guarded ML tables: span_risk_predictions, span_risk_inference_log,
model_monitoring_alerts, optical_anomaly_detection (any FROZEN object is guarded).

RESUME (freeze lift) PROCEDURE
1. @pm records a decided row in Lakebase `decisions` with decision_code
   'DEC-PRI-DEMO-FREEZE-LIFT' (full lift) OR assigns a task whose code is passed
   as lift_task (single approved write).
2. Run the ML write (inference refresh / drift baseline reset).
3. @data-planner re-captures the manifest (PRI-DEMO-FREEZE-v<N+1>) for the
   changed tables; @qa re-verifies.
4. Re-enable predictive optimization only after the demo (see note).

NOTE: Predictive Optimization (inherited ENABLE from the metastore) commits
OPTIMIZE on its own (span_risk_inference_log v61, 2026-10-24 05:53 UTC, after
the v2 freeze). Data and row counts are unchanged and VERSION AS OF still works,
but a later VACUUM could remove files needed for restore. Disabling it per
table needs owner approval (ALTER TABLE ... DISABLE PREDICTIVE OPTIMIZATION).
"""

CATALOG_SCHEMA = "cdm_tmforum.provable_resilience_intelligence"
LIFT_DECISION = "DEC-PRI-DEMO-FREEZE-LIFT"


class FrozenTableError(RuntimeError):
    pass


def _frozen_row(spark, table):
    rows = spark.sql(
        f"""
        SELECT manifest_version, delta_version, row_count
        FROM {CATALOG_SCHEMA}.demo_freeze_manifest
        WHERE object_name = :t AND freeze_status = 'FROZEN'
        ORDER BY manifest_version DESC LIMIT 1
        """,
        args={"t": table},
    ).collect()
    return rows[0] if rows else None


def _lift_decided(lakebase_cursor):
    if lakebase_cursor is None:
        return False
    lakebase_cursor.execute(
        "SELECT 1 FROM decisions WHERE decision_code = %s AND status = 'decided'",
        (LIFT_DECISION,),
    )
    return lakebase_cursor.fetchone() is not None


def _task_approved(lakebase_cursor, task_code):
    if lakebase_cursor is None or not task_code:
        return False
    lakebase_cursor.execute(
        "SELECT 1 FROM agent_tasks WHERE task_code = %s AND assigned_by = '@pm' "
        "AND status IN ('open','in_progress')",
        (task_code,),
    )
    return lakebase_cursor.fetchone() is not None


def assert_writable(spark, table, lakebase_cursor=None, lift_task=None):
    """Raise FrozenTableError if `table` is FROZEN and no lift is approved."""
    row = _frozen_row(spark, table)
    if row is None:
        return True
    if _lift_decided(lakebase_cursor) or _task_approved(lakebase_cursor, lift_task):
        print(f"[freeze-guard] {table}: write allowed (lift approved); re-capture manifest after.")
        return True
    raise FrozenTableError(
        f"{CATALOG_SCHEMA}.{table} is FROZEN in {row.manifest_version} "
        f"(delta v{row.delta_version}, {row.row_count} rows). Write skipped. "
        f"See RESUME procedure in ml_freeze_guard.py."
    )
