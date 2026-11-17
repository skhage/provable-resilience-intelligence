"""BUG-DW-191: /actions Type label keeps the NOC acronym ('Escalate to NOC'), and the hazard
table 'Showing a-b of N' range is thousands-grouped with formatCount().

Node evaluation of the pure helper module plus static source checks.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_COPY = os.path.join(UI, "lib", "action-queue-copy.ts")
_HZ = os.path.join(UI, "components", "hazards", "hazard-summary-table.tsx")
_AQ = os.path.join(UI, "components", "actions", "action-queue-table.tsx")


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


# ---------- (1) acronym-preserving action type label ----------

def test_escalate_noc_label():
    assert _node_ts(_COPY, "M.actionTypeLabel('escalate_noc')") == "Escalate to NOC"


def test_escalate_noc_label_case_and_whitespace_insensitive():
    d = _node_ts(_COPY, "[M.actionTypeLabel('ESCALATE_NOC'), M.actionTypeLabel(' escalate_noc ')]")
    assert d == ["Escalate to NOC", "Escalate to NOC"]


@pytest.mark.parametrize("raw,label", [
    ("reroute", "Reroute"),
    ("dispatch_crew", "Dispatch crew"),
    ("notify_customer", "Notify customer"),
    ("preposition_splice", "Preposition splice"),
])
def test_other_live_types_use_generic_rule(raw, label):
    assert _node_ts(_COPY, "M.actionTypeLabel(" + json.dumps(raw) + ")") == label


def test_null_empty_and_prototype_keys_safe():
    d = _node_ts(_COPY, "[M.actionTypeLabel(null), M.actionTypeLabel(''), "
                        "M.actionTypeLabel('toString'), M.actionTypeLabel('__proto__')]")
    # Own-property guard: prototype keys fall through to the generic rule, never an object.
    assert d == ["", "", "Tostring", "Proto"]


def test_known_label_map_exported_with_escalate_noc_only():
    d = _node_ts(_COPY, "M.ACTION_TYPE_LABEL")
    assert d == {"escalate_noc": "Escalate to NOC"}


def test_no_css_text_transform_used_for_label():
    s = _read(_AQ)
    assert "{actionTypeLabel(a.action_type)}" in s
    assert "text-transform" not in s


# ---------- (2) hazard 'Showing a-b of N' grouping ----------

def test_hazard_showing_total_grouped():
    s = _read(_HZ)
    assert "of {sorted.length}" not in s
    assert "of {formatCount(sorted.length)}" in s


def test_hazard_showing_range_grouped():
    s = _read(_HZ)
    assert "Showing {formatCount((safePage - 1) * pageSize + 1)}" in s
    assert "{formatCount(Math.min(safePage * pageSize, sorted.length))}" in s
    assert re.search(r"Showing \{\(safePage", s) is None


def test_hazard_page_counter_still_grouped():
    s = _read(_HZ)
    assert "Page {formatCount(safePage)} of {formatCount(totalPages)}" in s


# ---------- brand guard ----------

@pytest.mark.parametrize("path", [_COPY, _HZ], ids=os.path.basename)
def test_brand_guard(path):
    assert "lum" + "en" not in _read(path).lower()
