"""BUG-DW-112: /topology DW-111 residuals (Lakelink Fiber resilience app).

(a) live summary with unknown diversity + hops > 0 must not say 'No path data'
(b) persistent trace region text comes from traceStatusText(all props) only
(c) mobile summary shows no diversity badge in live mode with 0 hops
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
TOPO = os.path.join(UI, "routes", "topology.tsx")
STATE_TS = os.path.join(UI, "lib", "topology-data-state.ts")
DIV_TS = os.path.join(UI, "lib", "diversity-copy.ts")


def _src(p):
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


def _strip_jsx_comments(s):
    return re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.S)


def _persistent_region(src):
    i = src.index("BUG-DW-105: persistent sr-only status region")
    j = src.index("</div>", i)
    return src[i:j]


def _mobile_live_block(src):
    i = src.index("!traceBannerMessage(traceMode, tracedServiceId) && (")
    j = src.index("</div>", i)
    return src[i:j]


# ---------- (a) ----------

def test_summary_label_unknown_is_not_rated():
    d = _node_ts(DIV_TS, "{u:M.diversitySummaryLabel(undefined), n:M.diversitySummaryLabel(null),"
                         " x:M.diversitySummaryLabel('bogus'), k:M.diversitySummaryLabel('unknown'),"
                         " f:M.diversitySummaryLabel('fully_diverse'), p:M.diversitySummaryLabel('partially_diverse'),"
                         " s:M.diversitySummaryLabel('single_path'), c:M.DIVERSITY_NOT_RATED,"
                         " badge:M.diversityLabel(undefined)}")
    assert d["c"] == "Diversity not rated"
    for k in ("u", "n", "x", "k"):
        assert d[k] == "Diversity not rated"
    assert (d["f"], d["p"], d["s"]) == ("Fully diverse", "Partially diverse", "Single path")
    # the visible badge label is unchanged
    assert d["badge"] == "No path data"


def test_live_summary_unknown_with_hops_copy():
    s = _node_ts(STATE_TS, "M.traceLiveSummary('SVC-1', 'Diversity not rated', 3, 0)")
    assert s == "SVC-1 traced: Diversity not rated, 3 working hops, no protect path."
    assert "No path data" not in s
    # 0 hops still uses the No traced path copy
    assert _node_ts(STATE_TS, "M.traceLiveSummary('SVC-1', 'Diversity not rated', 0, 0)") == \
        "No traced path for SVC-1."


def test_region_uses_summary_label_not_badge_label():
    region = _strip_jsx_comments(_persistent_region(_src(TOPO)))
    assert "diversityLabel: diversitySummaryLabel(diversity?.diversity_status)" in region
    assert "diversityLabel(diversity" not in region


# ---------- (b) ----------

def test_region_text_is_single_traceStatusText_call_with_real_props():
    region = _strip_jsx_comments(_persistent_region(_src(TOPO)))
    assert region.count("traceStatusText(") == 1
    assert "busy: retryBusy," in region
    assert re.search(r"\bretryFeedback,", region)
    assert "busy: false" not in region
    assert "retryFeedback: null" not in region
    # no outer ternary duplicating the priority order
    assert "? RETRYING_LABEL" not in region
    assert "retryBusy\n" not in region
    # the call is the only child expression: '{traceStatusText({' directly inside the div
    assert re.search(r'aria-atomic="true">\s*\{traceStatusText\(\{', region)


def test_traceStatusText_priority_order():
    base = ("{mode:'live', serviceId:'S', diversityLabel:'Single path', workingHops:2, protectHops:0")
    d = _node_ts(STATE_TS, "["
                 + "M.traceStatusText(" + base + ", busy:true, retryFeedback:'FB'}),"
                 + "M.traceStatusText(" + base + ", busy:false, retryFeedback:'FB'}),"
                 + "M.traceStatusText(" + base + ", busy:false, retryFeedback:null}),"
                 + "M.RETRYING_LABEL]")
    assert d[0] == d[3]
    assert d[1] == "FB"
    assert d[2] == "S traced: Single path, 2 working hops, no protect path."


# ---------- (c) ----------

def test_mobile_live_zero_hops_suppresses_badge():
    blk = _strip_jsx_comments(_mobile_live_block(_src(TOPO)))
    m = re.search(r"\{tracedHopCount === 0 \? \(\s*<span className=\"mobile-tree-no-path\">"
                  r"\{noTracedPathMsg\(tracedServiceId\)\}</span>\s*\) : \(\s*"
                  r"diversityBadge\(diversity\.diversity_status\)\s*\)\}", blk)
    assert m, blk[:800]
    # badge is only rendered via that branch
    assert blk.count("diversityBadge(") == 1
    # BB-unverified qualifier is also suppressed at 0 hops
    assert "tracedHopCount !== 0 && showBackboneUnverified(" in blk


def test_mobile_receives_total_hop_count():
    src = _src(TOPO)
    assert "tracedHopCount={pathHops.length}" in src
    assert "tracedHopCount?: number;" in src


def test_no_brand_leak():
    for p in (TOPO, STATE_TS, DIV_TS):
        assert "lumen" not in _src(p).lower()
