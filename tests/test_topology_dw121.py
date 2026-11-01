"""BUG-DW-121: hops-shown copy number agreement and 0-case suffix.

(a) 0 of 1  -> 'The 1 hop is not drawn on this map' + ', it goes to a customer, hut, or other-region site'
(b) 0 of N  -> 'None of the N hops are drawn on this map' + ', they go to customer, hut, or other-region sites'
(c) drawn>0 -> unchanged (', others go to ...')
Tooltip, showHopsShown and countHopsShown are unchanged.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import glob
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

OTHERS = ", others go to customer, hut, or other-region sites"
NONE_ONE = ", it goes to a customer, hut, or other-region site"
NONE_MANY = ", they go to customer, hut, or other-region sites"
TOOLTIP = ("This map draws only tier 1 and tier 2 sites in the selected region. Hops to customer "
           "premises, hut sites, or other regions are counted but not drawn.")


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _case(drawn, total, working, protect):
    return _node(f"""
const hs = {{drawn: {drawn}, total: {total}}};
out = {{
  line: m.hopsShownLine(hs),
  spoken: m.hopsShownSpoken(hs),
  live: m.traceLiveSummary('SVC-00042', 'Partially diverse', {working}, {protect}, hs),
  status: m.traceStatusText({{mode: 'live', serviceId: 'SVC-00042', busy: false, retryFeedback: null,
    diversityLabel: 'Partially diverse', workingHops: {working}, protectHops: {protect}, hopsShown: hs}}),
}};
""")


def _assert_once_one_period(text, line):
    assert text.count(line) == 1
    assert text.endswith(".") and not text.endswith("..")
    assert " 1 hops" not in text


@needs_node
def test_suffix_constants_exported():
    out = _node("out = [m.HOPS_SHOWN_SPOKEN_SUFFIX, m.HOPS_SHOWN_SPOKEN_SUFFIX_NONE_ONE, "
                "m.HOPS_SHOWN_SPOKEN_SUFFIX_NONE_MANY, m.HOPS_SHOWN_TOOLTIP];")
    assert out == [OTHERS, NONE_ONE, NONE_MANY, TOOLTIP]


@needs_node
def test_zero_of_one_singular():
    out = _case(0, 1, 1, 0)
    line = "The 1 hop is not drawn on this map"
    assert out["line"] == line
    assert out["spoken"] == line + NONE_ONE
    assert out["live"] == ("SVC-00042 traced: Partially diverse, 1 working hop, no protect path. "
                           + line + NONE_ONE + ".")
    assert out["status"] == out["live"]
    for t in out.values():
        assert "others" not in t
        assert "1 hops" not in t
    _assert_once_one_period(out["live"], line)


@needs_node
def test_zero_of_six_plural_no_others():
    out = _case(0, 6, 4, 2)
    line = "None of the 6 hops are drawn on this map"
    assert out["line"] == line
    assert out["spoken"] == line + NONE_MANY
    assert out["live"] == ("SVC-00042 traced: Partially diverse, 4 working hops, 2 protect hops. "
                           + line + NONE_MANY + ".")
    assert "others" not in out["spoken"] and "others" not in out["live"]
    _assert_once_one_period(out["live"], line)


@needs_node
def test_four_of_six_unchanged():
    out = _case(4, 6, 4, 2)
    line = "4 of 6 hops shown on this map"
    assert out["line"] == line
    assert out["spoken"] == line + OTHERS
    assert out["live"].endswith(line + OTHERS + ".")
    _assert_once_one_period(out["live"], line)


@needs_node
def test_zero_of_1234_formatted():
    out = _case(0, 1234, 1000, 234)
    line = "None of the 1,234 hops are drawn on this map"
    assert out["line"] == line
    assert out["spoken"] == line + NONE_MANY
    assert "1234" not in out["live"]
    _assert_once_one_period(out["live"], line)


@needs_node
def test_show_and_count_unchanged():
    out = _node("""
out = [m.showHopsShown({drawn: 0, total: 1}), m.showHopsShown({drawn: 1, total: 1}),
       m.hopsShownLine({drawn: 1, total: 1}), m.hopsShownSpoken({drawn: 0, total: 0}),
       m.countHopsShown([{conduit_id: 'A'}], [{conduit_id: 'B', site_a_id: 'x', site_z_id: 'y'}], null)];
""")
    assert out == [True, False, None, None, {"drawn": 0, "total": 1}]


def test_no_brand_leak_in_ui():
    hits = []
    for p in glob.glob(os.path.join(UI, "**", "*.*"), recursive=True):
        if os.path.isfile(p) and p.endswith((".ts", ".tsx", ".css")):
            with open(p, encoding="utf-8") as f:
                if re.search("lumen", f.read(), re.I):
                    hits.append(p)
    assert hits == []
