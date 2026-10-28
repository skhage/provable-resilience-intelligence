"""BUG-DW-105: /topology Retry focus, feedback, in-flight guard, persistent status region.

Pure helpers in ui/lib/topology-data-state.ts are evaluated with Node (>= 22.18 strips
TS types). JSX wiring in routes/topology.tsx is checked statically (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
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
    """Run an ES module body with `m` = the real TS module; body must set `out`."""
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- stillUnavailableMsg --------------------------------------------------

@needs_node
def test_still_unavailable_msg_format():
    """The message includes HH:MM in 24h format."""
    out = _node("out = m.stillUnavailableMsg(new Date(2026, 9, 28, 14, 5));")
    assert out == "Still unavailable. Last checked 14:05."


@needs_node
def test_still_unavailable_msg_midnight():
    out = _node("out = m.stillUnavailableMsg(new Date(2026, 0, 1, 0, 0));")
    assert out == "Still unavailable. Last checked 00:00."


@needs_node
def test_still_unavailable_msg_single_digit_hour():
    out = _node("out = m.stillUnavailableMsg(new Date(2026, 0, 1, 9, 7));")
    assert out == "Still unavailable. Last checked 09:07."


# --- RETRYING_LABEL exported ----------------------------------------------

@needs_node
def test_retrying_label_exported():
    out = _node("out = m.RETRYING_LABEL;")
    assert out == "Retrying\u2026"


# --- JSX wiring: PathTraceBanner non-live block (static) ------------------

def _get_topology_src():
    return _read("routes", "topology.tsx")


def test_banner_accepts_busy_prop():
    src = _get_topology_src()
    assert "busy?: boolean;" in src
    assert "busy = false," in src


def test_banner_accepts_retry_feedback_prop():
    src = _get_topology_src()
    assert "retryFeedback?: string | null;" in src
    assert "retryFeedback = null," in src


def test_banner_accepts_banner_ref_prop():
    src = _get_topology_src()
    assert "bannerRef?: React.RefObject<HTMLDivElement | null>;" in src


def test_nonlive_banner_has_aria_busy():
    """The non-live block sets aria-busy={busy || undefined} on the container."""
    src = _get_topology_src()
    # Find the non-live block
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    assert "aria-busy={busy || undefined}" in block


def test_nonlive_banner_has_tabindex_minus1():
    """The non-live container has tabIndex={-1} for programmatic focus."""
    src = _get_topology_src()
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    assert "tabIndex={-1}" in block


def test_nonlive_banner_has_ref():
    """The non-live container has ref={bannerRef}."""
    src = _get_topology_src()
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    assert "ref={bannerRef}" in block


def test_retry_button_aria_disabled_when_busy():
    """The Retry button uses aria-disabled (not disabled) when busy, with a click guard."""
    src = _get_topology_src()
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    assert "aria-disabled={busy || undefined}" in block
    assert "onClick={busy ? undefined : onRetry}" in block


def test_retry_button_shows_retrying_label_when_busy():
    """The Retry button shows RETRYING_LABEL when busy."""
    src = _get_topology_src()
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    assert "{busy ? RETRYING_LABEL : RETRY_LABEL}" in block


def test_display_message_uses_retry_feedback():
    """The non-live block shows retryFeedback over the static message when set."""
    src = _get_topology_src()
    assert "const displayMessage = retryFeedback ?? nonLiveMessage;" in src
    assert "{displayMessage}" in src


def test_nonlive_banner_no_role_status_inline():
    """The visible banner div no longer has role=status (moved to persistent sr-only region)."""
    src = _get_topology_src()
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC", start)
    block = src[start:end]
    # Should NOT have role="status" on the banner div
    assert 'role="status"' not in block


def test_live_banner_no_role_status_inline():
    """The live banner div also no longer has inline role=status."""
    src = _get_topology_src()
    # The live div now has ref and tabIndex but no role
    assert '<div className="path-trace-banner" ref={bannerRef} tabIndex={-1}>' in src


# --- Persistent sr-only status region (issue 4) --------------------------

def test_persistent_status_region_mounted():
    """A persistent sr-only role=status region is mounted when tracedServiceId is set."""
    src = _get_topology_src()
    # Find the persistent region
    assert 'BUG-DW-105: persistent sr-only status region' in src
    idx = src.index('BUG-DW-105: persistent sr-only status region')
    block = src[idx:idx+500]
    assert 'role="status"' in block
    assert 'aria-live="polite"' in block
    assert 'aria-atomic="true"' in block
    assert 'className="sr-only"' in block


def test_persistent_region_shows_retrying_when_busy():
    """The persistent region shows RETRYING_LABEL when retryBusy is true."""
    src = _get_topology_src()
    idx = src.index('BUG-DW-105: persistent sr-only status region')
    block = src[idx:idx+500]
    assert "retryBusy" in block
    assert "RETRYING_LABEL" in block


def test_persistent_region_shows_retry_feedback():
    """The persistent region shows retryFeedback when set."""
    src = _get_topology_src()
    idx = src.index('BUG-DW-105: persistent sr-only status region')
    block = src[idx:idx+500]
    assert "retryFeedback" in block


# --- TopologyPage state and effects (issue 1, 3) --------------------------

def test_retry_busy_state_declared():
    src = _get_topology_src()
    assert "const [retryBusy, setRetryBusy] = useState(false);" in src


def test_retry_feedback_state_declared():
    src = _get_topology_src()
    assert 'const [retryFeedback, setRetryFeedback] = useState<string | null>(null);' in src


def test_retry_count_ref_declared():
    src = _get_topology_src()
    assert "const retryCountRef = useRef(0);" in src


def test_banner_focus_ref_declared():
    src = _get_topology_src()
    assert "const bannerFocusRef = useRef<HTMLDivElement | null>(null);" in src


def test_prev_trace_mode_ref_declared():
    src = _get_topology_src()
    assert 'const prevTraceModeRef = useRef<TraceBannerMode>("pending");' in src


def test_reset_effect_clears_retry_state():
    """When tracedServiceId changes, retryBusy/retryFeedback/retryCountRef reset."""
    src = _get_topology_src()
    # Find the reset effect
    reset_idx = src.index("BUG-DW-105: also reset retry tracking")
    block = src[reset_idx:reset_idx+300]
    assert "setRetryBusy(false)" in block
    assert "setRetryFeedback(null)" in block
    assert "retryCountRef.current = 0" in block
    assert 'prevTraceModeRef.current = "pending"' in block


def test_fetch_effect_sets_busy_on_retry():
    """The fetch effect sets retryBusy=true when isRetry is true."""
    src = _get_topology_src()
    assert "const isRetry = retryCountRef.current > 0;" in src
    assert "if (isRetry) setRetryBusy(true);" in src


def test_fetch_effect_sets_feedback_on_repeat_failure():
    """On retry failure, stillUnavailableMsg is called."""
    src = _get_topology_src()
    assert "setRetryFeedback(stillUnavailableMsg(new Date()));" in src


def test_focus_management_effect_exists():
    """Focus effect moves focus to banner after retry success."""
    src = _get_topology_src()
    assert 'BUG-DW-105: move focus to the banner container after a successful retry' in src
    idx = src.index('BUG-DW-105: move focus to the banner container')
    block = src[idx:idx+700]
    assert 'prev === "unavailable"' in block
    assert 'traceMode === "live"' in block
    assert 'traceMode === "not_found"' in block
    assert "retryCountRef.current > 0" in block
    assert "bannerFocusRef.current?.focus()" in block


def test_retry_handler_increments_ref():
    """The onRetry handler increments retryCountRef before bumping traceRetry."""
    src = _get_topology_src()
    assert "retryCountRef.current += 1; setTraceRetry" in src


def test_banner_render_passes_new_props():
    """PathTraceBanner render passes busy, retryFeedback, bannerRef."""
    src = _get_topology_src()
    assert "busy={retryBusy}" in src
    assert "retryFeedback={retryFeedback}" in src
    assert "bannerRef={bannerFocusRef}" in src


# --- CSS rules (static) --------------------------------------------------

def test_css_retry_aria_disabled():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    assert ".path-trace-retry[aria-disabled]" in css
    assert "opacity: 0.6" in css
    assert "pointer-events: none" in css


def test_css_banner_nodata_focus_visible():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    assert ".path-trace-banner-nodata:focus-visible" in css
    assert "outline: 2px solid #006272" in css


def test_css_tabular_nums_on_busy():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    assert ".path-trace-banner-nodata[aria-busy" in css
    assert "tabular-nums" in css


def test_css_forced_colors_disabled():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    idx = css.index("BUG-DW-105")
    block = css[idx:idx+600]
    assert "GrayText" in block


# --- Branding guard -------------------------------------------------------

def test_no_customer_real_name():
    for parts in (("lib", "topology-data-state.ts"), ("routes", "topology.tsx")):
        assert "lumen" not in _read(*parts).lower()
