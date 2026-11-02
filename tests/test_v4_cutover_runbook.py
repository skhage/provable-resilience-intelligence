"""P51-DEVOPS-V4-CUTOVER-RUNBOOK-DRYRUN: offline checks for ops/v4_cutover_runbook.py (no Spark needed)."""
import ast
import pathlib
import re
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


def test_promote_sql_targets_live_from_fingerprint_gated_candidate():
    """P65: promote reads the candidate at its current version (no VERSION AS OF), wrapped by FP gates."""
    for it in rb.RUNBOOK:
        sql = rb.promote_sql(it, "FP_PASS")
        writes = [s for s in sql if not s.startswith("--")]
        for s in writes:
            assert s == f"CREATE OR REPLACE TABLE {rb.FQ}.`{it.live}` AS SELECT * FROM {rb.FQ}.`{it.candidate}`", s
            assert "VERSION AS OF" not in s.upper() and "TIMESTAMP AS OF" not in s.upper()
        if writes:
            i = sql.index(writes[0])
            assert sql[i - 1].startswith("-- FINGERPRINT GATE") and rb.FP_DECISION in sql[i - 1]
            assert sql[i + 1].startswith("-- POST-SWAP CHECK") and rb.FP_GATE_TABLE in sql[i + 1]
        if it.action == "promote":
            assert len(writes) == 1 and any("freeze_v3_comment_snapshot" in s for s in sql)


def test_dry_run_only_issues_read_statements():
    """Every spark.sql literal in the module must be a read (SELECT / DESCRIBE)."""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "sql":
            first = node.args[0]
            if isinstance(first, ast.Call):  # P65: spark.sql(fingerprint_sql(...)); builder checked below
                # P71: bridge_orphan_sql is SELECT-only (test_p71_bridge_sql_is_read_only_and_unions_bridge)
                # BUG-QA-104: cand_fk_orphan_sql is SELECT-only (test_bug_qa_104_cand_fk_sql_read_only)
                assert getattr(first.func, "id", "") in ("fingerprint_sql", "bridge_orphan_sql", "cand_fk_orphan_sql"), \
                    ast.dump(first)
                continue
            if isinstance(first, ast.Name) and first.id == "coverage_q":  # BUG-QA-108: comment-coverage builders
                assert rb.comment_coverage_sql("x").startswith("SELECT")
                assert rb.comment_expectation_sql("x").startswith("SELECT")
                continue
            if isinstance(first, ast.Name):  # P71: only the bridge_integrity_sql() loop variable (all SELECT)
                assert first.id == "q" and "for k, q in bridge_integrity_sql(span_source).items():" in SRC, ast.dump(first)
                assert all(s.startswith("SELECT") for s in rb.bridge_integrity_sql().values())
                continue
            text = first.values[0].value if isinstance(first, ast.JoinedStr) else first.value
            assert text.lstrip().upper().startswith(("SELECT", "DESCRIBE")), text
    assert "cur.execute(\"SELECT" in SRC and "INSERT" not in SRC.split("# ---------------------------------------------------------------- read helpers")[1].split("# ---------------------------------------------------------------- plan builders")[0]


# ---------------------------------------------------------------- P65 fingerprint gates
def test_p65_fingerprint_sql_matches_dp_p58_formula():
    q = rb.fingerprint_sql("customer", ["customer_id", "name"])
    assert q.startswith("SELECT COUNT(*) AS fp_row_count, ") and q.endswith(f"FROM {rb.FQ}.`customer`")
    assert "VERSION AS OF" not in q.upper()
    v1 = "CAST(`customer_id` AS STRING), CAST(`name` AS STRING)"
    v2 = "COALESCE(CAST(`customer_id` AS STRING), '<NULL>'), COALESCE(CAST(`name` AS STRING), '<NULL>')"
    for e, alias in ((v1, "fp_sha2_v1_null_skip"), (v2, "fp_sha2_v2_null_token")):
        assert (f"CAST(SUM(CAST(CONV(SUBSTR(SHA2(CONCAT_WS('|', {e}), 256), 1, 15), 16, 10) AS DECIMAL(38,0))) "
                f"AS STRING) AS {alias}") in q
    assert "2 AS fp_column_count" in q
    with pytest.raises(ValueError):
        rb.fingerprint_sql("x", [])


_BASE = {"gate_status": "PASS", "fp_row_count": 1200, "fp_sha2_v1_null_skip": "683930732249270446323",
         "fp_sha2_v2_null_token": "683930732249270446323", "fp_column_count": 12}


def _act(**kw):
    a = {k: _BASE[k] for k in rb.FP_COMPONENTS}
    a.update(kw)
    return a


def test_p65_compare_fingerprint_fail_closed():
    assert rb.compare_fingerprint(_act(), _BASE)["status"] == "FP_PASS"
    # decimal baseline vs string actual must still compare equal (stored as STRING in the gate table)
    assert rb.compare_fingerprint(_act(fp_sha2_v1_null_skip=683930732249270446323), _BASE)["status"] == "FP_PASS"
    for k, v in (("fp_row_count", 1201), ("fp_sha2_v1_null_skip", "1"), ("fp_sha2_v2_null_token", "1"),
                 ("fp_column_count", 13)):
        r = rb.compare_fingerprint(_act(**{k: v}), _BASE)
        assert r == {"status": "FP_MISMATCH", "mismatched": [k]}, (k, r)
    # v1 alone is not enough: a NULL-shift changes only v2 and must still fail
    assert rb.compare_fingerprint(_act(fp_sha2_v2_null_token="9"), _BASE)["status"] == "FP_MISMATCH"
    assert rb.compare_fingerprint(_act(), None)["status"] == "FP_NO_BASELINE"
    assert rb.compare_fingerprint(None, _BASE)["status"] == "FP_UNREADABLE"
    prov = dict(_BASE, gate_status="PROVISIONAL")
    assert rb.compare_fingerprint(_act(), prov)["status"] == "FP_PROVISIONAL"
    assert rb.compare_fingerprint(_act(), dict(_BASE, gate_status=None))["status"] == "FP_NO_BASELINE"
    assert rb.compare_fingerprint(_act(), dict(_BASE, fp_sha2_v2_null_token=None))["status"] == "FP_MISMATCH"


def test_p65_fingerprint_gate_unreadable_fails_closed():
    class _Boom:
        def sql(self, *a, **k):
            raise RuntimeError("DELTA_UNSUPPORTED_TIME_TRAVEL")
    r = rb.fingerprint_gate(_Boom(), "customer", rb.V3, {(rb.V3, "customer"): _BASE})
    assert r["status"] == "FP_UNREADABLE"
    assert rb.fingerprint_gate(_Boom(), "customer", rb.V3, {})["status"] == "FP_NO_BASELINE"


def test_p65_only_fp_pass_is_non_blocking():
    it = next(i for i in rb.RUNBOOK if i.live == "physical_resource_span")
    for v in ("FP_MISMATCH", "FP_NO_BASELINE", "FP_PROVISIONAL", "FP_UNREADABLE", "V3_FP_MISMATCH"):
        assert rb.summary([rb.Finding(it, v)])["blocking"] == 1, v


def test_p65_no_freeze_pin_time_travel_left_in_runbook():
    """Only the gate-0 RESTORE, its readability probe and the tt-scan token list may mention VERSION AS OF."""
    code = [ln for ln in SRC.splitlines() if "VERSION AS OF" in ln.upper()]
    offenders = [ln for ln in code if "RESTORE TABLE" not in ln and "VERSION AS OF pins" not in ln
                 and "VERSION AS OF freeze pin" not in ln and "readability probe" not in ln
                 and "tt-scan" not in ln]
    assert offenders == [], offenders
    assert "PIN_DRIFT" not in SRC.split("def dry_run")[1]


# ---------------------------------------------------------------- BUG-QA-106 rollback readability
_PROMOTES = [i for i in rb.RUNBOOK if i.action in ("promote", "conditional_promote")]


def test_bug_qa_106_rollback_never_time_travels():
    """ROLLBACK must not depend on a time-travel target (any superseded version >168h old is unreadable)."""
    assert _PROMOTES
    for it in rb.RUNBOOK:
        for pin in (9, None):
            rs = rb.rollback_sql(it, pin)
            assert not rb.uses_time_travel(rs), (it.live, rs)
            assert not any(s.upper().startswith("RESTORE") for s in rs), (it.live, rs)


def test_bug_qa_106_rollback_restores_from_fingerprinted_deep_clone():
    for it in _PROMOTES:
        bak = f"{rb.FQ}.`{it.live}{rb.ROLLBACK_BACKUP_SUFFIX}`"
        live = f"{rb.FQ}.`{it.live}`"
        bs = rb.backup_sql(it, 9)
        writes = [s for s in bs if not s.startswith("--")]
        assert writes == [f"CREATE OR REPLACE TABLE {bak} DEEP CLONE {live}"], writes
        # DEC-46: tagging is gated on P4-ADD-TAG-VALUE, so it stays a comment until then
        assert any(s.startswith("-- tag") and rb.TAG_GATE_TASK in s and "SET TAGS ('telco_project'" in s for s in bs)
        assert any(s.startswith("-- verify (fail closed)") and rb.FP_GATE_TABLE in s and "ABORT" in s for s in bs)
        assert not rb.uses_time_travel(bs)
        rs = rb.rollback_sql(it, 9)
        assert rs[0].startswith(f"CREATE OR REPLACE TABLE {live} DEEP CLONE {bak}"), rs
        assert rs[1].startswith("-- verify (fail closed)") and "freeze_v3_comment_snapshot" in rs[2]
        # new-in-v4 objects have no backup; rollback drops them
        assert rb.backup_sql(it, None) == [] and rb.rollback_sql(it, None)[0].startswith("DROP TABLE IF EXISTS")
    assert "physical_resource_span__v3_rollback".endswith(rb.BRIDGE_SCAN_EXEMPT_SUFFIXES)  # DEC-46 staging
    assert rb.ROLLBACK_DECISION == "DEC-PRI-V4-ROLLBACK-DEEP-CLONE-BACKUP"
    view = next(i for i in rb.RUNBOOK if i.action == "repoint_view")
    assert rb.backup_sql(view, 9) == [] and all(s.startswith("--") for s in rb.rollback_sql(view, 9))


