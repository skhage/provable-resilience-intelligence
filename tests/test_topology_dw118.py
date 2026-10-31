"""BUG-DW-118: /topology trace banner counts hops the map never draws (tier 3 endpoints).

Adds "{drawn} of {total} hops shown on this map" + Info tooltip to the desktop banner,
the mobile diversity summary and the persistent live trace announcement. Omitted when
drawn == total.

Pure helpers are evaluated with Node (TS type stripping); JSX wiring is checked statically.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
APP = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard")
UI = os.path.join(APP, "ui")
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

# BUG-DW-120 superseded the DW-118 copy (undrawn hops are not only tier 3).
TOOLTIP = ("This map draws only tier 1 and tier 2 sites in the selected region. Hops to customer "
           "premises, hut sites, or other regions are counted but not drawn.")
SUFFIX = ", others go to customer, hut, or other-region sites"


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


# Fixture: 6 hops, 4 of them on conduits the map renders (C1..C4); C5 has a tier 3
# endpoint (not in the region list) and one hop has no conduit at all.
_FIXTURE = """
const hops = [
  {conduit_id: 'C1', path_type: 'working'}, {conduit_id: 'C2', path_type: 'working'},
  {conduit_id: 'C3', path_type: 'working'}, {conduit_id: 'C5', path_type: 'working'},
  {conduit_id: 'C4', path_type: 'protect'}, {conduit_id: null, path_type: 'protect'},
];
const conduits = [
  {conduit_id: 'C1', site_a_id: 'A', site_z_id: 'B'},
  {conduit_id: 'C2', site_a_id: 'B', site_z_id: 'C'},
  {conduit_id: 'C3', site_a_id: 'C', site_z_id: 'D'},
  {conduit_id: 'C4', site_a_id: 'A', site_z_id: 'D'},
  {conduit_id: 'C9', site_a_id: 'A', site_z_id: 'C'},
];
const sites = new Set(['A', 'B', 'C', 'D']);
"""


# --- known-answer helpers ----------------------------------------------------

@needs_node
def test_known_answer_4_of_6():
    out = _node(_FIXTURE + """
const hs = m.countHopsShown(hops, conduits, sites);
out = {hs, line: m.hopsShownLine(hs), spoken: m.hopsShownSpoken(hs), show: m.showHopsShown(hs)};
""")
    assert out["hs"] == {"drawn": 4, "total": 6}
    assert out["line"] == "4 of 6 hops shown on this map"
    assert out["spoken"] == "4 of 6 hops shown on this map" + SUFFIX
    assert out["show"] is True


@needs_node
def test_drawn_equals_total_renders_no_line():
    out = _node(_FIXTURE + """
const all = hops.filter((h) => h.conduit_id && h.conduit_id !== 'C5');
const hs = m.countHopsShown(all, conduits, sites);
out = {hs, line: m.hopsShownLine(hs), spoken: m.hopsShownSpoken(hs), show: m.showHopsShown(hs),
       live: m.traceLiveSummary('SVC-1', 'Fully diverse', 3, 1, hs)};
""")
    assert out["hs"] == {"drawn": 4, "total": 4}
    assert out["line"] is None and out["spoken"] is None and out["show"] is False
    assert "shown on this map" not in out["live"]


@needs_node
def test_null_and_zero_total_render_no_line():
    out = _node("""
out = [m.hopsShownLine(null), m.hopsShownLine(undefined), m.hopsShownLine({drawn: 0, total: 0}),
       m.showHopsShown(null), m.showHopsShown({drawn: 0, total: 0})];
""")
    assert out == [None, None, None, False, False]


@needs_node
def test_zero_of_n_still_has_spoken_reason():
    # BUG-DW-120 item 3: 0-of-N uses 'None of the N hops' wording; spoken form carries the reason.
    out = _node("out = [m.hopsShownLine({drawn: 0, total: 6}), m.hopsShownSpoken({drawn: 0, total: 6})];")
    assert out[0] == "None of the 6 hops are drawn on this map"
    assert out[1] == "None of the 6 hops are drawn on this map" + SUFFIX


@needs_node
def test_conduit_without_placed_endpoint_is_not_drawn():
    # SiteGraph skips an edge when either endpoint has no position.
    out = _node(_FIXTURE + """
out = [m.countHopsShown(hops, conduits, new Set(['A', 'B', 'C'])),
       m.countHopsShown(hops, conduits, null)];
