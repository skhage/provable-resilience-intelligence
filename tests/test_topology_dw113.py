"""BUG-DW-113: /topology auth_expired residuals.

(1) Legend copy: when the SRLG fetch is auth_expired (401/403) the legend line names the
    likely cause: 'SRLG data unavailable for <region>: session may have expired.'
    Transient outages keep the v3 copy 'SRLG data unavailable for <region>.'
(2) PathTraceBanner gates Retry with showTraceRetry(mode), the same helper as the mobile
    sticky summary, so the two cannot drift apart.
(3) Optional item: the sticky-summary Retry is described by its message span
    (aria-describedby), and the visible label is unchanged.
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
_TOPO = os.path.join(UI, "routes", "topology.tsx")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings",
                        "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _fn_block(src, name, end_marker):
    start = src.index(name)
    return src[start:src.index(end_marker, start)]


# ---------- (1) legend copy ----------

@needs_node
def test_legend_copy_auth_expired_names_session():
    out = _node("out = [m.srlgUnavailableMsg('West', 'auth_expired'), m.SRLG_SESSION_EXPIRED_SUFFIX];")
    assert out[0] == "SRLG data unavailable for West: session may have expired."
    assert out[1] == ": session may have expired."


@needs_node
def test_legend_copy_other_states_unchanged():
    out = _node("out = [m.srlgUnavailableMsg('West'), m.srlgUnavailableMsg('West', null),"
                " m.srlgUnavailableMsg('West', 'unavailable')];")
    assert out == ["SRLG data unavailable for West."] * 3


@needs_node
def test_legend_line_still_shown_for_auth_expired():
    # The line is kept (not suppressed) so the overlay never renders silently empty.
    out = _node("out = [m.showSrlgUnavailable(true, 'West', 'auth_expired'),"
                " m.showSrlgUnavailable(true, 'West', 'live')];")
    assert out == [True, False]


def test_legend_passes_srlg_state_through():
    src = _strip_comments(_read(_TOPO))
    legend = _fn_block(src, "function Legend(", "if (collapsed)")
    assert "srlgUnavailableState = null" in legend
    assert "srlgUnavailableMsg(srlgUnavailableRegion, srlgUnavailableState)" in legend
    call = src[src.index("<Legend\n"):]
    call = call[:call.index("/>")]
    assert "srlgUnavailableState={srlgState}" in call
    # same neutral class as before (iron, no new color)
    assert 'className="legend-coverage-note legend-srlg-unavailable"' in legend


# ---------- (2) single Retry gate ----------

def test_path_trace_banner_uses_show_trace_retry():
    src = _strip_comments(_read(_TOPO))
    banner = _fn_block(src, "function PathTraceBanner(", "const workingHops")
    assert "showTraceRetry(mode) && onRetry" in banner
    assert not re.search(r"mode\s*===\s*[\"']unavailable[\"']", banner)


def test_no_inline_unavailable_retry_gate_anywhere_in_topology():
    src = _strip_comments(_read(_TOPO))
    assert not re.search(r"(mode|traceMode)\s*===\s*[\"']unavailable[\"']", src)


# ---------- (3) optional: sticky-summary Retry context ----------

def test_mobile_retry_described_by_message_span():
    src = _strip_comments(_read(_TOPO))
    assert src.count('id="mobile-trace-summary-msg"') == 1
    m = re.search(r'<button[^>]*className="path-trace-retry mobile-tree-retry"[^>]*>', src, re.S)
    assert m and 'aria-describedby="mobile-trace-summary-msg"' in m.group(0)
    # visible label unchanged
    tail = src[m.end():m.end() + 120]
    assert "{retryBusy ? RETRYING_LABEL : RETRY_LABEL}" in tail


def test_no_old_brand_name():
    needle = "lu" + "men"
    for p in (_LIB, _TOPO):
        assert needle not in _read(p).lower()