def test_bug_qa_106_rollback_readiness_fail_closed():
    it = next(i for i in rb.RUNBOOK if i.live == "physical_resource_span")
    ok = rb.rollback_readiness(it, 20, "MANAGED", rb.rollback_sql(it, 20), 190.0)
    assert ok["status"] == "ROLLBACK_READY_CLONE" and ok["backup"] == "physical_resource_span__v3_rollback"
    assert ok["time_travel_rollback_would_fail"] is True
    tt = ["RESTORE TABLE x TO " + "VERSION AS OF 19"]
    assert rb.rollback_readiness(it, 20, "MANAGED", tt)["status"] == "ROLLBACK_TIME_TRAVEL"
    assert rb.rollback_readiness(it, 20, None, rb.rollback_sql(it, 20))["status"] == "ROLLBACK_NO_LIVE"
    assert rb.rollback_readiness(it, None, None, rb.rollback_sql(it, None))["status"] == "ROLLBACK_DROP_NEW"
    for bad in ("ROLLBACK_TIME_TRAVEL", "ROLLBACK_NO_LIVE"):
        f = rb.Finding(it, bad, {"rollback_ready": {"status": bad}})
        s = rb.summary([f])
        assert s["blocking"] == 1 and s["rollback_not_ready"] == ["physical_resource_span"], s
    s = rb.summary([rb.Finding(it, "READY", {"rollback_ready": ok})])
    assert s["blocking"] == 0 and s["rollback_ready"] == 1 and s["rollback_not_ready"] == []


# ---------------------------------------------------------------- BUG-QA-108 comment coverage
_WRITE_WORDS = ("CREATE ", "INSERT ", "MERGE ", "DROP ", "DELETE ", "ALTER ", "COMMENT ON", "UPDATE ", "SET TAGS")


def test_bug_qa_108_comment_sql_is_read_only_and_scoped():
    for q in (rb.comment_coverage_sql("derived_srlg_common_site"), rb.comment_expectation_sql("derived_srlg_common_site")):
        assert q.startswith("SELECT") and not any(w in q.upper() for w in _WRITE_WORDS), q
        assert "'derived_srlg_common_site'" in q and not rb.uses_time_travel([q])
    cov = rb.comment_coverage_sql("t")
    assert "information_schema.tables" in cov and "information_schema.columns" in cov
    assert f"table_schema = '{rb.SCHEMA}'" in cov  # never an unscoped information_schema scan
    exp = rb.comment_expectation_sql("t")
    assert rb.V3_COMMENT_SNAPSHOT in exp and f"'{rb.V3}'" in exp and "comment_level = 'TABLE'" in exp
    assert "\\'" in rb.comment_coverage_sql("a'b")  # literal is escaped


def test_bug_qa_108_verdict_fail_closed():
    v = rb.comment_coverage_verdict
    exp = {"table_comment_present": 1, "column_comment_count": 11}
    assert v({"table_comment_present": 1, "column_comment_count": 11}, exp)["status"] == rb.COMMENTS_OK
    # the QA S67 rehearsal: data FP + column comments OK, table comment missing after DEEP CLONE rollback
    assert v({"table_comment_present": 0, "column_comment_count": 11}, exp)["status"] == "COMMENTS_TABLE_MISSING"
    short = v({"table_comment_present": 1, "column_comment_count": 9}, exp)
    assert short["status"] == "COMMENTS_COLUMNS_SHORT" and short["missing"] == 2
    assert v({"table_comment_present": 1, "column_comment_count": 12}, exp)["status"] == "COMMENTS_COLUMNS_MISMATCH"
    assert v({"table_comment_present": 1, "column_comment_count": 12}, exp, strict=False)["status"] == rb.COMMENTS_OK
    assert v({"table_comment_present": 1, "column_comment_count": 9}, exp, strict=False)["status"] == "COMMENTS_COLUMNS_SHORT"
    assert v({"table_comment_present": None, "column_comment_count": 0}, exp)["status"] == "COMMENTS_UNREADABLE"
    assert v(None, exp)["status"] == "COMMENTS_UNREADABLE"
    for empty in (None, {"table_comment_present": 0, "column_comment_count": 0}):
        assert v({"table_comment_present": 1, "column_comment_count": 3}, empty)["status"] == "COMMENTS_NO_EXPECTATION"
    assert set(rb.COMMENT_FAIL_VERDICTS) >= {"COMMENTS_TABLE_MISSING", "COMMENTS_COLUMNS_SHORT", "COMMENTS_UNREADABLE"}


class _CovRow:
    def __init__(self, t, c):
        self.table_comment_present, self.column_comment_count = t, c


class _CovSpark:
    """Fake spark: answers coverage SELECTs by the table literal; records every query."""
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.queries = rows, fail, []

    def sql(self, q, **_):
        self.queries.append(q)
        if self.fail:
            raise RuntimeError("boom")
        key = ("snap" if rb.V3_COMMENT_SNAPSHOT in q else "live", re.findall(r"table_name = '([^']+)'", q)[0])
        r = self.rows.get(key)
        return type("_DF", (), {"first": lambda _s: r})()


def test_bug_qa_108_comment_coverage_check_rollback_and_promote():
    t, c = "derived_srlg_common_site", "derived_srlg_common_site_v4_candidate"
    sp = _CovSpark({("live", t): _CovRow(0, 11), ("snap", t): _CovRow(1, 11)})
    r = rb.comment_coverage_check(sp, t)
    assert r["status"] == "COMMENTS_TABLE_MISSING" and r["strict"] is True and len(sp.queries) == 2
    assert all(q.startswith("SELECT") for q in sp.queries)
    sp = _CovSpark({("live", t): _CovRow(1, 11), ("snap", t): _CovRow(1, 11)})
    assert rb.comment_coverage_check(sp, t)["status"] == rb.COMMENTS_OK
    sp = _CovSpark({("live", t): _CovRow(1, 13), ("live", c): _CovRow(1, 12)})
    p = rb.comment_coverage_check(sp, t, candidate=c)
    assert p["status"] == rb.COMMENTS_OK and p["strict"] is False
    assert not any(rb.V3_COMMENT_SNAPSHOT in q for q in sp.queries)  # promote compares to the candidate
    assert rb.comment_coverage_check(_CovSpark({}), t)["status"] == "COMMENTS_UNREADABLE"  # no rows at all
    e = rb.comment_coverage_check(_CovSpark({}, fail=True), t)
    assert e["status"] == "COMMENTS_UNREADABLE" and "boom" in e["error"]


def test_bug_qa_108_verify_lines_in_rollback_gate0_and_promote_plans():
    """Every plan that ends with a comment re-apply must end with the fail-closed COMMENT COVERAGE line."""
    assert _PROMOTES
    for it in _PROMOTES:
        rs = rb.rollback_sql(it, 9)
        assert rs[-1].startswith("-- COMMENT COVERAGE (BUG-QA-108, fail closed)"), rs
        assert f"comment_coverage_check(spark, '{it.live}')" in rs[-1] and "strict ==" in rs[-1]
        assert "freeze_v3_comment_snapshot" in rs[-2]  # after the re-apply
        ps = rb.promote_sql(it, "FP_PASS")
        assert ps[-1].startswith("-- COMMENT COVERAGE") and f"candidate='{it.candidate}'" in ps[-1], ps
        for g in (rb.gate0_restore_sql(it, 20), rb.gate0_restore_sql(it, 8, readable=False, backup_exists=True)):
            assert g[-1].startswith("-- COMMENT COVERAGE") and "freeze_v3_comment_snapshot" in g[-2], g
        assert rb.rollback_sql(it, None)[-1].startswith("DROP TABLE IF EXISTS")  # new-in-v4: nothing to verify
        assert len(rb.gate0_restore_sql(it, 8, readable=False)) == 1  # escalate path unchanged
    assert all(not s.upper().startswith("COMMENT ON") for it in _PROMOTES for s in rb.rollback_sql(it, 9))


def test_bug_qa_106_gate0_unreadable_restore_version_fails_closed():
    it = next(i for i in rb.RUNBOOK if i.live == "hazard_span_intersection")
    rs = rb.gate0_restore_sql(it, 23, readable=False)
    assert len(rs) == 1 and rs[0].startswith("--") and "NOT time-travelable" in rs[0] and "fail closed" in rs[0]
    assert rb.gate0_restore_sql(it, 24, readable=True)[0].startswith("RESTORE TABLE")
    s = rb.summary([rb.Finding(it, "READY", {"gate0_readable": {"readable": False}})])
    assert s["gate0_unreadable"] == ["hazard_span_intersection"]


def test_bug_qa_106_version_readable_probe_fails_closed():
    class _Boom:
        def sql(self, *a, **k):
            raise RuntimeError("DELTA_UNSUPPORTED_TIME_TRAVEL_BEYOND_DELETED_FILE_RETENTION_DURATION")
    r = rb.version_readable(_Boom(), "hazard_span_intersection", 23)
    assert r["readable"] is False and "RETENTION" in r["error"]
    assert rb.version_readable(_Boom(), "x", None)["readable"] is False
    assert rb.latest_commit_age_h(_Boom(), "x") is None


