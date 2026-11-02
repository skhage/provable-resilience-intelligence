"""BUG-DW-108: /topology PathTraceBanner polish.

(1) hop pluralization shared with the live summary (hopCount)
(2) basis caption is not inside any live region, but stays in the accessibility tree
(3) formatCount on both shared-SRLG branches
(4) mobile diversity badge: no aria-label on a generic span; sr-only 'Diversity: ' prefix
(5) .data-table th .th-qualifier font-size 12px (house floor), text-transform none
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
TOPO = os.path.join(UI, "routes", "topology.tsx")
STATE_TS = os.path.join(UI, "lib", "topology-data-state.ts")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")


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
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _banner_live_block(src):
    """Live-mode PathTraceBanner return: from the banner div to its actions div."""
    start = src.index('<div className="path-trace-banner" ref={bannerRef} tabIndex={-1}>\n      <div className="path-trace-info">')
    end = src.index('<div className="path-trace-actions">\n        <Link', start)
    return src[start:end]


def _stats_block(src):
    m = re.search(r'<span className="path-trace-stats">(.*?)\n\s*</span>\n', src, re.S)
    assert m, "path-trace-stats span not found"
    return m.group(1)


# ---------- (1) pluralization ----------

def test_hopcount_known_answers():
    out = _node_ts(STATE_TS, "[M.hopCount(1,'working'), M.hopCount(0,'working'), "
                             "M.hopCount(3,'protect'), M.hopCount(1,'protect'), M.hopCount(1200,'working')]")
    assert out == ["1 working hop", "0 working hops", "3 protect hops", "1 protect hop", "1,200 working hops"]


def test_live_summary_still_matches_hopcount():
    out = _node_ts(STATE_TS, "M.traceLiveSummary('SVC-1','Fully diverse',1,1)")
    assert out == "SVC-1 traced: Fully diverse, 1 working hop, 1 protect hop."


def test_banner_uses_hopcount_not_hardcoded_plural():
    src = _read(TOPO)
    block = _stats_block(src)
    assert '{hopCount(workingHops.length, "working")}' in block
    assert '${hopCount(protectHops.length, "protect")}' in block
    assert "working hops" not in block and "protect hops" not in block
    assert re.search(r"^\s+hopCount,$", src, re.M), "hopCount must be imported from topology-data-state"


# ---------- (2) caption outside live regions, still in a11y tree ----------

def test_banner_has_no_live_region_and_caption_is_exposed():
    block = _banner_live_block(_read(TOPO))
    assert 'role="status"' not in block and "aria-live" not in block
    cap = '<span className="diversity-basis-caption">{DIVERSITY_BASIS_CAPTION}</span>'
    assert cap in block
    # caption must not be hidden from AT
    line = [l for l in block.splitlines() if "diversity-basis-caption" in l][0]
    assert "aria-hidden" not in line and "sr-only" not in line


def test_live_summary_excludes_caption():
    out = _node_ts(STATE_TS, "M.traceLiveSummary('SVC-1','Partially diverse',4,2)")
    assert "From traced" not in out


# ---------- (3) formatCount on both SRLG branches ----------

def test_shared_srlg_count_formatted_in_both_branches():
    block = _stats_block(_read(TOPO))
    assert block.count("formatCount(diversity.shared_srlg_count)") == 2
    assert "${diversity.shared_srlg_count}" not in block


# ---------- (4) mobile badge ----------

def test_mobile_badge_no_aria_label_on_generic_span():
    src = _read(TOPO)
    i = src.index('className="mobile-tree-badge"')
    j = src.index("</span>\n    );", i)
    badge = re.sub(r"\{/\*.*?\*/\}", "", src[i:j], flags=re.S)  # ignore JSX comments
    assert "aria-label" not in badge
    assert '<span className="sr-only">Diversity: </span>' in badge
    assert badge.index("sr-only") < badge.index("{label}")


# ---------- (5) CSS ----------

def _base_rule(css, selector):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return dict((k.strip(), v.strip()) for k, v in
                (d.split(":", 1) for d in m.group(1).split(";") if ":" in d))


def test_th_qualifier_font_floor():
    css = _read(CSS)
    q = _base_rule(css, ".data-table th .th-qualifier")
    th = _base_rule(css, ".data-table th")
    assert q["font-size"] == "12px"
    assert q["font-size"] == th["font-size"]
    assert q["text-transform"] == "none"


def test_no_brand_regressions():
    for p in (TOPO, STATE_TS, CSS):
        assert "lumen" not in _read(p).lower(), p
