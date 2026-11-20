"""P303-APP-ESLINT-5-ERRORS: `npm run lint` (eslint --max-warnings 0) must pass.

Static guards for the 5 errors + 2 warnings cleared in P303, plus an optional live
eslint run when node_modules is present (CI on Node 22 / local /tmp build copy).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "resilience-scorecard"
UI = APP / "src" / "resilience_scorecard" / "ui"
TOPO = UI / "routes" / "topology.tsx"
XWALK = UI / "components" / "hazards" / "hazard-crosswalk-table.tsx"
BB = UI / "lib" / "bb-srlg-disclosure.ts"

# no-irregular-whitespace (default options): flags these code points outside strings,
# including in comments. Built with chr() so this test file contains none of them.
IRREGULAR = [chr(c) for c in (0x000B, 0x000C, 0x00A0, 0x0085, 0xFEFF, 0x1680, 0x180E,
                              0x2028, 0x2029, 0x202F, 0x205F, 0x3000)] + \
            [chr(c) for c in range(0x2000, 0x200C)]


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn_body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    nxt = src.find("\nfunction ", start + 10)
    return src[start: nxt if nxt != -1 else len(src)]


def _destructured_params(src: str, name: str) -> list[str]:
    start = src.index(f"function {name}(")
    open_ = src.index("{", start)
    close = src.index("}:", open_)
    block = src[open_ + 1: close]
    return [re.split(r"[=:\s]", p.strip())[0] for p in block.split(",") if p.strip()]


# ---------- error 1: BAND_ORDER unused ----------
def test_band_order_removed():
    assert "BAND_ORDER" not in _src(XWALK)


def test_band_labels_and_classes_kept():
    s = _src(XWALK)
    assert "BAND_CLASSES" in s and "direct_impact" in s and "buffer_zone" in s


# ---------- error 2: irregular whitespace ----------
def test_bb_disclosure_no_irregular_whitespace():
    s = _src(BB)
    bad = [hex(ord(c)) for c in IRREGULAR if c in s]
    assert not bad, bad


def test_bb_nbsp_still_emitted_at_runtime():
    # The visual NBSP must still come from the escape constant, not a literal char.
    s = _src(BB)
    assert 'const NBSP = "\\u00A0";' in s
    assert "${value}${NBSP}${METRO_ACCESS}" in s


def test_ui_src_no_irregular_whitespace_repo_wide():
    offenders = []
    for p in UI.rglob("*"):
        if p.suffix in {".ts", ".tsx"} and "node_modules" not in p.parts:
            s = _src(p)
            for c in IRREGULAR:
                if c in s:
                    offenders.append(f"{p.relative_to(UI)}:{hex(ord(c))}")
    assert not offenders, offenders


# ---------- error 3: divColor unused in PathTraceBanner ----------
def test_path_trace_banner_no_dead_divcolor():
    assert "divColor" not in _fn_body(_src(TOPO), "PathTraceBanner")


def test_canvas_divcolor_still_used():
    s = _src(TOPO)
    assert s.count("const divColor") == 1
    assert "edgeColor = divColor" in s and "nodeStroke = divColor" in s


# ---------- errors 4-5: MobileTreeView unused callbacks ----------
def test_mobile_tree_does_not_destructure_unused_callbacks():
    params = _destructured_params(_src(TOPO), "MobileTreeView")
    assert "regions" in params and "overlays" in params
    assert "onSelectSite" not in params
    assert "onSelectConduit" not in params


def test_mobile_tree_props_interface_unchanged():
    s = _src(TOPO)
    iface = s[s.index("interface MobileTreeProps"): s.index("function MobileTreeView(")]
    assert "onSelectSite: (site: SiteNode) => void;" in iface
    assert "onSelectConduit: (conduit: ConduitEdge) => void;" in iface


# ---------- warnings: exhaustive-deps (behaviour kept, disable is justified) ----------
def _disable_lines(s: str) -> list[int]:
    lines = s.splitlines()
    return [i for i, ln in enumerate(lines) if "eslint-disable-next-line react-hooks/exhaustive-deps" in ln]


def test_exhaustive_deps_disables_are_scoped_and_justified():
    s = _src(TOPO)
    lines = s.splitlines()
    idx = _disable_lines(s)
    assert len(idx) == 2, idx
    for i in idx:
        assert "P303" in lines[i - 2] or "P303" in lines[i - 1], lines[i - 2: i + 1]
        assert lines[i + 1].strip().startswith("}, ["), lines[i + 1]


def test_effect_deps_unchanged():
    s = _src(TOPO)
    assert "}, [search.service]);" in s
    assert "}, [tracedServiceId, traceRetry]);" in s


def test_no_file_wide_eslint_disable_in_topology():
    assert "/* eslint-disable" not in _src(TOPO)


# ---------- live eslint (runs where node_modules exists) ----------
@pytest.mark.skipif(not (APP / "node_modules" / ".bin" / "eslint").exists() or shutil.which("node") is None,
                    reason="node_modules not installed")
def test_eslint_max_warnings_zero():
    r = subprocess.run(
        ["node", "node_modules/.bin/eslint", "src/**/*.{ts,tsx}", "--max-warnings", "0"],
        cwd=APP, capture_output=True, text=True, timeout=600, env={**os.environ, "NO_COLOR": "1"},
    )
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