def test_p65_checklist_rebaseline_and_qa_gates():
    six = next(c for c in rb.CHECKLIST if c[0] == 6)
    seven = next(c for c in rb.CHECKLIST if c[0] == 7)
    assert "P65-DP-PIN-TO-FINGERPRINT-GATES" in six[4] and rb.FP_DECISION in six[4]
    assert "PROVISIONAL" in six[3] and rb.FP_GATE_TABLE in six[3] and "Re-pin" not in six[3]
    assert "P65-QA-VERIFY-FINGERPRINT-GATES" in seven[4]
    assert "FP_PASS" in next(c for c in rb.CHECKLIST if c[0] == 12)[3]


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
    """Fake Lakebase cursor: answers the read-only CEO-gate SELECT and decisions lookups (P63)."""

    def __init__(self, status, decided=()):
        self.status, self.sql, self.decided, self._last = status, [], set(decided), None

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self._last = params
        assert sql.lstrip().upper().startswith("SELECT"), sql

    def fetchall(self):
        return list(self.status.items())

    def fetchone(self):
        return (1,) if self._last and self._last[0] in self.decided else None


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
    assert len(cur.sql) == 2 and "agent_tasks" in cur.sql[0] and "decisions" in cur.sql[1]  # P63: + slip lookup
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
    # P63 default: service_path_v4 not promoted -> fk_path_span SKIPPED, never deferred
    p = rb.pk_fk_plan(_DDL)
    assert len(p["after_swap"]) == 3 and len(p["deferred"]) == 2 and len(p["skipped"]) == 1
    assert "fk_path_span" in p["skipped"][0]
    assert p["deferred_tables"] == ["geographic_site"]
    promoted = set(rb.promoted_tables())
    for s in p["after_swap"]:
        assert "geographic_site" not in s and "service_path" not in s
        assert s.split()[2] in promoted
    # an FK on a promoted child pointing at a v3 FROZEN parent is deferred too
    assert any("fk_span_site" in s for s in p["deferred"])


def test_p60_pk_fk_plan_missing_file_is_empty(tmp_path):
    p = rb.pk_fk_plan(root=str(tmp_path))
    assert p == {"source": None, "after_swap": [], "deferred": [], "deferred_tables": [], "skipped": []}


# ---------------------------------------------------------------- P63 retarget 11-02 + conditional service_path
def test_p63_slip_decided_locks_target_1102():
    import datetime as dt
    notdone = {"BUG-QA-073": "in_progress", "P36-ML-V4-RESCORE-CONDUIT-DIVERSITY": "blocked"}
    slip = {rb.SLIP_DECISION}
    for day in (dt.date(2026, 10, 30), dt.date(2026, 10, 31), dt.date(2026, 11, 1)):
        p = rb.contingency_plan(_GateCur(notdone, slip), day)
        assert p["path"] == "B" and p["target"] == dt.date(2026, 11, 2), (day, p["target"])
        assert p["slip_decided"] and p["ceo_deadline"] == dt.date(2026, 11, 1) and not p["needs_pm_decision"]
    # without DEC-38 decided, 10-31 would have rolled to 11-03 under DEC-33
    assert rb.contingency_plan(_GateCur(notdone), dt.date(2026, 10, 31))["target"] == dt.date(2026, 11, 3)
    # CEO writes land in time -> still 11-02
    done = {c: "completed" for c in rb.CEO_GATES}
    assert rb.contingency_plan(_GateCur(done, slip), dt.date(2026, 11, 2))["target"] == dt.date(2026, 11, 2)
    # new deadline missed -> proposal only, flagged for @pm (no silent auto-slip)
    m = rb.contingency_plan(_GateCur(notdone, slip), dt.date(2026, 11, 2))
    assert m["path"] == "B_MISSED" and m["needs_pm_decision"] and m["target"] == dt.date(2026, 11, 4)
    assert rb.ACTIVE_TARGET == dt.date(2026, 11, 2) and rb.SLIP_DECISION == "DEC-PRI-V4-CUTOVER-SLIP-1102"


def test_p63_1102_dated_checklist_ceo_writes_due_1101():
    import datetime as dt
    rows = {r["order"]: r["due"] for r in rb.dated_checklist(rb.ACTIVE_TARGET)}
    assert rows[1] == rows[2] == rb.SLIP_APPROVAL_DEADLINE == dt.date(2026, 11, 1)
    assert rows[12] == dt.date(2026, 11, 2) and rows[18] == rows[19] == dt.date(2026, 11, 3)


def test_p63_service_path_conditional_item_after_span():
    it = next(i for i in rb.RUNBOOK if i.live == "service_path")
    assert it.action == "conditional_promote" and it.candidate == "service_path_v4_candidate"
    assert _pos("physical_resource_span") < _pos("service_path") < _pos("path_diversity_conduit")
    for g in rb.SERVICE_PATH_GATES:
        assert g in it.owner_gate
    assert "service_path" not in rb.promoted_tables()
    assert "service_path" in rb.promoted_tables(include_conditional=True)
    sql = rb.promote_sql(it, 3)
    assert sql[0].startswith("-- CONDITIONAL") and rb.SERVICE_PATH_DECISION in sql[0]


def test_p63_service_path_condition_default_skip():
    done = {g: "completed" for g in rb.SERVICE_PATH_GATES}
    c = rb.service_path_condition({}, done)  # candidate not landed in UC
    assert not c["met"] and "SKIPPED" in c["log"] and "fk_path_span" in c["log"]
    assert not rb.service_path_condition({"service_path_v4_candidate": "MANAGED"}, {})["met"]
    assert not rb.service_path_condition({"service_path_v4_candidate": "VIEW"}, done)["met"]
    ok = rb.service_path_condition({"service_path_v4_candidate": "MANAGED"}, done)
    assert ok["met"] and ok["log"] is None


def test_p63_pk_fk_with_service_path_promoted():
    p = rb.pk_fk_plan(_DDL, service_path_promoted=True)
    assert p["skipped"] == [] and any("fk_path_span" in s for s in p["after_swap"])
    assert p["deferred_tables"] == ["geographic_site"]


def test_p63_steps_14_19_gated_on_service_path_decision():
    for order in (14, 19):
        row = next(c for c in rb.CHECKLIST if c[0] == order)
        assert rb.SERVICE_PATH_DECISION in row[4] and "fk_path_span" in row[3]
    st = {c["order"]: c for c in rb.checklist_status(_GateCur({}, {rb.SERVICE_PATH_DECISION}))}
    assert st[19]["gates"] == {rb.SERVICE_PATH_DECISION: "completed"} and not st[19]["done"]  # still manual
    assert st[14]["gates"]["P43-DE-V4-PK-FK-CONSTRAINTS"] == "UNKNOWN" and not st[14]["done"]


def test_p63_skip_is_non_blocking_in_summary():
    it = next(i for i in rb.RUNBOOK if i.live == "service_path")
    s = rb.summary([rb.Finding(it, "SKIPPED_CONDITIONAL")])
    assert s["blocking"] == 0 and s["conditional_skips"] == ["service_path"]


def test_p67_gate0_restore_uses_manifest_restore_version():
    """P67 / BUG-QA-095: gate-0 restore targets demo_freeze_manifest.restore_version, never delta_version."""
    it = next(i for i in rb.RUNBOOK if i.live == "physical_resource_span")
    rs = rb.gate0_restore_sql(it, 20)  # span: delta_version 11 (past retention), restore_version 20
    restores = [s for s in rs if s.startswith("RESTORE")]
    assert len(restores) == 1 and "VERSION AS OF 20" in restores[0] and "restore_version" in restores[0]
    assert "VERSION AS OF 11" not in " ".join(rs)
    assert not any(s.startswith("RESTORE") for s in rb.gate0_restore_sql(it, None))  # fail closed
    assert "restore_version" in SRC.split("def _manifest")[1].split("def ")[0]
    assert 'd["v3_restore"] = v3row.restore_version' in SRC


# ---------------------------------------------------------------- P68 partial cutover (DEC-41 option b)
def test_p68_partial_flag_defaults_off():
    import inspect
    for fn in (rb.dry_run, rb.execute, rb.promoted_tables, rb.pk_fk_plan):
        assert inspect.signature(fn).parameters["partial_cutover"].default is False, fn.__name__
    assert rb.PARTIAL_DECISION == "DEC-PRI-V4-073-SECOND-MISS-PARTIAL-CUTOVER"
    assert set(rb.PARTIAL_KEEP_V3) >= {"hazard_span_intersection", "span_risk_predictions", "resilience_score_snapshot"}
    acts = {i.live: i.action for i in rb.RUNBOOK}
    assert all(acts[t] in ("promote", "repoint_view") for t in rb.PARTIAL_KEEP_V3_ITEMS)
    kept_promotes = {t for t in rb.PARTIAL_KEEP_V3_ITEMS if acts[t] == "promote"}
    assert kept_promotes <= set(rb.promoted_tables())  # full cutover unchanged
    assert not set(rb.PARTIAL_KEEP_V3) & set(rb.promoted_tables(partial_cutover=True))
    assert set(rb.promoted_tables()) - set(rb.promoted_tables(partial_cutover=True)) == kept_promotes


# ---------------------------------------------------------------- P69 PARTIAL_KEEP_V3 expand (DEC id 42)
DEC42_ADDED = {"hazard_span_proximity", "span_hazard_features", "hazard_proximity_count", "proactive_action",
               "path_diversity_conduit", "diversity_coverage", "revenue_at_risk", "mv_mrc_protected"}


