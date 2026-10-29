"""P51-DEVOPS-V4-CUTOVER-RUNBOOK-DRYRUN: offline checks for ops/v4_cutover_runbook.py (no Spark needed)."""
import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import v4_cutover_runbook as rb  # noqa: E402

SRC = (ROOT / "ops" / "v4_cutover_runbook.py").read_text()


def _pos(live):
    return [i.live for i in rb.RUNBOOK].index(live)


def test_promotion_order_matches_p36_and_dec32():
    steps = [i.step for i in rb.RUNBOOK]
    assert steps == sorted(steps, key=lambda s: (s[0], s)), steps
    assert _pos("physical_resource_conduit") < _pos("physical_resource_span")
    assert _pos("physical_resource_span") < _pos("resource_alarm") < _pos("span_risk_predictions")
    assert _pos("physical_resource_span") < _pos("resource_performance_measure") < _pos("span_risk_predictions")
    assert _pos("hazard_span_intersection") < _pos("span_risk_predictions") < _pos("resilience_score_snapshot")
    assert _pos("resilience_score_snapshot") < _pos("proactive_action")


def test_promote_sql_targets_live_from_pinned_candidate():
    for it in rb.RUNBOOK:
        sql = rb.promote_sql(it, 7)
        writes = [s for s in sql if not s.startswith("--")]
        for s in writes:
            assert s.startswith(f"CREATE OR REPLACE TABLE {rb.FQ}.`{it.live}` AS SELECT * FROM "), s
            assert f"`{it.candidate}` VERSION AS OF 7" in s
        if it.action == "promote":
            assert len(writes) == 1 and any("freeze_v3_comment_snapshot" in s for s in sql)


def test_dry_run_only_issues_read_statements():
    """Every spark.sql literal in the module must be a read (SELECT / DESCRIBE)."""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "sql":
            first = node.args[0]
            text = first.values[0].value if isinstance(first, ast.JoinedStr) else first.value
            assert text.lstrip().upper().startswith(("SELECT", "DESCRIBE")), text
    assert "cur.execute(\"SELECT" in SRC and "INSERT" not in SRC.split("# ---------------------------------------------------------------- read helpers")[1].split("# ---------------------------------------------------------------- plan builders")[0]


def test_execute_refuses_by_default(monkeypatch):
    monkeypatch.delenv("PRI_V4_CUTOVER_WRITE", raising=False)
    with pytest.raises(rb.CutoverRefused):
        rb.execute(spark=None, cur=None)
    with pytest.raises(rb.CutoverRefused):
        rb.execute(spark=None, cur=None, write_enabled=True)
    monkeypatch.setenv("PRI_V4_CUTOVER_WRITE", "1")
    with pytest.raises(rb.CutoverRefused, match="DEC-PRI-V4-CUTOVER-GO"):
        rb.execute(spark=None, cur=None, write_enabled=True)


def test_cutover_checklist_order_p55():
    """P55: CEO writes first, then QA gates + GO, promotion, then post steps; bundle sync last-but-one."""
    orders = [c[0] for c in rb.CHECKLIST]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
    phases = [c[1] for c in rb.CHECKLIST]
    assert phases == sorted(phases, key=["PRE", "PROMOTE", "POST"].index)
    assert rb.CHECKLIST[0][1:3] == ("PRE", "CEO") and "BUG-QA-073" in rb.CHECKLIST[0][4]
    gates = {g for c in rb.CHECKLIST for g in c[4]}
    for code in ("P36-ML-V4-RESCORE-CONDUIT-DIVERSITY", "P43-DE-V4-PK-FK-CONSTRAINTS",
                 "P30-DA-GENIE-MRC-PROTECTED-CUTOVER", "P51-DA-V4-DIVERSITY-COVERAGE-MV",
                 "P43-DEVOPS-BUNDLE-PIPELINE-SYNC"):
        assert code in gates, code
    assert any("PRI_V4_KPIS" in c[3] for c in rb.CHECKLIST if c[1] == "POST")
    assert all("Lumen" not in c[3] for c in rb.CHECKLIST)
    assert rb.checklist_status(None)[0]["gates"] == {"BUG-QA-073": "UNKNOWN"}


def test_bug_qa_082_not_gating_step_c():
    assert all("BUG-QA-082" not in i.owner_gate for i in rb.RUNBOOK if i.step == "c")


