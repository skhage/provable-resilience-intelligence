"""BUG-DW-099: /topology diversity badge copy map, basis caption, shared-conduit stat,
and Service Table snapshot-grade naming.

Pure helpers in ui/lib/diversity-copy.ts are evaluated with Node (>= 22.18 strips TS
types). JSX wiring is checked statically (no npm on serverless).
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
_LIB = os.path.join(UI, "lib", "diversity-copy.ts")
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


# --- label maps ------------------------------------------------------------------

@needs_node
@pytest.mark.parametrize("status,full,short", [
    ("fully_diverse", "Fully diverse", "Diverse"),
    ("partially_diverse", "Partially diverse", "Partial"),
    ("single_path", "Single path", "Single"),
    ("unknown", "No path data", "No data"),
    (None, "No path data", "No data"),
    ("bogus", "No path data", "No data"),
    ("toString", "No path data", "No data"),  # prototype key must not leak
])
def test_labels(status, full, short):
    s = json.dumps(status)
    out = _node(f"out = [m.diversityLabel({s}), m.diversityShortLabel({s})];")
    assert out == [full, short]


@needs_node
def test_order_covers_all_statuses():
    out = _node("out = [m.DIVERSITY_STATUS_ORDER, Object.keys(m.DIVERSITY_LABELS).sort(),"
                " Object.keys(m.DIVERSITY_SHORT_LABELS).sort()];")
    assert sorted(out[0]) == out[1] == out[2]
    assert out[0] == ["fully_diverse", "partially_diverse", "single_path", "unknown"]


@needs_node
def test_caption_copy():
    assert _node("out = m.DIVERSITY_BASIS_CAPTION;") == "From traced working and protect hops."


@needs_node
@pytest.mark.parametrize("n,expected", [
    (0, ""), (None, ""), (-1, ""),
    (1, " \u00b7 1 shared conduit"),
    (3, " \u00b7 3 shared conduits"),
    (1309, " \u00b7 1,309 shared conduits"),
])
def test_shared_conduit_stat(n, expected):
    assert _node(f"out = m.sharedConduitStat({json.dumps(n)});") == expected


@needs_node
def test_shared_conduit_stat_uses_formatter():
    assert _node("out = m.sharedConduitStat(5, (n) => `<${n}>`);") == " \u00b7 <5> shared conduits"


@needs_node
@pytest.mark.parametrize("grade,expected", [
    ("A", "Path diversity grade (scored snapshot): A"),
    (None, "Path diversity grade (scored snapshot): not rated"),
])
def test_snapshot_grade_label(grade, expected):
    assert _node(f"out = m.snapshotGradeLabel({json.dumps(grade)});") == expected


# --- static wiring ---------------------------------------------------------------

def _banner_src():
    src = _read("routes", "topology.tsx")
    start = src.index("function PathTraceBanner(")
    return src[start:src.index("\nfunction ", start + 10)]


def test_banner_uses_map_not_raw_status():
    b = _banner_src()
    assert "diversityLabel(diversity?.diversity_status)" in b
    assert "diversity_status.replace(" not in b


def test_caption_only_in_live_badge_branch():
    b = _banner_src()
    non_live = b[:b.index("bbUnverified = ")]
    live = b[b.index("bbUnverified = "):]
    assert "DIVERSITY_BASIS_CAPTION" not in non_live
    assert live.count("DIVERSITY_BASIS_CAPTION") == 1
    # caption sits right after the badge, inside the stack wrapper
    stack = live[live.index('className="diversity-badge-stack"'):]
    assert stack.index('className="diversity-badge"') < stack.index("diversity-basis-caption")


def test_banner_never_shows_snapshot_score():
    assert "path_diversity_score" not in _banner_src()


def test_shared_conduit_stat_in_stats_with_formatcount():
    b = _banner_src()
    stats = b[b.index('className="path-trace-stats"'):]
    stats = stats[:stats.index("</span>")]
    assert "sharedConduitStat(diversity.shared_conduit_count, formatCount)" in stats


def test_mobile_and_legend_use_shared_map():
    src = _read("routes", "topology.tsx")
    assert "diversityShortLabel(status)" in src
    assert "DIVERSITY_STATUS_ORDER.map" in src
    assert 'label: "Unknown"' not in src
    assert ': "Unknown";' not in src
    assert "Fully Diverse" not in src


def test_interface_fields():
    src = _read("routes", "topology.tsx")
    iface = src[src.index("interface ServiceDiversity {"):]
    iface = iface[:iface.index("}")]
    for f in ("shared_conduit_count?:", "sold_as_diverse?:", "path_diversity_score?:"):
        assert f in iface


def test_service_table_pill_names_basis():
    src = _read("components", "dashboard", "service-table.tsx")
    assert "aria-label={snapshotGradeLabel(s.path_diversity_rating)}" in src
    assert "title={snapshotGradeLabel(s.path_diversity_rating)}" in src
    assert "Path diversity: grade" not in src


def test_css_sentence_case_and_iron_caption():
    css = _read("styles", "lakelink-theme.css")
    badge = css[css.index(".diversity-badge {"):]
    badge = badge[:badge.index("}")]
    assert "capitalize" not in badge
    cap = css[css.index(".diversity-basis-caption {"):]
    cap = cap[:cap.index("}")]
    assert "font-size: 12px" in cap and "var(--lf-iron)" in cap


def test_no_old_brand_token():
    for parts in [("lib", "diversity-copy.ts"), ("routes", "topology.tsx"),
                  ("components", "dashboard", "service-table.tsx")]:
        assert not re.search("lumen", _read(*parts), re.I), parts