def test_p69_partial_keep_v3_has_dec42_objects():
    assert rb.PARTIAL_EXPAND_DECISION == "DEC-PRI-V4-PARTIAL-KEEP-V3-EXPAND"
    assert set(rb.PARTIAL_KEEP_V3_ITEMS) == DEC42_ADDED | {"hazard_span_intersection", "span_risk_predictions",
                                                           "resilience_score_snapshot"}
    assert len(rb.PARTIAL_KEEP_V3_ITEMS) == len(set(rb.PARTIAL_KEEP_V3_ITEMS)) == 11
    lives = {i.live for i in rb.RUNBOOK}
    assert set(rb.PARTIAL_KEEP_V3_ITEMS) <= lives  # every kept runbook name is a real runbook item
    # P71 (QA S59): the DEC-44 FK consumers are kept too, but they are NOT runbook items
    assert set(rb.PARTIAL_KEEP_V3_FK_CONSUMERS).isdisjoint(lives)
    assert set(rb.PARTIAL_KEEP_V3) == set(rb.PARTIAL_KEEP_V3_ITEMS) | set(rb.PARTIAL_KEEP_V3_FK_CONSUMERS)
    # Non-HSI promotes stay in partial mode (DEC-42: conduit, span, SRLG set, site promote).
    part = set(rb.promoted_tables(partial_cutover=True))
    assert {"physical_resource_conduit", "physical_resource_span", "derived_shared_risk_group"} <= part
    assert {"hazard_span_proximity", "proactive_action", "path_diversity_conduit"}.isdisjoint(part)


def test_p69_partial_keep_verdict_views_and_v4_only():
    item = {i.live: i for i in rb.RUNBOOK}
    view_ok = {"live_type": "METRIC_VIEW", "v3_status": "FROZEN"}
    for v in ("hazard_proximity_count", "diversity_coverage", "revenue_at_risk"):
        assert rb.partial_keep_verdict(item[v], view_ok) == rb.PARTIAL_VERDICT  # v3 view kept, not repointed
    new_v4 = {"live_type": None, "v3_status": "NOT_IN_V3"}
    for v in ("span_hazard_features", "path_diversity_conduit", "mv_mrc_protected"):
        assert rb.partial_keep_verdict(item[v], new_v4) == rb.PARTIAL_DEFERRED_VERDICT
    # fail closed: v3-manifest object whose live view/table is gone
    assert rb.partial_keep_verdict(item["revenue_at_risk"], {"live_type": None, "v3_status": "FROZEN"}) == "V3_FP_NO_LIVE"
    assert rb.partial_keep_verdict(item["proactive_action"], {"live_type": None, "v3_status": "FROZEN"}) == "V3_FP_NO_LIVE"
    # kept MANAGED tables still go through the v3 fingerprint gate
    ok = {"live_type": "MANAGED", "v3_status": "FROZEN", "live_fp": {"status": "FP_PASS"}}
    assert rb.partial_keep_verdict(item["hazard_span_proximity"], ok) == rb.PARTIAL_VERDICT
    assert rb.partial_keep_verdict(item["proactive_action"], {**ok, "live_fp": {"status": "FP_MISMATCH"}}) == "V3_FP_MISMATCH"
    # a MANAGED promote item is never treated as a view
    assert rb.partial_keep_verdict(item["proactive_action"], view_ok) == "V3_FP_NO_LIVE"


def test_p69_summary_deferred_is_non_blocking():
    fs = [rb.Finding(i, rb.PARTIAL_DEFERRED_VERDICT if i.live == "mv_mrc_protected" else
                     (rb.PARTIAL_VERDICT if i.live in rb.PARTIAL_KEEP_V3 else "READY"), {"partial_cutover": True})
          for i in rb.RUNBOOK]
    s = rb.summary(fs, _GateCur({}, decided={rb.GO_DECISION, rb.PARTIAL_DECISION}))
    assert s["blocking"] == 0 and s["deferred_v4_1"] == ["mv_mrc_protected"] and s["cutover_ready"] is True
    assert len(s["kept_v3_provisional"]) == 10


def test_p68_partial_keep_verdict_fails_closed():
    hsi = next(i for i in rb.RUNBOOK if i.live == "hazard_span_intersection")
    span = next(i for i in rb.RUNBOOK if i.live == "physical_resource_span")
    ok = {"live_type": "MANAGED", "v3_status": "FROZEN", "live_fp": {"status": "FP_PASS"}}
    assert rb.partial_keep_verdict(hsi, ok) == rb.PARTIAL_VERDICT
    assert rb.partial_keep_verdict(span, ok) is None  # non-kept items use the normal promote path
    assert rb.partial_keep_verdict(hsi, {**ok, "live_fp": {"status": "FP_MISMATCH"}}) == "V3_FP_MISMATCH"
    assert rb.partial_keep_verdict(hsi, {**ok, "live_fp": {}}) == "V3_FP_NO_BASELINE"
    assert rb.partial_keep_verdict(hsi, {**ok, "live_type": None}) == "V3_FP_NO_LIVE"
    assert rb.partial_keep_verdict(hsi, {**ok, "v3_status": "NOT_IN_V3"}) == "V3_FP_NO_LIVE"
    sql = rb.partial_sql(hsi)
    assert sql and all(s.startswith("--") for s in sql)  # plan text only, no writes
    assert rb.PARTIAL_DECISION in sql[0] and "PROVISIONAL" in sql[0] and rb.V3 in sql[1]


def test_p68_summary_and_execute_gate_on_dec41(monkeypatch):
    keep = [rb.Finding(i, rb.PARTIAL_VERDICT, {"partial_cutover": True}) for i in rb.RUNBOOK if i.live in rb.PARTIAL_KEEP_V3]
    rest = [rb.Finding(i, "READY", {"partial_cutover": True}) for i in rb.RUNBOOK if i.live not in rb.PARTIAL_KEEP_V3]
    s = rb.summary(keep + rest, _GateCur({}, decided={rb.GO_DECISION}))
    assert s["blocking"] == 0 and s["partial_cutover"] and sorted(s["kept_v3_provisional"]) == sorted(rb.PARTIAL_KEEP_V3_ITEMS)
    assert s["cutover_ready"] is False  # GO alone is not enough in partial mode
    assert rb.summary(keep + rest, _GateCur({}, decided={rb.GO_DECISION, rb.PARTIAL_DECISION}))["cutover_ready"] is True
    bad = [rb.Finding(keep[0].item, "V3_FP_MISMATCH", {"partial_cutover": True})] + keep[1:] + rest
    assert rb.summary(bad, _GateCur({}, decided={rb.GO_DECISION, rb.PARTIAL_DECISION}))["blocking"] == 1
    full = rb.summary([rb.Finding(i, "READY") for i in rb.RUNBOOK], _GateCur({}, decided={rb.GO_DECISION}))
    assert full["partial_cutover"] is False and full["partial_decision"] is None
    monkeypatch.setenv("PRI_V4_CUTOVER_WRITE", "1")
    with pytest.raises(rb.CutoverRefused, match=rb.PARTIAL_DECISION):
        rb.execute(None, _GateCur({}, decided={rb.GO_DECISION}), write_enabled=True, partial_cutover=True)


def test_p68_pk_fk_partial_defers_kept_tables():
    ddl = ("ALTER TABLE x.hazard_span_intersection ADD CONSTRAINT pk_hsi PRIMARY KEY (id);\n"
           "ALTER TABLE x.physical_resource_span ADD CONSTRAINT pk_span PRIMARY KEY (span_id);")
    full = rb.pk_fk_plan(text=ddl)
    part = rb.pk_fk_plan(text=ddl, partial_cutover=True)
    assert len(full["after_swap"]) == 2 and not full["deferred"]
    assert len(part["after_swap"]) == 1 and "physical_resource_span" in part["after_swap"][0]
    assert part["deferred_tables"] == ["hazard_span_intersection"]


# ---------------------------------------------------------------- P71 b0 span_bb_route_bridge (DEC id 44)
class _Row(tuple):
    def __new__(cls, *vals, **kw):
        r = super().__new__(cls, vals or tuple(kw.values()))
        r.__dict__.update(kw)
        return r


class _Res:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows

    def first(self):
        return self.rows[0]


class _BridgeSpark:
    """Fake spark for bridge_check: answers information_schema, integrity counts and orphan SELECTs."""

    def __init__(self, orphans=None, integrity=None, cols=None, boom=False):
        self.orphans, self.integrity, self.boom, self.sql_log = orphans or {}, integrity or {}, boom, []
        default = {t: {"span_id"} for t in rb.BRIDGE_FK_CONSUMERS}
        default[rb.BRIDGE_TABLE] = {"bb_span_id", "bbs_span_id"}
        self.cols = default if cols is None else cols

    def sql(self, q, args=None):
        self.sql_log.append(q)
        assert q.lstrip().upper().startswith("SELECT"), q  # read-only
        if self.boom:
            raise RuntimeError("table not readable")
        if "information_schema.columns" in q:
            return _Res([_Row(table_name=t, column_name=c) for t, cs in self.cols.items() for c in cs])
        if "AS n" in q:
            t = next(t for t in rb.BRIDGE_FK_CONSUMERS if f"`{t}` c" in q)
            n = self.orphans.get(t, 0)
            return _Res([_Row(n=n, k=min(n, 92))])
        k = next(k for k, s in rb.bridge_integrity_sql().items() if s == q)
        return _Res([_Row(self.integrity.get(k, {"rows": 5325, "bb_keys": 92}.get(k, 0)))])


def test_p71_runbook_items_b0_before_span_and_keep_consumers_appended():
    assert rb.BRIDGE_TABLE not in {i.live for i in rb.RUNBOOK}
    # P73 (DEC id 45): full mode now has the same b0 + keep_v3 consumer shape as partial mode
    assert [(i.step, i.live, i.action) for i in rb.runbook_items()] == \
        [(i.step, i.live, i.action) for i in rb.runbook_items(partial_cutover=True)]
    part = rb.runbook_items(partial_cutover=True)
    lives = [i.live for i in part]
    assert lives.index(rb.BRIDGE_TABLE) + 1 == lives.index("physical_resource_span")  # b0 right before (b)
    assert part[lives.index(rb.BRIDGE_TABLE)].step == "b0" and part[lives.index(rb.BRIDGE_TABLE)].action == "bridge_verify"
    assert lives[-2:] == list(rb.PARTIAL_KEEP_V3_FK_CONSUMERS)
    assert all(i.action == "keep_v3" and i.candidate is None for i in part[-2:])
    assert len(part) == len(rb.RUNBOOK) + 3


