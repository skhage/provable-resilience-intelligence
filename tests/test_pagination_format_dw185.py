"""BUG-DW-185: 'Page X of Y' is thousands-grouped in all 3 paginated tables, and the /actions
Type column uses a sentence-case actionTypeLabel() in source (not CSS text-transform).

Static source checks plus Node evaluation of the pure helper modules.
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
_AQ = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
_ST = os.path.join(UI, "components", "dashboard", "service-table.tsx")
_HZ = os.path.join(UI, "components", "hazards", "hazard-summary-table.tsx")
_COPY = os.path.join(UI, "lib", "action-queue-copy.ts")
_FMT = os.path.join(UI, "lib", "bb-srlg-disclosure.ts")
_CSS = os.path.join(UI, "styles", "lakelink-theme.css")
_TABLES = [_AQ, _ST, _HZ]


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


# ---------- (1) page counter grouping ----------

def test_format_count_groups_thousands():
    d = _node_ts(_FMT, "[M.formatCount(1081), M.formatCount(1), M.formatCount(12000)]")
    assert d == ["1,081", "1", "12,000"]


@pytest.mark.parametrize("path", _TABLES, ids=lambda p: os.path.basename(p))
def test_no_raw_total_pages(path):
    s = _read(path)
    assert "of {totalPages}" not in s
    assert "of {formatCount(totalPages)}" in s


@pytest.mark.parametrize("path", _TABLES, ids=lambda p: os.path.basename(p))
def test_current_page_also_grouped(path):
    s = _read(path)
    assert re.search(r"Page \{formatCount\((safeCurrentPage|safePage)\)\}", s)
    assert re.search(r"Page \{(safeCurrentPage|safePage)\}", s) is None


@pytest.mark.parametrize("path", _TABLES, ids=lambda p: os.path.basename(p))
def test_format_count_imported(path):
    s = _read(path)
    assert re.search(r"import \{[^}]*\bformatCount\b[^}]*\} from \"@/lib/bb-srlg-disclosure\"", s)


# ---------- (2) action type label ----------

def test_action_type_label_known_answers():
    d = _node_ts(_COPY, "[M.actionTypeLabel('reroute_service'), M.actionTypeLabel('escalate_noc'), "
                        "M.actionTypeLabel('preposition_splice'), M.actionTypeLabel('dispatch'), "
                        "M.actionTypeLabel('NOTIFY_CUSTOMER'), M.actionTypeLabel(null), M.actionTypeLabel('')]")
    # BUG-DW-191: escalate_noc now maps to 'Escalate to NOC' via ACTION_TYPE_LABEL.
    assert d == ["Reroute service", "Escalate to NOC", "Preposition splice", "Dispatch",
                 "Notify customer", "", ""]


def test_type_cell_uses_label_helper():
    s = _read(_AQ)
    assert "{actionTypeLabel(a.action_type)}" in s
    assert "a.action_type.replace(" not in s
    assert re.search(r"import \{[^}]*\bactionTypeLabel\b[^}]*\} from \"@/lib/action-queue-copy\"", s)


def test_no_css_text_transform_on_type_cell():
    css = _read(_CSS)
    for m in re.finditer(r"\.action-type-cell[^{]*\{([^}]*)\}", css):
        assert "text-transform" not in m.group(1)
