"""BUG-DW-104: /actions copy + polish (labels, label-in-name, mobile target, error alert,
hazard time zone, skeleton count, cancelled badge on zebra, route comment).

Static source checks plus Node evaluation of the pure helper module.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from test_action_queue_scroll_region import _computed

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_TSX = os.path.join(UI, "components", "actions", "action-queue-table.tsx")
_ROUTE = os.path.join(UI, "routes", "actions.tsx")
_CSS = os.path.join(UI, "styles", "lakelink-theme.css")
_COPY = os.path.join(UI, "lib", "action-queue-copy.ts")


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


# ---------- (1) one label map ----------

def test_status_label_map_known_answers():
    d = _node_ts(_COPY, "{m:M.STATUS_LABEL, all:M.statusLabel(undefined), "
                        "ip:M.statusLabel('in_progress'), odd:M.statusLabel('on_hold_by_noc')}")
    assert d["m"] == {"pending": "Pending", "in_progress": "In progress",
                      "completed": "Completed", "cancelled": "Cancelled"}
    assert d["all"] == "All"
    assert d["ip"] == "In progress"
    # Unknown enums: every underscore replaced (old bug replaced only the first).
    assert d["odd"] == "On hold by noc"


def test_toast_copy():
    d = _node_ts(_COPY, "[M.statusToast('in_progress','Acme Denver DIA'), M.statusToast('completed')]")
    assert d == ["Action marked In progress for Acme Denver DIA", "Action marked Completed"]


def test_tsx_has_no_first_underscore_replace_and_uses_label_map():
    s = _read(_TSX)
    assert '.replace("_", " ")' not in s
    assert "Action updated to" not in s
    assert "{statusLabel(s)}" in s
    assert "{statusLabel(a.status)}" in s
    assert "statusToast(variables.data.status, serviceName)" in s
    # Action type keeps its global replace.
    assert 'a.action_type.replace(/_/g, " ")' in s


# ---------- (2) no raw snake_case tooltip ----------

def test_action_type_has_no_native_title():
    assert "title={a.action_type}" not in _read(_TSX)


# ---------- (3) label in name ----------

def test_previous_button_label_in_name():
    s = _read(_TSX)
    assert "\u2039 Prev\n" not in s
    m = re.search(r'aria-label="Previous page"\s*>(.*?)</button>', s, re.S)
    assert m, "Previous button not found"
    visible = re.sub(r"\{/\*.*?\*/\}", "", m.group(1), flags=re.S)
    assert '<span aria-hidden="true">\u2039</span> Previous' in visible
    m2 = re.search(r'aria-label="Next page"\s*>(.*?)</button>', s, re.S)
    assert m2 and '<span aria-hidden="true">\u203a</span>' in m2.group(1)


# ---------- (4) mobile expand target + decorative chevrons ----------

def test_expand_toggle_44px_on_mobile_only():
    css = _read(_CSS)
    for w in (320, 375, 767):
        assert _computed(css, ".expand-toggle", "min-width", w) == "44px", w
        assert _computed(css, ".expand-toggle", "min-height", w) == "44px", w
    assert _computed(css, ".expand-toggle", "min-height", 1280) == "24px"


def test_chevrons_aria_hidden():
    s = _read(_TSX)
    for icon in ("ChevronUp", "ChevronDown"):
        tags = re.findall(r"<" + icon + r"\b[^>]*/>", s)
        assert tags, icon
        assert all('aria-hidden="true"' in t for t in tags), tags


# ---------- (5) error fallback announced ----------

def test_error_fallback_is_alert_with_spec_copy():
    s = _read(_TSX)
    assert '<div className="error-fallback" role="alert">' in s
    assert "<p>{ACTION_QUEUE_LOAD_ERROR}</p>" in s
    assert "Failed to load action queue" not in s
    d = _node_ts(_COPY, "M.ACTION_QUEUE_LOAD_ERROR")
    assert d == "Couldn\u2019t load the action queue. Check your connection and retry."


# ---------- (6) hazard time zone ----------

def test_hazard_time_has_zone_and_does_not_throw():
    # dateStyle/timeStyle + timeZoneName throws in ECMA-402; the helper must not.
    d = _node_ts(_COPY, "[M.formatHazardTime('2026-10-30T14:05:00Z','en-US','America/Denver'), "
                        "M.formatHazardTime('2026-10-30T14:05:00Z','en-US','UTC'), "
                        "M.formatHazardTime('not-a-date','en-US','UTC'), "
                        "'dateStyle' in M.HAZARD_TIME_FORMAT]")
    assert d[0] == "Oct 30, 2026, 8:05 AM MDT"
    assert d[1] == "Oct 30, 2026, 2:05 PM UTC"
    assert d[2] == "not-a-date"
    assert d[3] is False
    s = _read(_TSX)
    assert "toLocaleString()" not in s
    assert "{formatHazardTime(a.hazard_last_update)}" in s


# ---------- (7) skeleton count ----------

def test_skeleton_count_matches_kpi_row():
    assert _node_ts(_COPY, "[M.actionKpiSkeletonCount(true), M.actionKpiSkeletonCount(false)]") == [5, 4]
    s = _read(_TSX)
    assert "const skeletonCards = actionKpiSkeletonCount(useV4Kpis());" in s
    assert "Array.from({ length: skeletonCards })" in s
    assert "Array.from({ length: 4 })" not in s


# ---------- (8) cancelled badge on zebra ----------

def test_cancelled_badge_outline():
    css = _read(_CSS)
    assert _computed(css, ".badge.cancelled", "border-color", 1280) == "var(--lf-platinum-shade)"
    # v3 fill/text unchanged.
    assert _computed(css, ".badge.cancelled", "background", 1280) == "var(--lf-platinum)"
    assert _computed(css, ".badge.cancelled", "color", 1280) == "var(--lf-iron)"


# ---------- (9) route comment ----------

def test_route_comment_uses_cancelled():
    s = _read(_ROUTE)
    assert "dismissed" not in s
    assert "completed | cancelled" in s


def test_brand_no_old_name():
    for p in (_TSX, _ROUTE, _COPY):
        assert "lumen" not in _read(p).lower(), p