def test_p71_fk_consumer_set_matches_dec44():
    assert rb.BRIDGE_DECISION == "DEC-PRI-V4-PARTIAL-SPAN-GRAIN-BRIDGE"
    assert set(rb.PARTIAL_KEEP_V3_FK_CONSUMERS) == {"optical_anomaly_detection", "span_risk_inference_log"}
    # DP P68 section C: the 7 tables that orphan 32,502 rows on the 92 BB-* keys
    assert set(rb.BRIDGE_FK_CONSUMERS) == {"service_path", "hazard_span_intersection", "proactive_action",
                                           "hazard_span_proximity", "span_risk_predictions",
                                           "optical_anomaly_detection", "span_risk_inference_log"}
    assert set(rb.BRIDGE_FK_CONSUMERS) <= set(rb.PARTIAL_KEEP_V3) | {"service_path"}
    assert "physical_resource_span" not in rb.BRIDGE_FK_CONSUMERS
    # kept FK consumers never enter the promote set (no v4 comment snapshot / AFTER_SWAP constraints)
    assert set(rb.PARTIAL_KEEP_V3_FK_CONSUMERS).isdisjoint(rb.promoted_tables(include_conditional=True))


def test_p71_bridge_sql_is_read_only_and_unions_bridge():
    for t in rb.BRIDGE_FK_CONSUMERS:
        q = rb.bridge_orphan_sql(t)
        assert q.startswith("SELECT") and "LEFT ANTI JOIN" in q and "UNION" in q and "bb_span_id" in q
        assert rb.SPAN_V4 in q and rb.BRIDGE_TABLE in q
    assert "`physical_resource_span`" in rb.bridge_orphan_sql("service_path", "physical_resource_span")
    assert set(rb.BRIDGE_INTEGRITY_ZERO) <= set(rb.bridge_integrity_sql())
    assert all(q.startswith("SELECT") for q in rb.bridge_integrity_sql().values())
    plan = rb.bridge_plan_sql()
    assert all(s.startswith(("--", "SELECT")) for s in plan)  # never writes the bridge
    assert not any(w in s.upper() for s in plan for w in ("CREATE ", "INSERT ", "MERGE ", "DROP ", "DELETE "))
    assert "POST-SWAP" in plan[-1]


def test_p71_bridge_check_ready_and_fail_closed():
    objs = {rb.BRIDGE_TABLE: "MANAGED"}
    ok = rb.bridge_check(_BridgeSpark(), objs)
    assert ok["integrity"]["rows"] == 5325 and set(ok["orphans"]) == set(rb.BRIDGE_FK_CONSUMERS)
    assert rb.bridge_verdict(ok, True) == "READY"
    assert rb.bridge_verdict(ok, False) == "BRIDGE_NOT_DECIDED"
    assert rb.bridge_verdict(ok, True, ["P70-QA-VERIFY-PARTIAL-FK-BRIDGE"]) == "GATE_OPEN"
    assert rb.bridge_verdict(None, True) == "BRIDGE_NOT_CHECKED"
    # missing bridge fails closed (P70-DE not landed)
    assert rb.bridge_verdict(rb.bridge_check(_BridgeSpark(), {}), True) == "BRIDGE_MISSING"
    orph = rb.bridge_check(_BridgeSpark(orphans={"service_path": 30769}), objs)
    assert rb.bridge_verdict(orph, True) == "BRIDGE_FK_ORPHANS" and orph["orphans"]["service_path"]["rows"] == 30769
    bad = rb.bridge_check(_BridgeSpark(integrity={"bbs_unmapped": 3}), objs)
    assert rb.bridge_verdict(bad, True) == "BRIDGE_INTEGRITY"
    nocol = _BridgeSpark()
    nocol.cols[rb.BRIDGE_TABLE] = {"bbs_span_id"}
    r = rb.bridge_check(nocol, objs)
    assert r["missing_columns"] == ["bb_span_id"] and rb.bridge_verdict(r, True) == "BRIDGE_COLUMNS_MISSING"
    extra = _BridgeSpark()
    extra.cols["resilience_score_snapshot"] = {"span_id"}  # a kept table gains span_id -> gate must list it
    assert rb.bridge_verdict(rb.bridge_check(extra, objs), True) == "BRIDGE_CONSUMER_SET_DRIFT"
    boom = rb.bridge_check(_BridgeSpark(boom=True), objs)
    assert "error" in boom and rb.bridge_verdict(boom, True) == "BRIDGE_UNREADABLE"


def test_p71_summary_bridge_blocks_partial_cutover():
    part = rb.runbook_items(partial_cutover=True)

    def fs(bridge_verdict):
        out = []
        for i in part:
            v = (bridge_verdict if i.action == "bridge_verify" else
                 rb.PARTIAL_VERDICT if i.live in rb.PARTIAL_KEEP_V3 else "READY")
            out.append(rb.Finding(i, v, {"partial_cutover": True, "bridge": {"orphans": {"service_path": {"rows": 0}}}}))
        return out

    dec = {rb.GO_DECISION, rb.PARTIAL_DECISION}
    good = rb.summary(fs("READY"), _GateCur({}, decided=dec))
    assert good["blocking"] == 0 and good["bridge"] == "READY" and good["bridge_orphans"] == 0 and good["cutover_ready"]
    assert set(rb.PARTIAL_KEEP_V3_FK_CONSUMERS) <= set(good["kept_v3_provisional"])
    miss = rb.summary(fs("BRIDGE_MISSING"), _GateCur({}, decided=dec))
    assert miss["blocking"] == 1 and miss["bridge"] == "BRIDGE_MISSING" and miss["cutover_ready"] is False
    assert rb.summary([rb.Finding(i, "READY") for i in rb.RUNBOOK], _GateCur({}, decided=dec))["bridge"] is None


def test_p71_keep_v3_consumer_uses_v3_fingerprint_gate():
    it = rb.KEEP_V3_CONSUMER_ITEMS[0]
    ok = {"live_type": "MANAGED", "v3_status": "FROZEN", "live_fp": {"status": "FP_PASS"}}
    assert rb.partial_keep_verdict(it, ok) == rb.PARTIAL_VERDICT
    assert rb.partial_keep_verdict(it, {**ok, "live_fp": {"status": "FP_MISMATCH"}}) == "V3_FP_MISMATCH"
    assert rb.partial_keep_verdict(it, {**ok, "live_type": None}) == "V3_FP_NO_LIVE"
    sql = rb.partial_sql(it)
    assert all(s.startswith("--") for s in sql) and "None" not in sql[0] and rb.BRIDGE_DECISION in sql[0]


def test_p71_dry_run_wires_bridge_in_both_modes():
    body = SRC.split("def dry_run")[1].split("\ndef ")[0]
    assert "if partial_cutover else None" not in body  # P73: b0 is no longer partial-only
    assert 'consumers=bridge_consumers(False, sp_cond["met"])' in body
    assert "bridge_decision(partial_cutover)" in body
    assert "runbook_items(partial_cutover)" in body
    assert '"bridge_verify") and verdict not in' in body  # a failed b0 blocks everything downstream


# ---------------------------------------------------------------- P73 full-mode bridge consumers (DEC id 45)
def test_p73_full_mode_consumers_and_decision():
    assert rb.BRIDGE_FULL_DECISION == "DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES"
    assert rb.bridge_decision(False) == rb.BRIDGE_FULL_DECISION and rb.bridge_decision(True) == rb.BRIDGE_DECISION
    assert set(rb.FULL_MODE_PROVISIONAL) == {"optical_anomaly_detection", "span_risk_inference_log"}
    assert rb.bridge_consumers(True) == rb.BRIDGE_FK_CONSUMERS
    assert rb.bridge_consumers(False, service_path_promoted=True) == rb.FULL_KEEP_V3_FK_CONSUMERS
    assert set(rb.bridge_consumers(False)) == set(rb.FULL_KEEP_V3_FK_CONSUMERS) | {"service_path"}
    # promoted v4 tables are never full-mode bridge consumers
    assert set(rb.bridge_consumers(False)).isdisjoint(rb.promoted_tables())


def test_p73_full_mode_bridge_check_ready_and_fail_closed():
    objs = {rb.BRIDGE_TABLE: "MANAGED"}
    cons = rb.bridge_consumers(False)

    def full_spark(**kw):  # information_schema is filtered to the watched tables (consumers + bridge)
        cols = {t: {"span_id"} for t in cons}
        cols[rb.BRIDGE_TABLE] = {"bb_span_id", "bbs_span_id"}
        return _BridgeSpark(cols=cols, **kw)

    sp = full_spark()
    ok = rb.bridge_check(sp, objs, consumers=cons)
    assert set(ok["orphans"]) == set(cons) and ok["unlisted_consumers"] == []
    assert rb.bridge_verdict(ok, True) == "READY"
    # only the full-mode consumers are queried (promoted v3 tables like HSI are not)
    assert not any("`hazard_span_intersection` c" in q for q in sp.sql_log)
    assert "'hazard_span_intersection'" not in next(q for q in sp.sql_log if "information_schema" in q)
    orph = rb.bridge_check(full_spark(orphans={"optical_anomaly_detection": 4}), objs, consumers=cons)
    assert rb.bridge_verdict(orph, True) == "BRIDGE_FK_ORPHANS"
    miss = full_spark()
    miss.cols["span_risk_inference_log"] = set()
    assert rb.bridge_verdict(rb.bridge_check(miss, objs, consumers=cons), True) == "BRIDGE_CONSUMER_SET_DRIFT"
    part = rb.bridge_check(full_spark(), objs, consumers=cons)
    part["orphans"].pop("span_risk_inference_log")
    assert rb.bridge_verdict(part, True) == "BRIDGE_FK_UNCHECKED"
    plan = rb.bridge_plan_sql(cons, rb.BRIDGE_FULL_DECISION)
    assert rb.BRIDGE_FULL_DECISION in plan[0] and sum(s.startswith("SELECT") for s in plan) == len(cons)


