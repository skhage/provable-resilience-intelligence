"""BUG-DW-106: /topology outage-state polish (items 2 and 4; items 1 and 3 closed by BUG-DW-111).

(2) The mobile sticky summary offers the same Retry as the banner (44px target).
(4) 401/403 maps to 'auth_expired': session-expired copy, no Retry, focus target kept.
Pure helpers are evaluated with Node (type stripping); JSX wiring is checked statically.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _mobile_summary_nonlive_block(src):
    start = src.index("function MobileTreeView(")
    seg = src[start:]
    a = seg.index("traceBannerMessage(traceMode, tracedServiceId) && (")
    b = seg.index("</div>", a)
    return seg[a:b]


# --- item 4: auth_expired helpers -------------------------------------------

@needs_node
@pytest.mark.parametrize("status", [401, 403])
def test_401_403_are_auth_expired(status):
    assert _node(f"out = m.classifyResponse({status}, null);") == "auth_expired"


@needs_node
@pytest.mark.parametrize("path,div,expected", [
    ("auth_expired", "live", "auth_expired"),
    ("live", "auth_expired", "auth_expired"),
    ("auth_expired", "not_found", "auth_expired"),   # auth wins: the 404 cannot be trusted
    ("unavailable", "auth_expired", "auth_expired"),
    (None, "auth_expired", "pending"),
    ("unavailable", "live", "unavailable"),           # unchanged
])
def test_trace_mode_auth_priority(path, div, expected):
    assert _node(f"out = m.traceBannerMode({json.dumps(path)}, {json.dumps(div)});") == expected


@needs_node
def test_session_expired_copy_and_no_retry():
    out = _node(
        "out = [m.traceBannerMessage('auth_expired', 'SVC-1'), m.SESSION_EXPIRED_MSG,"
        " m.showTraceRetry('auth_expired'), m.showTraceRetry('not_found'),"
        " m.showTraceRetry('unavailable'), m.showTraceRetry('live'), m.showTraceRetry('pending')];")
    assert out[0] == out[1] == "Your session may have expired. Reload the page."
    assert out[2:] == [False, False, True, False, False]


@needs_node
def test_status_region_text_for_auth_expired():
    out = _node(
        "out = m.traceStatusText({mode: 'auth_expired', serviceId: 'SVC-1', busy: false,"
        " retryFeedback: null, diversityLabel: 'x', workingHops: 0, protectHops: 0});")
    assert out == "Your session may have expired. Reload the page."


@needs_node
def test_srlg_legend_discloses_auth_expired():
    assert _node("out = m.showSrlgUnavailable(true, 'West', 'auth_expired');") is True
    assert _node("out = m.showSrlgUnavailable(true, 'West', 'live');") is False


def test_banner_retry_still_unavailable_only():
    src = _read("routes", "topology.tsx")
    # banner Retry guard unchanged: auth_expired / not_found get no Retry
    assert '{mode === "unavailable" && onRetry && (' in src
    # the banner renders for auth_expired (any settled mode)
    assert 'tracedServiceId && traceMode !== "pending" && (' in src


def test_focus_moves_when_retry_lands_on_auth_expired():
    src = _read("routes", "topology.tsx")
    assert ('(traceMode === "live" || traceMode === "not_found" || traceMode === "auth_expired")'
            in src)


# --- item 2: mobile summary Retry ---------------------------------------------

def test_mobile_summary_has_guarded_retry():
    blk = _mobile_summary_nonlive_block(_read("routes", "topology.tsx"))
    assert "showTraceRetry(traceMode) && onRetry && (" in blk
    assert 'type="button"' in blk
    assert 'className="path-trace-retry mobile-tree-retry"' in blk
    assert "onClick={retryBusy ? undefined : onRetry}" in blk
    assert "aria-disabled={retryBusy || undefined}" in blk
    assert "{retryBusy ? RETRYING_LABEL : RETRY_LABEL}" in blk


def test_mobile_summary_is_not_a_live_region():
    # item 1 (closed by DW-111) must stay closed: no duplicate announcement
    src = _read("routes", "topology.tsx")
    for tag in re.findall(r'<div className="mobile-tree-diversity-summary"[^>]*>', src):
        assert "role=" not in tag and "aria-live" not in tag


def test_mobile_tree_wired_to_same_retry_handler():
    src = _read("routes", "topology.tsx")
    start = src.index("<MobileTreeView")
    call = src[start:src.index("/>", start)]
    assert "onRetry={() => { retryCountRef.current += 1; setTraceRetry((n) => n + 1); }}" in call
    assert "retryBusy={retryBusy}" in call
    assert "retryFeedback={retryFeedback}" in call


def test_mobile_retry_css_wraps_and_inherits_44px():
    css = _read("styles", "lakelink-theme.css")
    m = re.search(r"(?m)^\.mobile-tree-diversity-summary \{([^}]*)\}", css)
    assert m and "flex-wrap: wrap" in m.group(1)
    assert re.search(r"(?m)^\.mobile-tree-retry \{[^}]*margin-left: auto", css)
    # 44px comes from the existing .path-trace-retry mobile rule
    assert re.search(r"@media \(max-width: 768px\) \{\s*\.path-trace-retry \{\s*min-height: 44px;", css)


def test_no_lumen_in_changed_sources():
    for parts in [("routes", "topology.tsx"), ("lib", "topology-data-state.ts"),
                  ("styles", "lakelink-theme.css")]:
        assert "lumen" not in _read(*parts).lower()
