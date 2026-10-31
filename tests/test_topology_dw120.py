"""BUG-DW-120: /topology hops-shown copy must not attribute every undrawn hop to tier 3.

Live check (@designer S65): undrawn hops are 39% tier 3, 37% out of region, 24% customer
premise with no tier. Copy now names all three causes; 0-of-N reads 'None of the N hops'.
countHopsShown (the drawn definition) is unchanged.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
APP = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard")
UI = os.path.join(APP, "ui")
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

TOOLTIP = ("This map draws only tier 1 and tier 2 sites in the selected region. Hops to customer "
           "premises, hut sites, or other regions are counted but not drawn.")
SUFFIX = ", others go to customer, hut, or other-region sites"


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# SVC-00001 on the Central map (designer live check): 6 hops, none drawn.
# hop 1 and 6 end at tier 3 sites, hops 2/3/5 cross into East/West, hop 4 ends at a
# customer premise with no tier. None of those conduits/sites are in the Central render.
_SVC1_CENTRAL = """
const hops = [
  {conduit_id: 'CDT-T3-A'}, {conduit_id: 'CDT-EAST-1'}, {conduit_id: 'CDT-WEST-1'},
  {conduit_id: 'CDT-MT-1039'}, {conduit_id: 'CDT-EAST-2'}, {conduit_id: 'CDT-T3-B'},
];
const conduits = [
  {conduit_id: 'CDT-C-1', site_a_id: 'CO-1', site_z_id: 'CO-2'},
  {conduit_id: 'CDT-C-2', site_a_id: 'CO-2', site_z_id: 'CO-3'},
];
const sites = new Set(['CO-1', 'CO-2', 'CO-3']);
const hs = m.countHopsShown(hops, conduits, sites);
"""


@needs_node
def test_tooltip_names_all_three_causes():
    tip = _node("out = m.HOPS_SHOWN_TOOLTIP;")
    assert tip == TOOLTIP
    for cause in ("customer premises", "hut sites", "other regions"):
        assert cause in tip


@needs_node
def test_spoken_suffix_exported_and_used():
    out = _node("out = [m.HOPS_SHOWN_SPOKEN_SUFFIX, m.hopsShownSpoken({drawn: 2, total: 5})];")
    assert out[0] == SUFFIX
    assert out[1] == "2 of 5 hops shown on this map" + SUFFIX


@needs_node
def test_svc00001_central_zero_of_six():
    out = _node(_SVC1_CENTRAL + """
out = {hs, show: m.showHopsShown(hs), line: m.hopsShownLine(hs), spoken: m.hopsShownSpoken(hs)};
""")
    assert out["hs"] == {"drawn": 0, "total": 6}
    assert out["show"] is True          # the note (and its Info tooltip) still renders
    assert out["line"] == "None of the 6 hops are drawn on this map"
    assert out["spoken"] == "None of the 6 hops are drawn on this map" + SUFFIX


@needs_node
def test_zero_of_n_live_summary_has_sentence_once():
    out = _node(_SVC1_CENTRAL + """
out = m.traceStatusText({mode: 'live', serviceId: 'SVC-00001', busy: false, retryFeedback: null,
  diversityLabel: 'Partially diverse', workingHops: 4, protectHops: 2, hopsShown: hs});
""")
    assert out == ("SVC-00001 traced: Partially diverse, 4 working hops, 2 protect hops. "
                   "None of the 6 hops are drawn on this map" + SUFFIX + ".")
    assert out.count("hops are drawn on this map") == 1
    assert "0 of 6" not in out


@needs_node
def test_grouping_in_zero_of_n():
    assert _node("out = m.hopsShownLine({drawn: 0, total: 54572});") == \
        "None of the 54,572 hops are drawn on this map"


@needs_node
def test_no_copy_attributes_undrawn_hops_to_tier_3_only():
    out = _node("""
out = [m.HOPS_SHOWN_TOOLTIP, m.hopsShownSpoken({drawn: 4, total: 6}),
       m.hopsShownSpoken({drawn: 0, total: 6})];
""")
    for s in out:
        assert "tier 3" not in s
        assert "pass through" not in s


@needs_node
def test_count_hops_shown_definition_unchanged():
    # Item 4: drawn = conduit rendered AND both endpoints placed.
    out = _node("""
const hops = [{conduit_id: 'A'}, {conduit_id: 'B'}, {conduit_id: null}, {conduit_id: 'Z'}];
const conduits = [{conduit_id: 'A', site_a_id: 's1', site_z_id: 's2'},
                  {conduit_id: 'B', site_a_id: 's2', site_z_id: 's9'}];
out = [m.countHopsShown(hops, conduits, new Set(['s1', 's2'])), m.countHopsShown(hops, conduits, null)];
""")
    assert out == [{"drawn": 1, "total": 4}, {"drawn": 2, "total": 4}]


def test_no_retired_brand_name_in_ui():
    hits = []
    for dp, _, fs in os.walk(UI):
        for f in fs:
            if f.endswith((".ts", ".tsx", ".css")):
                p = os.path.join(dp, f)
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    if "lumen" in fh.read().lower():
                        hits.append(p)
    assert hits == []