""")
    assert out[0] == {"drawn": 2, "total": 6}   # C3 (C-D) and C4 (A-D) lose site D
    assert out[1] == {"drawn": 4, "total": 6}   # no site filter: conduit list only


@needs_node
def test_counts_use_en_us_grouping_like_formatcount():
    out = _node("out = m.hopsShownLine({drawn: 33518, total: 54572});")
    assert out == "33,518 of 54,572 hops shown on this map"


@needs_node
def test_tooltip_copy_verbatim():
    assert _node("out = m.HOPS_SHOWN_TOOLTIP;") == TOOLTIP


# --- live announcement (item 4) ----------------------------------------------

@needs_node
def test_live_summary_includes_sentence_once():
    out = _node(_FIXTURE + """
const hs = m.countHopsShown(hops, conduits, sites);
out = m.traceStatusText({mode: 'live', serviceId: 'SVC-00001', busy: false, retryFeedback: null,
  diversityLabel: 'Partially diverse', workingHops: 4, protectHops: 2, hopsShown: hs});
""")
    assert out == ("SVC-00001 traced: Partially diverse, 4 working hops, 2 protect hops. "
                   "4 of 6 hops shown on this map" + SUFFIX + ".")
    assert out.count("shown on this map") == 1


@needs_node
def test_live_summary_unchanged_without_hops_shown():
    out = _node("""
const a = m.traceLiveSummary('SVC-1', 'Fully diverse', 3, 1);
const b = m.traceStatusText({mode: 'live', serviceId: 'SVC-1', busy: false, retryFeedback: null,
  diversityLabel: 'Fully diverse', workingHops: 3, protectHops: 1});
out = [a, b];
""")
    assert out == ["SVC-1 traced: Fully diverse, 3 working hops, 1 protect hop."] * 2


@needs_node
def test_non_live_modes_never_mention_hops_shown():
    out = _node("""
const hs = {drawn: 1, total: 6};
out = ['unavailable', 'not_found', 'auth_expired', 'pending'].map((mode) => m.traceStatusText({
  mode, serviceId: 'SVC-1', busy: false, retryFeedback: null, diversityLabel: 'x',
  workingHops: 3, protectHops: 3, hopsShown: hs}));
""")
    assert all("shown on this map" not in s for s in out)


# --- JSX wiring (static) -----------------------------------------------------

def _fn_body(src, name):
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j != -1 else len(src)]


def test_note_always_renders_info_tooltip_with_spec_copy():
    body = _fn_body(_read("routes", "topology.tsx"), "HopsShownNote")
    assert "<InfoTooltip label={spoken} text={HOPS_SHOWN_TOOLTIP} />" in body
    assert "{line}" in body and 'className="path-trace-hops-shown"' in body


def test_banner_and_mobile_render_note_only_when_hops_hidden():
    src = _read("routes", "topology.tsx")
    guard = "{showHopsShown(hopsShown) && <HopsShownNote hopsShown={hopsShown} />}"
    assert guard in _fn_body(src, "PathTraceBanner")
    assert guard in _fn_body(src, "MobileTreeView")
    assert src.count("<HopsShownNote ") == 2


def test_page_passes_one_hops_shown_to_banner_mobile_and_status():
    page = _fn_body(_read("routes", "topology.tsx"), "TopologyPage")
    assert "countHopsShown(pathHops, visibleConduits, siteIds)" in page
    assert "if (!selectedRegion || loading || pathHops.length === 0) return null;" in page
    assert page.count("hopsShown={hopsShown}") == 2      # PathTraceBanner + MobileTreeView
    status = page[page.index("traceStatusText({"):]
    assert "hopsShown," in status[: status.index("})}")]


def test_css_iron_no_new_colour():
    css = _read("styles", "lakelink-theme.css")
    m = re.search(r"(?m)^\.path-trace-hops-shown \{([^}]*)\}", css)
    assert m, "missing .path-trace-hops-shown rule"
    rule = m.group(1)
    assert "color: var(--lf-iron, #4D4D4D);" in rule
    assert set(re.findall(r"#[0-9A-Fa-f]{3,6}\b", rule)) == {"#4D4D4D"}


def test_no_retired_brand_name_in_ui_or_backend():
    hits = []
    for base in (UI, os.path.join(APP, "backend")):
        for dp, _, fs in os.walk(base):
            for f in fs:
                if f.endswith((".ts", ".tsx", ".css", ".py")):
                    p = os.path.join(dp, f)
                    with open(p, encoding="utf-8", errors="ignore") as fh:
                        if "lumen" in fh.read().lower():
                            hits.append(p)
    assert hits == []
