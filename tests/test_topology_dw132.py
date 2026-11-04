"""BUG-DW-132: SiteGraph CLLI labels must never overlap after DW-131 counter-scaling.

Known answers (9-char CLLI, 10 px floor, SiteGraph 1200x600 viewBox, wrap height
max(500, width/2), i.e. the designer's scales 0.613 / 0.8 / 1.0):
  736 px  -> scale 0.6133, font 16.30 VB, width 88.0 VB  -> hidden at spacing 60 / 61.1
  960 px  -> scale 0.8,    font 12.5 VB,  width 67.5 VB  -> hidden at spacing 60 / 61.1
  1200 px -> scale 1.0,    font 10 VB,    width 54.0 VB  -> shown  (54 <= 56 and <= 57.1)
"""
import json
import os
import re
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
LIB_DIR = os.path.join(UI, "lib")
TOPOLOGY = os.path.join(UI, "routes", "topology.tsx")


def _node_ts(code: str):
    r = subprocess.run(
        ["node", "--experimental-strip-types", "-e", code],
        capture_output=True, text=True, timeout=20, cwd=LIB_DIR,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


def _src():
    with open(TOPOLOGY, encoding="utf-8") as f:
        return f.read()


def _h(width_px: int) -> float:
    return max(500, width_px / 2)


def _scale(width_px: int) -> float:
    return min(width_px / 1200, _h(width_px) / 600)


def _font(width_px: int) -> float:
    return max(10, 10 / _scale(width_px))


@pytest.mark.parametrize("width,spacing,expected", [
    (736, 60, False), (960, 60, False), (1200, 60, True),
    (736, 1100 / 18, False), (960, 1100 / 18, False), (1200, 1100 / 18, True),
])
def test_show_clli_label_known_answers(width, spacing, expected):
    out = _node_ts(textwrap.dedent(f"""\
        import {{ showClliLabel, clliLabelWidth, scaledFontSize, svgScale }} from './svg-label-scale.ts';
        const fs = scaledFontSize(10, svgScale({width}, {_h(width)}));
        console.log(JSON.stringify({{ show: showClliLabel(9, fs, {spacing}), w: clliLabelWidth(9, fs), fs }}));
    """))
    assert out["show"] is expected
    assert out["fs"] == pytest.approx(_font(width))
    assert out["w"] == pytest.approx(9 * 0.6 * _font(width))
    assert out["fs"] * _scale(width) >= 10 - 1e-9  # 10 px floor kept


def _row_ids(width, n, priority):
    return _node_ts(textwrap.dedent(f"""\
        import {{ clliLabelIds, clliLabelWidth, scaledFontSize, svgScale, CLLI_LABEL_GAP }} from './svg-label-scale.ts';
        import {{ rowSpacing }} from './site-graph-layout.ts';
        const n = {n};
        const sp = rowSpacing(n, 'tier_1');
        const row = [];
        for (let i = 0; i < n; i++) row.push({{ id: 'S' + i, x: 50 + i * sp + sp / 2, len: 9 }});
        const fs = scaledFontSize(10, svgScale({width}, {_h(width)}));
        const ids = [...clliLabelIds(row, fs, sp, {json.dumps(priority)})];
        const shown = row.filter((s) => ids.includes(s.id));
        let overlaps = 0;
        for (let a = 0; a < shown.length; a++) for (let b = a + 1; b < shown.length; b++) {{
          const min = clliLabelWidth(9, fs) + CLLI_LABEL_GAP;
          if (Math.abs(shown[a].x - shown[b].x) < min) overlaps++;
        }}
        console.log(JSON.stringify({{ ids: shown.map((s) => s.id), overlaps, sp }}));
    """))


@pytest.mark.parametrize("width", [736, 960, 1200])
@pytest.mark.parametrize("priority", [[], ["S3", "S4", "S5"], ["S0", "S1", "S2", "S3", "S17"]])
def test_no_rendered_pair_overlaps(width, priority):
    out = _row_ids(width, 18, priority)
    assert out["overlaps"] == 0
    assert out["sp"] == pytest.approx(1100 / 18)


def test_wide_canvas_shows_every_label():
    assert len(_row_ids(1200, 18, [])["ids"]) == 18


def test_letterboxed_1200x500_hides_labels():
    # 1200x500 wrap -> scale 0.833, font 12 VB, width 64.8 > 57.1: labels would overlap
    out = _node_ts(
        "import { showClliLabel, scaledFontSize, svgScale } from './svg-label-scale.ts';\n"
        "console.log(JSON.stringify(showClliLabel(9, scaledFontSize(10, svgScale(1200, 500)), 1100 / 18)));"
    )
    assert out is False


@pytest.mark.parametrize("width", [736, 960])
def test_narrow_canvas_only_priority_labels(width):
    assert _row_ids(width, 18, [])["ids"] == []
    # selected first: always drawn; adjacent on-path S4 would overlap S3 so is skipped; S5 fits
    out = _row_ids(width, 18, ["S3", "S4", "S5"])
    assert "S3" in out["ids"] and "S4" not in out["ids"]
    assert out["ids"] == ["S3", "S5"]


def test_selected_wins_over_neighbour():
    out = _row_ids(736, 18, ["S4", "S3"])
    assert "S4" in out["ids"] and "S3" not in out["ids"]


def test_ignores_unknown_and_null_priority_ids():
    out = _row_ids(736, 18, [None, "ZZ", "S2", "S2"])
    assert out["ids"] == ["S2"]


def test_topology_wires_clli_helper():
    s = _src()
    assert "clliLabelIds," in s and "rowSpacing," in s
    assert 'rowSpacing(row.length, "tier_1")' in s
    assert "[selectedSiteId, focusedSiteId, ...onPath]" in s
    assert "const clliFontSize = scaledFontSize(10, canvasScale);" in s  # floor kept
    assert "isT1 && clliShown.has(s.site_id) && (" in s
    assert "onFocus={() => setFocusedSiteId(s.site_id)}" in s


def test_clli_kept_in_title_and_name():
    s = _src()
    i = s.index('className={`topo-site-node')
    head = s[s.rfind("return (", 0, i):i]
    assert '<g key={s.site_id} role="none">' in head
    assert "<title>{`${s.site_name} (${clliText})`}</title>" in head
    assert "${clliSpoken})" in s
    # the focusable button itself still carries no child <title> (DW-100 / DW-115 rule)
    btn = s[i:s.index("</g>", i)]
    assert "<title" not in btn


def test_no_brand_regression():
    lib = open(os.path.join(LIB_DIR, "svg-label-scale.ts"), encoding="utf-8").read()
    assert not re.search("lumen", lib + _src(), re.I)