def test_data_change_rule():
    assert rb._is_data_change("WRITE") and rb._is_data_change("CREATE OR REPLACE TABLE AS SELECT")
    assert rb._is_data_change("MERGE") and rb._is_data_change("RESTORE")
    for op in ("OPTIMIZE", "VACUUM END", "SET TBLPROPERTIES", "CHANGE COLUMN", "ADD CONSTRAINT"):
        assert not rb._is_data_change(op), op


class _GateCur:
    """Fake Lakebase cursor: only answers the read-only CEO-gate SELECT."""

    def __init__(self, status):
        self.status, self.sql = status, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        assert sql.lstrip().upper().startswith("SELECT"), sql

    def fetchall(self):
        return list(self.status.items())


def test_p57_slip_contingency_paths():
    """P57: path A keeps 10-30; no approval past 10-29 EOD slips to >= 11-02 and never earlier than DEC-33 (+48h/day)."""
    import datetime as dt
    done = {c: "completed" for c in rb.CEO_GATES}
    notdone = {"BUG-QA-073": "in_progress", "P36-ML-V4-RESCORE-CONDUIT-DIVERSITY": "blocked"}
    a = rb.contingency_plan(_GateCur(done), dt.date(2026, 10, 29))
    assert a["path"] == "A" and a["target"] == dt.date(2026, 10, 30)
    p = rb.contingency_plan(_GateCur(notdone), dt.date(2026, 10, 29))
    assert p["path"] == "PENDING" and p["target"] == dt.date(2026, 10, 30)
    b = rb.contingency_plan(_GateCur(notdone), dt.date(2026, 10, 30))
    assert b["path"] == "B" and b["target"] == dt.date(2026, 11, 2) and b["missed_days"] == 1
    assert b["target"] >= rb.rule_target(1) == dt.date(2026, 11, 1)
    late = rb.contingency_plan(_GateCur(notdone), dt.date(2026, 11, 1))
    assert late["target"] == rb.rule_target(3) == dt.date(2026, 11, 5)
    # approval that lands after the deadline still follows the slipped date
    assert rb.contingency_plan(_GateCur(done), dt.date(2026, 10, 30))["path"] == "B"
    assert b["candidate_drop_earliest"] == b["target"] + dt.timedelta(days=rb.AUDIT_HOLD_DAYS)


def test_p57_dated_checklist_covers_all_steps_in_order():
    import datetime as dt
    t = dt.date(2026, 11, 2)
    rows = rb.dated_checklist(t)
    assert [r["order"] for r in rows] == [c[0] for c in rb.CHECKLIST] and len(rows) == 19  # P60: +2 steps
    assert set(rb.STEP_OFFSET_DAYS) == {c[0] for c in rb.CHECKLIST}
    dues = [r["due"] for r in rows]
    assert dues == sorted(dues)
    assert rows[0]["due"] == rows[1]["due"] == dt.date(2026, 11, 1)  # CEO writes EOD T-1
    assert next(r for r in rows if r["order"] == 12)["due"] == t
    assert rb.contingency_plan(None, dt.date(2026, 10, 29))["plan_b"][11]["due"] == t


def test_p57_contingency_is_read_only():
    import datetime as dt
    cur = _GateCur({})
    rb.contingency_plan(cur, dt.date(2026, 10, 31))
    assert len(cur.sql) == 1 and "agent_tasks" in cur.sql[0]
    body = SRC[SRC.index("def contingency_plan"):SRC.index("POST_STEPS = [")]
    for kw in ("INSERT", "UPDATE ", "DELETE", "CREATE", "spark.sql"):
        assert kw not in body, kw


# ---------------------------------------------------------------- P60 v4 comment snapshot + PK/FK placement
def _step(text):
    return next(c for c in rb.CHECKLIST if text in c[3])


def test_p60_v4_comment_snapshot_step_right_after_swap():
    promote = next(c for c in rb.CHECKLIST if c[1] == "PROMOTE")
    snap = _step("freeze_v4_comment_snapshot")
    assert snap[0] == promote[0] + 1 and snap[1] == "POST" and snap[2] == "@devops"
    assert snap[4] == ()  # manual: never auto-DONE when P60 itself completes
    # every other POST DDL step comes after the snapshot
    assert all(c[0] > snap[0] for c in rb.CHECKLIST if c[1] == "POST" and c is not snap)
    assert any("freeze_v4_comment_snapshot" in p for p in rb.POST_STEPS)


