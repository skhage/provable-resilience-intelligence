"""BUG-DW-111: /topology residuals after BUG-DW-105.

1) No literal \\uXXXX escapes in JSX text (Clear trace glyph), glyph aria-hidden, type=button.
2) Live trace result is written to the persistent sr-only status region (4.1.3).
3) Live + 0 hops renders a neutral 'No traced path' banner (focus target after Retry).
4) Mobile diversity summaries are not live regions (single persistent region).
5) Repeat-failure copy keeps its subject.
6) CSS hygiene: tabular-nums unconditional; no duplicate hardcoded focus rule.

Pure helpers are evaluated with Node (TS type stripping); JSX wiring is checked statically.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import glob
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
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- 1) JSX text escapes ---------------------------------------------------

_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")


def jsx_text_escapes(src):
    """Return \\uXXXX escapes that sit in JSX text (between '>' and '<', outside {}).

    JSX text cannot contain unescaped < > { }, so a '>...<' run free of those is
    either JSX text or (rarely) code between comparison operators. Comments are
    stripped first so documentation mentioning escapes is ignored.
    """
    s = re.sub(r"/\*[\s\S]*?\*/", "", src)
    s = re.sub(r"(?<![:\"'\\])//[^\n]*", "", s)
    hits = []
    for m in re.finditer(r">([^<>{}]*)<", s):
        hits.extend(_ESCAPE.findall(m.group(1)))
    return hits


def test_scanner_detects_known_bad_case():
    bad = '<button className="x" onClick={f}>\n  \\u2715 Clear trace\n</button>'
    assert jsx_text_escapes(bad) == ["\\u2715"]


def test_scanner_ignores_escapes_in_js_strings_and_comments():
    ok = ('<span>{"\\u2715"}</span>\n{/* \\u2715 doc */}\n'
          'const a = `x\\u00A0y`; // \\u2026 note\n<p title="\\u2026">ok</p>')
    assert jsx_text_escapes(ok) == []


def test_no_unicode_escape_in_jsx_text_any_tsx():
    files = glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True)
    assert files, "no .tsx files found"
    offenders = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            hits = jsx_text_escapes(fh.read())
        if hits:
            offenders[os.path.relpath(f, UI)] = hits
    assert offenders == {}


def _clear_buttons(src):
    return re.findall(r"<button[^>]*className=\"path-trace-clear\"[^>]*>[\s\S]*?</button>", src)


def test_both_clear_buttons_typed_and_glyph_hidden():
    btns = _clear_buttons(_read("routes", "topology.tsx"))
    assert len(btns) == 2
    for b in btns:
        assert 'type="button"' in b
        assert '<span aria-hidden="true">\u2715</span> Clear trace' in b


# --- 2) live summary in the persistent region ------------------------------

@needs_node
def test_live_summary_copy():
    out = _node('out = m.traceLiveSummary("SVC-00001", "Fully diverse", 4, 3);')
    assert out == "SVC-00001 traced: Fully diverse, 4 working hops, 3 protect hops."


@needs_node
def test_live_summary_singular_and_no_protect():
    out = _node('out = m.traceLiveSummary("SVC-1", "Single path", 1, 0);')
    assert out == "SVC-1 traced: Single path, 1 working hop, no protect path."


@needs_node
def test_live_summary_zero_hops():
    out = _node('out = m.traceLiveSummary("SVC-9", "No path data", 0, 0);')
    assert out == "No traced path for SVC-9."


def test_live_summary_excludes_basis_caption():
    src = _read("lib", "topology-data-state.ts")
    start = src.index("export function traceLiveSummary")
    end = src.index("export function traceStatusText")
    body = src[start:end]
    assert "DIVERSITY_BASIS_CAPTION" not in body and "basis" not in body.lower()


@needs_node
def test_status_text_priority():
    base = ('{mode:"live", serviceId:"S", busy:false, retryFeedback:null, '
            'diversityLabel:"Fully diverse", workingHops:2, protectHops:2}')
    out = _node(f"""const b = {base};