def test_p73_full_mode_keep_v3_items_use_v3_fp_gate():
    full = rb.runbook_items()
    keep = [i for i in full if i.action == "keep_v3"]
    assert [i.live for i in keep] == list(rb.FULL_KEEP_V3_FK_CONSUMERS)
    body = SRC.split("def dry_run")[1].split("\ndef ")[0]
    assert 'partial_keep_verdict(it, d) if (partial_cutover or it.action == "keep_v3") else None' in body
    sql = rb.partial_sql(keep[0], partial_cutover=False)
    assert all(s.startswith("--") for s in sql) and rb.BRIDGE_FULL_DECISION in sql[0] and "FULL CUTOVER" in sql[0]


def test_p73_full_mode_summary_counts_kept_consumers_non_blocking():
    full = rb.runbook_items()
    fs = [rb.Finding(i, rb.PARTIAL_VERDICT if i.action == "keep_v3" else "READY",
                     {"partial_cutover": False, "bridge": {"orphans": {}}}) for i in full]
    s = rb.summary(fs, _GateCur({}, decided={rb.GO_DECISION}))
    assert s["blocking"] == 0 and s["cutover_ready"] and not s["partial_cutover"]
    assert s["kept_v3_provisional"] == list(rb.FULL_MODE_PROVISIONAL) and s["bridge"] == "READY"


# ---------------------------------------------------------------- BUG-QA-102 b0 gates everything after it
def _qa102_verdicts(b0_verdict):
    """Replays the dry_run BUG-QA-102 rule on a list of READY items after b0."""
    body = SRC.split("def dry_run")[1].split("\ndef ")[0]
    assert 'elif (not bridge_ok and verdict == "READY"' in body and 'bridge_ok = verdict == "READY"' in body
    out, bridge_ok = {}, True
    for it in rb.runbook_items(partial_cutover=True):
        verdict = b0_verdict if it.action == "bridge_verify" else "READY"
        if it.action == "bridge_verify":
            bridge_ok = verdict == "READY"
        elif not bridge_ok and verdict == "READY" and it.action in ("promote", "conditional_promote", "repoint_view"):
            verdict = "WAITS_UPSTREAM"
        out.setdefault(it.live, verdict)
    return out


def test_bug_qa_102_non_ready_b0_makes_span_wait_upstream():
    v = _qa102_verdicts("BRIDGE_MISSING")
    assert v["physical_resource_conduit"] == "READY"  # step (a) is before b0
    for t in ("physical_resource_span", "resource_alarm", "resource_performance_measure", "service_path",
              "unified_shared_risk_group"):
        assert v[t] == "WAITS_UPSTREAM", t
    assert all(x in ("READY", "WAITS_UPSTREAM") for k, x in v.items() if k != rb.BRIDGE_TABLE)
    ok = _qa102_verdicts("READY")
    assert ok["physical_resource_span"] == "READY" and ok["resource_alarm"] == "READY"


class _Q102Spark:
    """Minimal end-to-end fake for dry_run: every object present and FP_PASS, bridge table absent."""

    def sql(self, q, args=None):
        raise RuntimeError("no spark in unit test")


def test_bug_qa_102_dry_run_end_to_end(monkeypatch):
    items = rb.runbook_items(partial_cutover=True)
    objs = {}
    for i in items:
        if i.action == "bridge_verify":
            continue
        objs[i.live] = "MANAGED"
        if i.candidate:
            objs[i.candidate] = "MANAGED"
    row = type("R", (), {"freeze_status": "FROZEN", "delta_version": 1, "restore_version": 1})
    drow = type("D", (), {"freeze_status": "V4_CANDIDATE", "delta_version": 1, "restore_version": None})
    monkeypatch.setattr(rb, "_objects", lambda s: objs)
    monkeypatch.setattr(rb, "_manifest", lambda s, v: ({i.live: row for i in items} if v == rb.V3
                                                       else {i.candidate: drow for i in items if i.candidate}))
    monkeypatch.setattr(rb, "_comment_counts", lambda s: {})
    monkeypatch.setattr(rb, "_fp_baselines", lambda s: {})
    monkeypatch.setattr(rb, "_open_tasks", lambda c: set())
    monkeypatch.setattr(rb, "latest_data_version", lambda s, n: 1)
    monkeypatch.setattr(rb, "fingerprint_gate", lambda s, n, v, b=None: {"status": "FP_PASS"})
    monkeypatch.setattr(rb, "_decided", lambda c, code: True)
    monkeypatch.setattr(rb, "cand_fk_check", lambda s, t, span_source=rb.SPAN_V4: {"span_cols": [], "orphans": {}})
    for partial in (True, False):
        f = {x.item.live: x.verdict for x in rb.dry_run(_Q102Spark(), None, verbose=False, pin_guard=False, partial_cutover=partial)}
        assert f[rb.BRIDGE_TABLE] == "BRIDGE_MISSING"
        assert f["physical_resource_conduit"] == "READY"
        assert f["physical_resource_span"] == "WAITS_UPSTREAM" and f["resource_alarm"] == "WAITS_UPSTREAM"
        assert "READY" not in [v for k, v in f.items() if k not in ("physical_resource_conduit",)]


# ---------------------------------------------------------------- BUG-QA-104 candidate FK gate + schema-wide scan
def _dry_run_fixture(monkeypatch, cand_fk):
    """Every object present + FP_PASS, bridge READY, all decided; cand_fk_check returns the given dict."""
    items = rb.runbook_items()
    objs = {rb.BRIDGE_TABLE: "MANAGED"}
    for i in items:
        if i.action != "bridge_verify":
            objs[i.live] = "MANAGED"
            if i.candidate:
                objs[i.candidate] = "MANAGED"
    row = type("R", (), {"freeze_status": "FROZEN", "delta_version": 1, "restore_version": 1})
    drow = type("D", (), {"freeze_status": "V4_CANDIDATE", "delta_version": 1, "restore_version": None})
    monkeypatch.setattr(rb, "_objects", lambda s: objs)
    monkeypatch.setattr(rb, "_manifest", lambda s, v: ({i.live: row for i in items} if v == rb.V3
                                                       else {i.candidate: drow for i in items if i.candidate}))
    monkeypatch.setattr(rb, "_comment_counts", lambda s: {})
    monkeypatch.setattr(rb, "_fp_baselines", lambda s: {})
    monkeypatch.setattr(rb, "_open_tasks", lambda c: set())
    monkeypatch.setattr(rb, "latest_data_version", lambda s, n: 1)
    monkeypatch.setattr(rb, "fingerprint_gate", lambda s, n, v, b=None: {"status": "FP_PASS"})
    monkeypatch.setattr(rb, "_decided", lambda c, code: True)
    monkeypatch.setattr(rb, "bridge_check", lambda s, o, span_source=rb.SPAN_V4, consumers=None: {"ok": True})
    monkeypatch.setattr(rb, "bridge_verdict", lambda b, dec, gates=(): "READY")
    seen = {}

    def fake_check(spark, targets, span_source=rb.SPAN_V4):
        seen.update(targets)
        return cand_fk
    monkeypatch.setattr(rb, "cand_fk_check", fake_check)
    return seen


def test_bug_qa_104_cand_fk_sql_read_only():
    q = rb.cand_fk_orphan_sql("span_risk_predictions_v4_candidate")
    assert q.startswith("SELECT") and "LEFT ANTI JOIN" in q and rb.SPAN_V4 in q
    assert "UNION" not in q and rb.BRIDGE_TABLE not in q  # promoted candidates must match span_v4 alone
    qb = rb.cand_fk_orphan_sql("x", allow_bridge=True)
    assert "UNION" in qb and rb.BRIDGE_TABLE in qb and "bb_span_id" in qb
    assert "`physical_resource_span`" in rb.cand_fk_orphan_sql("x", "physical_resource_span")


def test_bug_qa_104_cand_fk_targets():
    items = rb.runbook_items()
    objs = {i.candidate: "MANAGED" for i in items if i.candidate}
    full = rb.cand_fk_targets(items, objs)
    assert rb.SPAN_V4 not in full  # the span candidate is the FK parent
    assert {"span_risk_predictions_v4_candidate", "hazard_span_intersection_v4_candidate"} <= set(full)
    assert not any(full.values())  # no promoted candidate may use the bridge
    assert not any(rb._c(v) in full for v in ("unified_shared_risk_group", "kpi_delta_attribution"))  # views/report
    part = rb.cand_fk_targets(items, objs, partial_cutover=True)
    assert not any(t[:-len(rb.SUFFIX)] in rb.PARTIAL_KEEP_V3 for t in part)  # kept on v3 -> not promoted
    assert "resource_alarm_v4_candidate" in part
    assert rb.cand_fk_targets(items, {}) == {}  # candidate not in UC -> MISSING_CANDIDATE, not this gate