def test_p60_pk_fk_after_swap_and_deferred_after_v4_capture():
    snap = _step("freeze_v4_comment_snapshot")
    after = _step("AFTER_SWAP")
    deferred = _step("DEFERRED")
    capture = _step("Capture PRI-DEMO-FREEZE-v4")
    assert "P43-DE-V4-PK-FK-CONSTRAINTS" in after[4] and after[0] == snap[0] + 1
    assert deferred[0] > capture[0]  # v3 must be SUPERSEDED before non-promoted tables are ALTERed


@pytest.mark.parametrize("target", ["2026-10-30", "2026-11-02"])
def test_p60_both_paths_schedule_snapshot_and_constraints(target):
    import datetime as dt
    t = dt.date.fromisoformat(target)
    rows = {r["order"]: r["due"] for r in rb.dated_checklist(t)}
    snap, after, deferred = (_step(s)[0] for s in ("freeze_v4_comment_snapshot", "AFTER_SWAP", "DEFERRED"))
    swap = next(c for c in rb.CHECKLIST if c[1] == "PROMOTE")[0]
    assert rows[swap] == rows[snap] == rows[after] == t  # same day as the swap
    assert rows[deferred] == rows[_step("Capture PRI-DEMO-FREEZE-v4")[0]] == t + dt.timedelta(days=1)
    plan = rb.contingency_plan(None, dt.date(2026, 10, 29))
    key = "plan_a" if t == rb.BASE_TARGET else "plan_b"
    assert next(r for r in plan[key] if r["order"] == snap)["due"] == t


def test_p60_snapshot_sql_mirrors_v3_and_only_writes_v4_snapshot():
    sql = rb.v4_comment_snapshot_sql()
    writes = [s for s in sql if not s.startswith("--")]
    tgt = f"{rb.FQ}.freeze_v4_comment_snapshot"
    assert writes[0].startswith(f"CREATE TABLE IF NOT EXISTS {tgt} (")
    for col in rb.COMMENT_SNAPSHOT_COLUMNS:
        assert f"{col} " in writes[0], col
    assert writes[1] == f"DELETE FROM {tgt} WHERE manifest_version = '{rb.V4}'"
    assert writes[2].startswith(f"INSERT INTO {tgt} SELECT '{rb.V4}'")
    for s in writes:
        assert f"{rb.FQ}.freeze_v3_comment_snapshot" not in s and rb.SUFFIX not in s and "Lumen" not in s
        assert not s.upper().startswith(("CREATE OR REPLACE", "DROP", "ALTER"))
    for t in rb.promoted_tables():
        assert f"'{t}'" in writes[2], t
    assert "unified_shared_risk_group" not in writes[2]  # views are not snapshotted as promoted tables
    assert writes[2].count("information_schema.") == 2  # TABLE + COLUMN rows


_DDL = """
USE SCHEMA provable_resilience_intelligence;
SELECT 'x' AS fk, COUNT(*) FROM service_path; -- pre-flight
ALTER TABLE physical_resource_span ALTER COLUMN span_id SET NOT NULL;
ALTER TABLE geographic_site ALTER COLUMN site_id SET NOT NULL;
ALTER TABLE physical_resource_span ADD CONSTRAINT pk_span PRIMARY KEY (span_id);
ALTER TABLE resource_alarm ADD CONSTRAINT fk_alarm_span FOREIGN KEY (span_id) REFERENCES physical_resource_span (span_id);
ALTER TABLE physical_resource_span ADD CONSTRAINT fk_span_site FOREIGN KEY (site_a_id) REFERENCES geographic_site (site_id);
ALTER TABLE service_path ADD CONSTRAINT fk_path_span FOREIGN KEY (span_id) REFERENCES physical_resource_span (span_id);
"""


def test_p60_pk_fk_plan_never_alters_non_promoted_after_swap():
    p = rb.pk_fk_plan(_DDL)
    assert len(p["after_swap"]) == 3 and len(p["deferred"]) == 3
    assert p["deferred_tables"] == ["geographic_site", "service_path"]
    promoted = set(rb.promoted_tables())
    for s in p["after_swap"]:
        assert "geographic_site" not in s and "service_path" not in s
        assert s.split()[2] in promoted
    # an FK on a promoted child pointing at a v3 FROZEN parent is deferred too
    assert any("fk_span_site" in s for s in p["deferred"])


def test_p60_pk_fk_plan_missing_file_is_empty(tmp_path):
    p = rb.pk_fk_plan(root=str(tmp_path))
    assert p == {"source": None, "after_swap": [], "deferred": [], "deferred_tables": []}