out = [
  m.traceStatusText({{...b, busy:true}}),
  m.traceStatusText({{...b, retryFeedback:"F"}}),
  m.traceStatusText({{...b, mode:"unavailable"}}),
  m.traceStatusText({{...b, mode:"not_found"}}),
  m.traceStatusText(b),
  m.traceStatusText({{...b, mode:"pending"}}),
];""")
    assert out == [
        "Retrying\u2026",
        "F",
        "Path data is temporarily unavailable.",
        "Service S not found.",
        "S traced: Fully diverse, 2 working hops, 2 protect hops.",
        "",
    ]


def _persistent_region(src):
    idx = src.index("BUG-DW-105: persistent sr-only status region")
    end = src.index("</div>", idx)
    return src[idx:end]


def test_persistent_region_writes_live_summary():
    blk = _persistent_region(_read("routes", "topology.tsx"))
    assert 'role="status"' in blk and 'aria-atomic="true"' in blk
    assert "traceStatusText({" in blk
    assert "mode: traceMode" in blk
    assert "diversityLabel(diversity?.diversity_status)" in blk
    assert 'h.path_type === "working"' in blk and 'h.path_type === "protect"' in blk
    assert "DIVERSITY_BASIS_CAPTION" not in blk
    # old null-for-live expression is gone from the region
    assert "traceBannerMessage(traceMode, tracedServiceId) ?? \"\"" not in blk


# --- 3) live + 0 hops banner ---------------------------------------------

def test_banner_rendered_for_live_with_zero_hops():
    src = _read("routes", "topology.tsx")
    assert "pathHops.length > 0))" not in src
    assert ('(traceMode === "unavailable" || traceMode === "not_found" || '
            'traceMode === "live")') in src
    assert ('(mode === "live" && hops.length === 0 ? noTracedPathMsg(serviceId) : null)') in src


@needs_node
def test_no_traced_path_msg():
    assert _node('out = m.noTracedPathMsg("SVC-7");') == "No traced path for SVC-7."


# --- 4) mobile summaries not live regions ----------------------------------

def test_mobile_summaries_have_no_role_status():
    src = _read("routes", "topology.tsx")
    tags = re.findall(r"<div className=\"mobile-tree-diversity-summary\"[^>]*>", src)
    assert len(tags) == 2
    for t in tags:
        assert "role=" not in t and "aria-live" not in t


def test_single_trace_live_region_outside_mobile_branch():
    src = _read("routes", "topology.tsx")
    region = src.index("BUG-DW-105: persistent sr-only status region")
    assert region < src.index("{isMobile ? (")


# --- 5) repeat-failure copy ----------------------------------------------

@needs_node
def test_still_unavailable_keeps_subject():
    out = _node("out = m.stillUnavailableMsg(new Date(2026, 9, 29, 8, 3));")
    assert out == "Path data is still unavailable. Last checked 08:03."


# --- 6) CSS hygiene --------------------------------------------------------

def _css():
    return _read("styles", "lakelink-theme.css")


def test_tabular_nums_unconditional():
    css = _css()
    m = re.search(r"(?m)^\.path-trace-unavailable\s*\{([^}]*)\}", css)
    assert m and "font-variant-numeric: tabular-nums" in m.group(1)
    assert "[aria-busy=\"true\"] .path-trace-unavailable" not in css


def test_no_duplicate_hardcoded_banner_focus_rule():
    css = _css()
    assert not re.search(r"(?m)^\.path-trace-banner-nodata:focus-visible\s*\{", css)
    assert re.search(r"\[tabindex\]:focus-visible\s*\{\s*outline: 2px solid var\(--lf-dark-teal\)", css)


# --- Branding guard -------------------------------------------------------

def test_no_old_brand_token_in_touched_files():
    for parts in [("routes", "topology.tsx"), ("lib", "topology-data-state.ts"),
                  ("styles", "lakelink-theme.css")]:
        assert "lumen" not in _read(*parts).lower()