class _CandSpark:
    def __init__(self, cols, orphans, boom=False):
        self.cols, self.orphans, self.boom, self.sql_log = cols, orphans, boom, []

    def sql(self, q, args=None):
        self.sql_log.append(q)
        assert q.lstrip().upper().startswith("SELECT"), q
        if self.boom:
            raise RuntimeError("unreadable")
        if "information_schema.columns" in q:
            return _Res([_Row(table_name=t, column_name=c) for t, cs in self.cols.items() for c in cs])
        t = next(t for t in self.cols if f"`{t}` c" in q)
        n = self.orphans.get(t, 0)
        return _Res([_Row(n=n, k=min(n, 92))])


def test_bug_qa_104_injected_bb_key_in_candidate_fails_closed():
    srp, hsp, cond = "span_risk_predictions_v4_candidate", "hazard_span_proximity_v4_candidate", rb._c("physical_resource_conduit")
    targets = {srp: False, hsp: False, cond: False}
    sp = _CandSpark({srp: {"span_id", "score"}, hsp: {"span_id"}, cond: {"conduit_id"}}, {srp: 1})  # 1 injected BB key
    c = rb.cand_fk_check(sp, targets)
    assert c["span_cols"] == sorted([srp, hsp]) and c["orphans"][srp]["rows"] == 1
    assert rb.cand_fk_verdict(c, srp) == "CAND_FK_ORPHANS"
    assert rb.cand_fk_verdict(c, hsp) is None and rb.cand_fk_verdict(c, cond) is None  # clean / no span_id
    assert not any(f"`{cond}` c" in q for q in sp.sql_log)
    boom = rb.cand_fk_check(_CandSpark({}, {}, boom=True), targets)
    assert "error" in boom and rb.cand_fk_verdict(boom, cond) == "CAND_FK_UNREADABLE"
    assert rb.cand_fk_verdict(None, srp) == "CAND_FK_UNREADABLE"
    assert rb.cand_fk_verdict({"span_cols": [srp], "orphans": {}}, srp) == "CAND_FK_UNREADABLE"  # unchecked
    assert rb.cand_fk_check(sp, {}) == {"span_source": rb.SPAN_V4, "span_cols": [], "orphans": {}, "no_cols": []}


def test_bug_qa_109_target_with_zero_column_rows_fails_closed():
    """A target present in UC but with 0 information_schema.columns rows cannot be proven span_id-free."""
    srp, hsp, cond = "span_risk_predictions_v4_candidate", "hazard_span_proximity_v4_candidate", rb._c("physical_resource_conduit")
    # QA repro: every query returns [] -> was {'span_cols': [], 'orphans': {}} -> verdict None (fail-open)
    empty = rb.cand_fk_check(_CandSpark({}, {}), {srp: False})
    assert empty["no_cols"] == [srp] and rb.cand_fk_verdict(empty, srp) == "CAND_FK_UNREADABLE"
    # Mixed: srp has no column rows; hsp clean with span_id; cond has columns but no span_id -> both still pass
    sp = _CandSpark({hsp: {"span_id"}, cond: {"conduit_id"}}, {})
    c = rb.cand_fk_check(sp, {srp: False, hsp: False, cond: False})
    assert c["no_cols"] == [srp] and "error" not in c
    assert rb.cand_fk_verdict(c, srp) == "CAND_FK_UNREADABLE"
    assert rb.cand_fk_verdict(c, hsp) is None and rb.cand_fk_verdict(c, cond) is None  # siblings not masked
    assert not any(f"`{srp}` c" in q for q in sp.sql_log)  # no orphan scan attempted for the unprovable target


def test_bug_qa_107_cand_fk_targets_include_non_managed_candidates():
    items = rb.runbook_items()
    srp, hsi = "span_risk_predictions_v4_candidate", "hazard_span_intersection_v4_candidate"
    for t in ("VIEW", "MATERIALIZED_VIEW", "METRIC_VIEW", "EXTERNAL", "STREAMING_TABLE"):
        objs = {i.candidate: "MANAGED" for i in items if i.candidate}
        objs[srp] = t
        assert srp in rb.cand_fk_targets(items, objs), t  # was skipped (fail-open) before BUG-QA-107
    objs = {i.candidate: "MANAGED" for i in items if i.candidate}
    objs.pop(srp)
    assert srp not in rb.cand_fk_targets(items, objs) and hsi in rb.cand_fk_targets(items, objs)  # missing -> MISSING_CANDIDATE


class _HalfBoomSpark(_CandSpark):
    """Orphan scan raises for one table (e.g. an unscannable MV/metric view); the others read fine."""
    def __init__(self, cols, orphans, bad):
        super().__init__(cols, orphans)
        self.bad = bad

    def sql(self, q, args=None):
        if f"`{self.bad}` c" in q:
            raise RuntimeError("METRIC_VIEW_NOT_SCANNABLE")
        return super().sql(q, args)


def test_bug_qa_107_unscannable_candidate_fails_closed_per_table():
    srp, hsp = "span_risk_predictions_v4_candidate", "hazard_span_proximity_v4_candidate"
    c = rb.cand_fk_check(_HalfBoomSpark({srp: {"span_id"}, hsp: {"span_id"}}, {}, bad=srp), {srp: False, hsp: False})
    assert "error" not in c and "error" in c["orphans"][srp]
    assert rb.cand_fk_verdict(c, srp) == "CAND_FK_UNREADABLE"
    assert rb.cand_fk_verdict(c, hsp) is None  # a clean sibling is not masked by the bad one
    assert rb.cand_fk_verdict({"span_cols": [srp], "orphans": {srp: {"keys": 0}}}, srp) == "CAND_FK_UNREADABLE"


def test_bug_qa_104_dry_run_full_mode_cand_fk_orphans_block(monkeypatch):
    srp, hsi = "span_risk_predictions_v4_candidate", "hazard_span_intersection_v4_candidate"
    seen = _dry_run_fixture(monkeypatch, {"span_cols": [srp, hsi],
                                          "orphans": {srp: {"rows": 92, "keys": 92}, hsi: {"rows": 18495, "keys": 92}}})
    fs = rb.dry_run(object(), None, verbose=False, pin_guard=False)
    f = {x.item.live: x for x in fs}
    assert f["span_risk_predictions"].verdict == "CAND_FK_ORPHANS" and f["span_risk_predictions"].details["cand_fk"]["rows"] == 92
    assert f["hazard_span_intersection"].verdict == "CAND_FK_ORPHANS"
    assert f["physical_resource_span"].verdict == "READY" and f["resource_alarm"].verdict == "READY"
    assert rb.SPAN_V4 not in seen
    s = rb.summary(fs)
    assert s["blocking"] >= 2 and not s["cutover_ready"]
    # clean candidates: the same items go READY (the gate is the only thing that changed)
    _dry_run_fixture(monkeypatch, {"span_cols": [srp, hsi], "orphans": {srp: {"rows": 0}, hsi: {"rows": 0}}})
    f = {x.item.live: x.verdict for x in rb.dry_run(object(), None, verbose=False, pin_guard=False)}
    assert f["span_risk_predictions"] == "READY" and f["hazard_span_intersection"] == "READY"
    # unreadable check fails closed on every promote candidate
    _dry_run_fixture(monkeypatch, {"error": "boom", "span_cols": [], "orphans": {}})
    f = {x.item.live: x.verdict for x in rb.dry_run(object(), None, verbose=False, pin_guard=False)}
    assert f["physical_resource_conduit"] == "CAND_FK_UNREADABLE"
    assert f["physical_resource_span"] == "READY"  # the span candidate is the FK parent, never cand-FK gated


def test_bug_qa_104_partial_mode_kept_candidates_unaffected(monkeypatch):
    srp = "span_risk_predictions_v4_candidate"
    seen = _dry_run_fixture(monkeypatch, {"span_cols": [srp], "orphans": {srp: {"rows": 92}}})
    f = {x.item.live: x.verdict for x in rb.dry_run(object(), None, verbose=False, pin_guard=False, partial_cutover=True)}
    assert f["span_risk_predictions"] == rb.PARTIAL_VERDICT and srp not in seen


def test_bug_qa_104_schema_wide_unlisted_consumer_scan():
    objs = {rb.BRIDGE_TABLE: "MANAGED"}
    cons = rb.bridge_consumers(False)

    class _ScanSpark(_BridgeSpark):
        def sql(self, q, args=None):
            if "information_schema.columns" in q and "table_name IN (" in q:  # honour the watch-list filter
                self.sql_log.append(q)
                names = set(re.findall(r"'(\w+)'", q.split("table_name IN (")[1]))
                return _Res([_Row(table_name=t, column_name=c) for t, cs in self.cols.items() if t in names for c in cs])
            if "AS n" in q and not any(f"`{t}` c" in q for t in rb.BRIDGE_FK_CONSUMERS):
                self.sql_log.append(q)
                t = next(t for t in self.cols if f"`{t}` c" in q)
                n = self.orphans.get(t, 0)
                return _Res([_Row(n=n, k=min(n, 92))])
            return super().sql(q, args)

    def spark(extra, **kw):
        cols = {t: {"span_id"} for t in rb.BRIDGE_FK_CONSUMERS}  # promoted ones are skipped by the full-mode scan
        cols[rb.BRIDGE_TABLE] = {"bb_span_id", "bbs_span_id"}
        cols.update(extra)
        return _ScanSpark(cols=cols, **kw)

    extra = {"new_span_log": {"span_id"}, "logical_resource": {"span_id", "x"},
             "hazard_span_intersection": {"span_id"},  # promoted in full mode: replaced, never scanned
             "service_path_regen_candidate": {"span_id"}, "access_span_regen": {"span_id"},  # staging: exempt
             rb.SPAN_V4: {"span_id"}, "physical_resource_span": {"span_id"}, "no_span": {"other"}}
    ok = rb.bridge_check(spark(extra), objs, consumers=cons)
    assert set(ok["scanned"]) == {"new_span_log", "logical_resource"} and ok["unlisted_consumers"] == []
    assert ok["scan_exempt"] == ["access_span_regen", "service_path_regen_candidate"]
    assert rb.bridge_verdict(ok, True) == "READY"
    bad = rb.bridge_check(spark(extra, orphans={"new_span_log": 7}), objs, consumers=cons)
    assert bad["unlisted_consumers"] == ["new_span_log"] and rb.bridge_verdict(bad, True) == "BRIDGE_CONSUMER_SET_DRIFT"
    # partial mode: HSI is kept on v3, so it is a listed consumer, not an unlisted one
    p = rb.bridge_check(spark(extra), objs)
    assert "hazard_span_intersection" in p["orphans"] and "hazard_span_intersection" not in p["scanned"]
    assert rb.bridge_verdict(p, True) == "READY"


