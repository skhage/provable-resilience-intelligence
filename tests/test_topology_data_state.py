"""BUG-DW-098: /topology distinguishes live-unavailable from not-found and no-data.

Pure helpers in ui/lib/topology-data-state.ts are evaluated with Node (>= 22.18 strips
TS types). JSX wiring in routes/topology.tsx is checked statically (no npm on serverless).
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
    """Run an ES module body with `m` = the real TS module; body must set `out`."""
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- classifyResponse ---------------------------------------------------------

@needs_node
@pytest.mark.parametrize("status,header,expected", [
    (200, "live", "live"),
    (200, None, "live"),                # older backend / no header: v3 render
    (200, "unavailable", "unavailable"),  # path-trace / srlgs outage = 200 + []
    (200, "Unavailable", "unavailable"),
    (503, "unavailable", "unavailable"),  # diversity outage
    (503, None, "unavailable"),
    (500, None, "unavailable"),
    (404, None, "not_found"),            # diversity: service genuinely absent
    (401, None, "auth_expired"),          # BUG-DW-106 item 4
    (403, "unavailable", "auth_expired"),  # auth wins over the outage header
    (400, None, "unavailable"),
])
def test_classify_response(status, header, expected):
    assert _node(f"out = m.classifyResponse({status}, {json.dumps(header)});") == expected


# --- fetchWithState with a mocked fetch -----------------------------------------

def _mock_fetch(status, header, body):
    return (
        "globalThis.fetch = async () => ({ status: %d, headers: { get: (k) => k === 'X-PRI-Data-Source' ? %s : null },"
        " json: async () => (%s) });" % (status, json.dumps(header), json.dumps(body))
    )


@needs_node
def test_fetch_unavailable_header_drops_data():
    out = _node(_mock_fetch(200, "unavailable", []) + "out = await m.fetchWithState('/x');")
    assert out == {"state": "unavailable", "data": None}


@needs_node
def test_fetch_live_returns_data():
    hops = [{"path_type": "working"}]
    out = _node(_mock_fetch(200, "live", hops) + "out = await m.fetchWithState('/x');")
    assert out == {"state": "live", "data": hops}


@needs_node
def test_fetch_503_and_404_differ():
    a = _node(_mock_fetch(503, "unavailable", {"detail": "x"}) + "out = await m.fetchWithState('/x');")
    b = _node(_mock_fetch(404, None, {"detail": "x"}) + "out = await m.fetchWithState('/x');")
    assert a["state"] == "unavailable" and b["state"] == "not_found"
    assert a["data"] is None and b["data"] is None


@needs_node
def test_fetch_network_error_is_unavailable():
    out = _node("globalThis.fetch = async () => { throw new Error('net'); };"
                "out = await m.fetchWithState('/x');")
    assert out == {"state": "unavailable", "data": None}


# --- banner mode + copy -----------------------------------------------------------

@needs_node
@pytest.mark.parametrize("path,div,expected", [
    (None, None, "pending"),
    ("live", None, "pending"),
    ("live", "live", "live"),
    ("unavailable", "live", "unavailable"),
    ("live", "unavailable", "unavailable"),
    ("unavailable", "unavailable", "unavailable"),
    ("live", "not_found", "not_found"),
    ("unavailable", "not_found", "not_found"),
])
def test_trace_banner_mode(path, div, expected):
    assert _node(f"out = m.traceBannerMode({json.dumps(path)}, {json.dumps(div)});") == expected


@needs_node
def test_banner_copy_503_vs_404():
    out = _node("out = [m.traceBannerMessage('unavailable','SVC-00001'),"
                " m.traceBannerMessage('not_found','SVC-99999'),"
                " m.traceBannerMessage('live','SVC-00001'), m.traceBannerMessage('pending','SVC-00001')];")
    assert out == ["Path data is temporarily unavailable.", "Service SVC-99999 not found.", None, None]
    assert "protect" not in out[0].lower() and "protect" not in out[1].lower()


@needs_node
def test_srlg_unavailable_line():
    out = _node("out = [m.showSrlgUnavailable(true,'West','unavailable'), m.showSrlgUnavailable(true,'West','live'),"
                " m.showSrlgUnavailable(false,'West','unavailable'), m.showSrlgUnavailable(true,null,'unavailable'),"
                " m.srlgUnavailableMsg('West')];")
    assert out == [True, False, False, False, "SRLG data unavailable for West."]


# --- JSX wiring (static) -------------------------------------------------------------

def _banner_nonlive_block(src):
    start = src.index("if (nonLiveMessage) {")
    end = src.index("// V4-KPI-COPY-SPEC \u00a72.1: diverse services", start)
    return src[start:end]


def test_nonlive_banner_has_no_badge_no_hop_stats_but_retry_and_clear():
    blk = _banner_nonlive_block(_read("routes", "topology.tsx"))
    assert "diversity-badge" not in blk
    assert "path-trace-stats" not in blk and "protect" not in blk.lower()
    # BUG-DW-105: role="status" moved to a persistent sr-only region outside PathTraceBanner
    # The non-live block now uses aria-busy on the container instead
    assert "path-trace-retry" in blk and 'mode === "unavailable"' in blk
    assert "Clear trace" in blk


def test_fetches_read_header_not_raw_json():
    src = _read("routes", "topology.tsx")
    assert re.search(r"fetchWithState<PathHop\[\]>\(`/api/topology/path-trace/", src)
    assert re.search(r"fetchWithState<ServiceDiversity>\(`/api/topology/diversity/", src)
    assert re.search(r"fetchWithState<SrlgMember\[\]>\(`/api/topology/srlgs", src)
    # the old header-blind fetches are gone
    assert "fetch(`/api/topology/path-trace/" not in src
    assert "r.ok ? r.json() : null" not in src


def test_live_render_condition_unchanged_and_outage_always_disclosed():
    src = _read("routes", "topology.tsx")
    # BUG-DW-111 item 3: live with 0 hops renders the neutral 'No traced path' banner.
    # BUG-DW-106: every settled mode (incl. auth_expired) renders it; only pending does not.
    assert 'tracedServiceId && traceMode !== "pending" && (' in src
    assert "traceMode={traceMode}" in src  # mobile tree uses the same states
    assert "srlgUnavailableRegion={" in src


def test_outage_styles_neutral_and_targets():
    css = open(os.path.join(UI, "styles", "lakelink-theme.css"), encoding="utf-8").read()
    start = css.index("/* BUG-DW-098")
    blk = css[start:css.index("/* BUG-DW-062: Error banner retry", start)]
    assert "#F26522" not in blk.upper() and "red" not in blk.lower().replace("no orange or red", "")
    assert "min-height: 44px" in blk and "outline: 2px solid #006272" in blk
    assert "CanvasText" in blk


def test_no_customer_real_name():
    for parts in (("lib", "topology-data-state.ts"), ("routes", "topology.tsx")):
        assert "lumen" not in _read(*parts).lower()
