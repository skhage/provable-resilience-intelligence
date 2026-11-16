"""BUG-DW-189: Home Avg Resilience Score band shared with the service table gauge (binding, @designer S138).

Before: scorecard-header.tsx scoreClass() used 80/60/40 and only set the border colour (WCAG 1.4.1),
while service-table.tsx gaugeClass() used 85/70/55/40. Now both use scoreBand() from lib/score-band.ts,
and under the v4 flag the Avg card shows the band label as a .kpi-caption and in its aria-label.
Static source checks plus Node known-answer evaluation (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
TABLE = os.path.join(UI, "components", "dashboard", "service-table.tsx")
BAND_TS = os.path.join(UI, "lib", "score-band.ts")
BANNED = "lu" + "men"


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
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


# (a) shared helper, local copies removed
def test_score_band_lib_exists():
    assert os.path.isfile(BAND_TS)
    ts = _read(BAND_TS)
    assert "export function scoreBand(score: number): ScoreBand" in ts


def test_header_score_class_removed():
    assert "scoreClass" not in _read(HEADER)


def test_table_gauge_class_removed():
    assert "gaugeClass" not in _read(TABLE)


@pytest.mark.parametrize("path", [HEADER, TABLE])
def test_both_files_import_shared_score_band(path):
    src = _read(path)
    m = re.search(r'import \{([^}]*)\} from "@/lib/score-band";', src)
    assert m, "missing import from @/lib/score-band"
    assert "scoreBand" in [s.strip() for s in m.group(1).split(",")]


def test_no_local_thresholds_in_components():
    for p in (HEADER, TABLE):
        assert not re.search(r"score >= \d+", _read(p)), p


# (b) known answers, evaluated with Node on the real TS
@pytest.mark.parametrize("score,label,key", [
    (100, "Excellent", "excellent"),
    (85, "Excellent", "excellent"),
    (84.99, "Good", "good"),
    (75, "Good", "good"),
    (70, "Good", "good"),
    (61.55, "Fair", "fair"),
    (55, "Fair", "fair"),
    (40, "Poor", "poor"),
    (39.9, "Failing", "failing"),
    (0, "Failing", "failing"),
])
def test_score_band_known_answers(score, label, key):
    assert _node_ts(BAND_TS, "M.scoreBand(" + str(score) + ")") == {"key": key, "label": label}


def test_score_band_non_finite_is_failing():
    assert _node_ts(BAND_TS, "M.scoreBand(NaN).label") == "Failing"


@pytest.mark.parametrize("score,cls", [
    (90, "success"), (75, "success"), (61.55, "warning"), (45, "high"), (10, "critical"),
])
def test_border_class_mapped_from_band(score, cls):
    assert _node_ts(BAND_TS, "M.scoreBandKpiClass(" + str(score) + ")") == cls


def test_border_classes_are_existing_tokens():
    css = _read(os.path.join(UI, "styles", "lakelink-theme.css"))
    for cls in ("success", "warning", "high", "critical"):
        assert ".kpi-card." + cls + " {" in css


# (c) visible caption + aria-label under the v4 flag; v3 aria-label unchanged
def test_header_border_uses_shared_band():
    assert "kpi-card ${scoreBandKpiClass(summary.avg_resilience_score)}" in _read(HEADER)


def test_avg_card_caption_flag_gated():
    src = _read(HEADER)
    assert '{v4Kpis && <div className="kpi-caption">{avgBand.label}</div>}' in src
    # caption is inside the Avg card: after its value and before the Critical card
    i_val = src.index('<div className="kpi-value score">{avgScore}</div>')
    i_cap = src.index('{avgBand.label}</div>}')
    i_crit = src.index('aria-label={`Critical Risk: ${critical}`}')
    assert i_val < i_cap < i_crit


def test_avg_card_aria_label_contains_band_under_flag():
    src = _read(HEADER)
    assert ("aria-label={v4Kpis ? `Avg Resilience Score: ${avgScore}, ${avgBand.label}` "
            ": `Avg Resilience Score: ${avgScore}`}") in src


def test_kpi_caption_is_solid_iron():
    css = _read(os.path.join(UI, "styles", "lakelink-theme.css"))
    m = re.search(r"\n\.kpi-caption \{([^}]*)\}", css)
    assert m and "color: #4D4D4D;" in m.group(1)


# (d) branding
def test_no_banned_brand_string():
    for p in (HEADER, TABLE, BAND_TS, os.path.abspath(__file__)):
        assert BANNED not in _read(p).lower(), p
