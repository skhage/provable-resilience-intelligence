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