# ---------------------------------------------------------------- P79 pin commit guard
def test_p79_pin_risk_classification_fail_closed():
    lo = rb.pin_risk(31, 31, 228.9)
    assert lo["status"] == "PIN_LATEST_ONLY" and lo["commit_guard"] == rb.PIN_BLOCK
    assert rb.pin_risk(31, 31, 228.9, backed_up=True)["commit_guard"] == rb.PIN_WARN  # backup lifts the block
    assert rb.pin_risk(23, 24, 189.0)["status"] == "PIN_EXPIRED"  # HSI v3 v23 after the 10-31 CHANGE COLUMN
    assert rb.pin_risk(23, 24, 189.0)["commit_guard"] == rb.PIN_WARN
    ok = rb.pin_risk(5, 5, 25.0)
    assert ok["status"] == "PIN_OK" and ok["commit_guard"] == rb.PIN_ALLOW and ok["expires_in_h"] == 143.0
    assert rb.pin_risk(5, 5, 130.0)["commit_guard"] == rb.PIN_WARN  # > PIN_WARN_HOURS
    assert rb.pin_risk(4, 5, 10.0)["status"] == "PIN_SUPERSEDED_EXPIRING"
    for args in ((None, 5, 1.0), (5, None, 1.0), (5, 5, None)):
        u = rb.pin_risk(*args)
        assert u["status"] == "PIN_UNKNOWN" and u["commit_guard"] == rb.PIN_BLOCK


def test_p79_commit_targets_cover_comment_tag_alter_optimize():
    fq = rb.FQ
    cases = {
        f"COMMENT ON COLUMN {fq}.`customer`.`name` IS 'x'": ["customer"],
        f"COMMENT ON TABLE {fq}.logical_resource IS 'x'": ["logical_resource"],
        f"ALTER TABLE {fq}.`hazard_span_intersection` CHANGE COLUMN hazard_source_id COMMENT 'x'": ["hazard_span_intersection"],
        f"ALTER TABLE {fq}.customer SET TAGS ('telco_project' = 'provable_resilience_intelligence')": ["customer"],
        f"SET TAG ON TABLE {fq}.customer telco_project = provable_resilience_intelligence": ["customer"],
        f"SET TAG ON COLUMN {fq}.customer.name pii": ["customer"],
        "optimize provable_resilience_intelligence.customer": ["customer"],
        "OPTIMIZE customer": ["customer"],  # unqualified -> this schema
        f"CREATE OR REPLACE TABLE {fq}.`customer__v3_rollback` DEEP CLONE {fq}.`customer`": ["customer__v3_rollback"],
        f"-- note\nVACUUM {fq}.a; UPDATE {fq}.b SET x = 1": ["a", "b"],
        f"SELECT * FROM {fq}.customer": [],
        f"DESCRIBE HISTORY {fq}.customer": [],
        "COMMENT ON TABLE other_cat.other_schema.customer IS 'x'": [],  # other schema: not guarded
        "ALTER TABLE other_schema.customer SET TAGS ('a' = 'b')": [],
    }
    for sql, want in cases.items():
        assert rb.commit_targets(sql) == want, sql


def _guard(**objs):
    return {"by_object": {n: {**rb.pin_risk(*a), "restore_version": a[0], "restore_age_h": a[2],
                              "manifest_version": rb.V3} for n, a in objs.items()}}


def test_p79_check_commit_blocks_latest_only_until_backup(monkeypatch):
    g = _guard(customer=(8, 8, 213.0), span_bb_route_bridge=(3, 3, 25.0))
    r = rb.check_commit(f"COMMENT ON COLUMN {rb.FQ}.customer.name IS 'x'", g)
    assert r["verdict"] == rb.PIN_BLOCK and r["blocked"] == ["customer"]
    assert any(f"DEEP CLONE {rb.FQ}.`customer`" in s for s in r["remedy"])
    assert rb.check_commit(f"OPTIMIZE {rb.FQ}.span_bb_route_bridge", g)["verdict"] == rb.PIN_ALLOW
    assert rb.check_commit(f"OPTIMIZE {rb.FQ}.not_pinned", g)["verdict"] == rb.PIN_ALLOW
    g2 = _guard(customer=(8, 8, 213.0, True))
    assert rb.check_commit(f"ALTER TABLE {rb.FQ}.customer SET TAGS ('a'='b')", g2)["verdict"] == rb.PIN_WARN
    with pytest.raises(rb.PinCommitBlocked):
        rb.assert_commit_allowed(None, f"ALTER TABLE {rb.FQ}.customer SET TAGS ('a'='b')", g)
    assert rb.assert_commit_allowed(None, "SELECT 1", g)["verdict"] == rb.PIN_ALLOW


def test_p79_pin_backup_sql_is_text_only_dec46_names():
    g = _guard(customer=(8, 8, 213.0), ok_tbl=(3, 3, 25.0), done=(8, 8, 213.0, True))
    s = rb.pin_backup_sql(g)
    clones = [x for x in s if not x.startswith("--")]
    assert clones == [f"CREATE OR REPLACE TABLE {rb.FQ}.`customer{rb.ROLLBACK_BACKUP_SUFFIX}` DEEP CLONE "
                      f"{rb.FQ}.`customer`  -- P79/DEC-46 pre-commit backup (pin v8, 213.0h)"]
    assert not rb.uses_time_travel(s)


class _PinRow(dict):
    __getattr__ = dict.get


class _PinDF:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return self.rows

    def first(self):
        return self.rows[0]

    def select(self, *_):
        return self


class _PinSpark:
    def __init__(self, manifest, history, po="ENABLE (inherited from METASTORE m)"):
        self.manifest, self.history, self.po, self.queries = manifest, history, po, []

    def sql(self, q, args=None):
        import datetime as dt
        self.queries.append(q)
        assert q.lstrip().upper().startswith(("SELECT", "DESCRIBE")), q
        now = dt.datetime(2026, 11, 1, 12, 0)
        if "current_timestamp" in q:
            return _PinDF([_PinRow(now=now)])
        if "demo_freeze_manifest" in q:
            return _PinDF([_PinRow(object_name=n, delta_version=None, restore_version=rv, row_count=1, freeze_status="FROZEN")
                        for (mv, n), rv in self.manifest.items() if mv == args["v"]])
        if q.startswith("DESCRIBE HISTORY"):
            name = q.split("`")[1]
            if name not in self.history:
                raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")
            return _PinDF([_PinRow(version=v, timestamp=now - dt.timedelta(hours=h)) for v, h in self.history[name]])
        if q.startswith("DESCRIBE TABLE EXTENDED"):
            return _PinDF([_PinRow(col_name="Predictive Optimization", data_type=self.po)])
        raise AssertionError(q)


def test_p79_pin_commit_guard_read_only_and_reproduces_dp_probe():
    manifest = {(rb.V3, "customer"): 8, (rb.V3, "hazard_span_intersection"): 24, (rb.V3, "span_bb_route_bridge"): 3,
                (rb.V4_DRAFT, "hazard_span_intersection_v4_candidate"): 34, (rb.V3, "gone"): 2}
    history = {"customer": [(8, 213.0), (7, 214.0)], "hazard_span_intersection": [(24, 23.0), (23, 189.0)],
               "span_bb_route_bridge": [(3, 25.0)], "hazard_span_intersection_v4_candidate": [(34, 22.0)]}
    sp = _PinSpark(manifest, history)
    g = rb.pin_commit_guard(sp, objs={"customer": "MANAGED"})
    assert g["latest_only"] == ["customer"]
    assert g["commit_blocked"] == ["customer", "gone"]  # unreadable history fails closed (PIN_UNKNOWN)
    assert g["by_object"]["hazard_span_intersection"]["commit_guard"] == rb.PIN_ALLOW
    assert len(g["pins"]) == 5 and len(g["po_enabled"]) == 5
    g2 = rb.pin_commit_guard(sp, objs={"customer": "MANAGED", "customer__v3_rollback": "MANAGED"}, check_po=False)
    assert "customer" not in g2["commit_blocked"] and g2["predictive_optimization"] == {}


def test_p79_gate0_falls_back_to_dec46_backup_when_pin_unreadable():
    it = rb.Item("x", "customer", None, "", "keep_v3")
    rs = rb.gate0_restore_sql(it, 8, readable=False, backup_exists=True)
    assert rs[0].startswith(f"CREATE OR REPLACE TABLE {rb.FQ}.`customer` DEEP CLONE {rb.FQ}.`customer__v3_rollback`")
    assert not rb.uses_time_travel(rs)
    assert "escalate to @pm" in rb.gate0_restore_sql(it, 8, readable=False)[0]  # unchanged without a backup


def test_p79_summary_reports_pin_commit_blocked_non_blocking():
    it = rb.Item("x", "customer", None, "", "regenerate")
    f = rb.Finding(it, "POST_CUTOVER", {"pin_guard": rb.pin_risk(8, 8, 213.0)})
    s = rb.summary([f])
    assert s["pin_commit_blocked"] == ["customer"] and s["blocking"] == 0
