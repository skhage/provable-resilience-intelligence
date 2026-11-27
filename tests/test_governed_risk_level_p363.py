"""P363-APP-GOVERNED-RISK-LEVEL-ALIGN (V4-KPI-COPY-SPEC §8, binding @designer S189).

Before: scorecard KPI cards were Critical/High/Medium/Low Risk at 40/60/75, so 537 services
scored 75-79.99 showed as Low Risk while the governed level is moderate; score-band.ts used a
second cut set (Excellent..Failing, 85/70/55/40); action priority badges reused risk words.
Now: governed critical/at_risk/moderate/healthy at 40/60/80 read from risk_band_vocabulary,
one label set on screen, and priority badges read P1 Urgent..P4 Low.
Live known answer (2026-11-27): 848 / 2,932 / 3,172 / 1,048 = 8,000, avg 61.5 -> Moderate band.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend import models as m  # noqa: E402
from resilience_scorecard.backend import risk_levels as rl  # noqa: E402
from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402
from resilience_scorecard.backend.services import mock_data as md  # noqa: E402

PKG = os.path.join(APP_SRC, "resilience_scorecard")
UI = os.path.join(PKG, "ui")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
QUEUE = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
BAND_TS = os.path.join(UI, "lib", "score-band.ts")
COPY_TS = os.path.join(UI, "lib", "action-queue-copy.ts")
CATALOG_PY = os.path.join(PKG, "backend", "services", "catalog_sql.py")
BANNED = "lu" + "men"
LIVE = {"critical_count": 848, "at_risk_count": 2932, "moderate_count": 3172, "healthy_count": 1048}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _node_ts(ts_path, expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(ts_path, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _strip_comments(s):
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


# ---------- §8.4 backend ----------

def test_summary_sql_reads_governed_vocabulary_not_literal_cuts():
    sql = cs._SUMMARY_SQL
    assert "FROM risk_band_vocabulary" in sql
    assert "is_governed = TRUE AND vocabulary = 'GOVERNED_RISK_LEVEL'" in sql
    for lvl in ("critical", "at_risk", "moderate", "healthy"):
        assert f"g.level = '{lvl}'" in sql and f"AS {lvl}_count" in sql
    assert not re.search(r"overall_score\s*[<>]=?\s*\d", sql), "no literal cuts in the summary SQL"
    for old in ("high_risk_count", "medium_risk_count", "low_risk_count"):
        assert old not in sql


def test_cuts_sql_orders_worst_to_best():
    assert "ORDER BY governed_sort_order" in cs._RISK_LEVEL_CUTS_SQL


def test_dead_risk_level_removed_from_catalog_sql():
    assert "def _risk_level" not in _read(CATALOG_PY)


def test_risk_level_enum_governed_and_priority_enum_separate():
    assert [e.value for e in m.RiskLevel] == ["critical", "at_risk", "moderate", "healthy"]
    # §8.3: stored priority data is unchanged, so it must not share the risk-level enum.
    assert [e.value for e in m.ActionPriority] == ["critical", "high", "medium", "low"]
    assert m.ProactiveActionOut.model_fields["priority"].annotation is m.ActionPriority


def test_summary_model_fields():
    f = m.ResilienceSummaryOut.model_fields
    for k in ("critical_count", "at_risk_count", "moderate_count", "healthy_count", "risk_level_cuts"):
        assert k in f, k
    for old in ("high_risk_count", "medium_risk_count", "low_risk_count"):
        assert old not in f, old


class _FakeSql(cs.CatalogSqlService):
    def __init__(self, cuts_rows):
        self._cuts_rows = cuts_rows

    def _execute(self, sql, row_limit=12000, params=None):
        if sql is cs._SUMMARY_SQL:
            return [{"total_services": 8000, "avg_resilience_score": 61.5, **LIVE,
                     "total_single_point_failures": 1, "total_srlg_groups": 809,
                     "total_revenue_at_risk_usd": 48445092.9}]
        if sql is cs._RISK_LEVEL_CUTS_SQL:
            return self._cuts_rows
        return None


def test_get_summary_live_known_answer_sums_to_total():
    live_cuts = [dict(c) for c in rl.GOVERNED_RISK_CUTS]
    out = _FakeSql(live_cuts).get_summary()
    assert {k: out[k] for k in LIVE} == LIVE
    assert sum(out[k] for k in LIVE) == out["total_services"] == 8000
    s = m.ResilienceSummaryOut(**out)
    assert [c.level.value for c in s.risk_level_cuts] == ["critical", "at_risk", "moderate", "healthy"]
    assert [c.score_min_inclusive for c in s.risk_level_cuts] == [0, 40, 60, 80]


def test_cuts_fall_back_to_constants_when_vocabulary_unavailable():
    out = _FakeSql(None).get_summary()
    assert out["risk_level_cuts"] == [dict(c) for c in rl.GOVERNED_RISK_CUTS]


@pytest.mark.parametrize("score,level", [
    (0, "critical"), (39.99, "critical"), (40, "at_risk"), (59.99, "at_risk"), (60, "moderate"),
    (75, "moderate"), (79.99, "moderate"), (80, "healthy"), (100, "healthy"),
    (None, "critical"), (float("nan"), "critical"),
])
def test_python_governed_level_boundaries(score, level):
    assert rl.governed_risk_level(score) == level
    if score is not None and score == score:
        assert md._risk_level(score) == level


def test_mock_summary_parity():
    scores = md.generate_mock_scores()
    s = md.generate_mock_summary(scores)
    assert s["critical_count"] + s["at_risk_count"] + s["moderate_count"] + s["healthy_count"] == len(scores)
    want = {lvl: 0 for lvl in ("critical", "at_risk", "moderate", "healthy")}
    for x in scores:
        want[rl.governed_risk_level(x["resilience_score"])] += 1
    assert [s[f"{k}_count"] for k in want] == list(want.values())
    m.ResilienceSummaryOut(**s)  # validates


# ---------- §8.1 KPI cards ----------

@pytest.mark.parametrize("level,caption", [
    ("critical", "Score below 40"), ("at_risk", "Score 40 to 59"),
    ("moderate", "Score 60 to 79"), ("healthy", "Score 80 or above"),
])
def test_caption_known_answers(level, caption):
    assert _node_ts(BAND_TS, f'M.riskLevelCaption("{level}")') == caption


def test_aria_known_answer_from_spec():
    assert _node_ts(BAND_TS, 'M.riskCardAria("at_risk", "2,932")') == "At Risk: 2,932 services, score 40 to 59"


def test_captions_and_bands_follow_api_cuts():
    cuts = ('[{level:"critical",score_min_inclusive:0,score_max_exclusive:50},'
            '{level:"at_risk",score_min_inclusive:50,score_max_exclusive:70},'
            '{level:"moderate",score_min_inclusive:70,score_max_exclusive:90},'
            '{level:"healthy",score_min_inclusive:90,score_max_exclusive:100.01}]')
    got = _node_ts(BAND_TS, f"[M.riskLevelCaption('at_risk', {cuts}), M.scoreBand(65, {cuts}).key, "
                            f"M.scoreBand(85, {cuts}).key, M.riskLevelCaption('healthy', {cuts})]")
    assert got == ["Score 50 to 69", "at_risk", "moderate", "Score 90 or above"]


def test_incomplete_api_cuts_fall_back_to_governed():
    got = _node_ts(BAND_TS, 'M.scoreBand(75, [{level:"critical",score_min_inclusive:0,score_max_exclusive:99}]).key')
    assert got == "moderate"


def test_header_cards_labels_classes_order():
    src = _strip_comments(_read(HEADER))
    order = [("critical", "critical"), ("high", "at_risk"), ("warning", "moderate"), ("success", "healthy")]
    pos = []
    for cls, lvl in order:
        i = src.index(f'<div className="kpi-card {cls}"\n           role="group" aria-label={{riskCardAria("{lvl}", ')
        pos.append(i)
        nxt = src.index('<div className="kpi-card', i + 10)
        card = src[i:nxt]
        assert f"{{RISK_LEVEL_LABEL.{lvl}}}" in card
        assert f'<div className="kpi-caption">{{riskLevelCaption("{lvl}", cuts)}}</div>' in card
    assert pos == sorted(pos)


def test_header_has_no_hard_coded_cuts():
    code = _strip_comments(_read(HEADER))
    assert not re.search(r"\b(40|60|75|80)\b", code), "cuts must come from the API / score-band"
    assert "const cuts = summary.risk_level_cuts;" in code


def test_label_known_answers():
    assert _node_ts(BAND_TS, "M.RISK_LEVEL_ORDER.map(k => M.RISK_LEVEL_LABEL[k])") == [
        "Critical", "At Risk", "Moderate", "Healthy"]


# ---------- §8.3 priority badges ----------

@pytest.mark.parametrize("stored,text,aria", [
    ("critical", "P1 Urgent", "Priority 1, urgent"),
    ("high", "P2 High", "Priority 2, high"),
    ("medium", "P3 Normal", "Priority 3, normal"),
    ("low", "P4 Low", "Priority 4, low"),
    (" HIGH ", "P2 High", "Priority 2, high"),
    (None, "Unranked", "Priority unranked"),
    ("", "Unranked", "Priority unranked"),
    ("toString", "Unranked", "Priority unranked"),
])
def test_priority_badge_known_answers(stored, text, aria):
    arg = "null" if stored is None else json.dumps(stored)
    assert _node_ts(COPY_TS, f"[M.priorityLabel({arg}), M.priorityAria({arg})]") == [text, aria]


def test_priority_badge_class_keeps_existing_tokens():
    got = _node_ts(COPY_TS, '["critical","high","medium","low",null].map(M.priorityBadgeClass)')
    assert got == ["critical", "high", "medium", "low", "neutral"]


def test_no_priority_text_equals_a_risk_label():
    texts = _node_ts(COPY_TS, "Object.values(M.PRIORITY_LABEL)")
    risk = {"Critical", "At Risk", "Moderate", "Healthy", "High", "Medium", "Low", "critical", "high", "medium", "low"}
    assert not set(texts) & risk


def test_queue_renders_priority_helpers_not_raw_value():
    src = _read(QUEUE)
    assert "{priorityLabel(a.priority)}" in src
    assert "aria-label={priorityAria(a.priority)}" in src
    assert "{a.priority}</span>" not in src
    assert '<th scope="col">Priority</th>' in src


# ---------- §8.5 #2 / #6 greps ----------

def _ui_files():
    for dp, _, fs in os.walk(UI):
        if "node_modules" in dp:
            continue
        for f in fs:
            if f.endswith((".ts", ".tsx", ".css")):
                yield os.path.join(dp, f)


def test_no_retired_labels_in_ui():
    pat = re.compile(r'High Risk|Medium Risk|Low Risk|Excellent|Failing|"Fair"|"Poor"')
    hits = [p for p in _ui_files() if pat.search(_read(p))]
    assert hits == []


def test_no_banned_brand_string():
    hits = [p for p in _ui_files() if BANNED in _read(p).lower()]
    hits += [p for p in (CATALOG_PY, os.path.abspath(__file__)) if BANNED in _read(p).lower()]
    assert hits == []
