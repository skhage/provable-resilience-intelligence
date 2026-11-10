"""BUG-DW-161: header data-source badge must not claim Mock Data while /api/health loads.

WCAG 4.1.3 Status Messages / honest status. The badge has four states: loading
("Checking data source", neutral), live (per-route live label), mock ("Mock Data", amber,
only when health explicitly says mock) and unavailable (health fetch failed, neutral).
Behavioral checks extract the real fetch effect from routes/__root.tsx and run it in Node
against fake fetch responses. Pure helpers in ui/lib/data-source-badge.ts run in Node too.
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
BACKEND = os.path.join(os.path.dirname(UI), "backend")
_LIB = os.path.join(UI, "lib", "data-source-badge.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _root():
    return _read("routes", "__root.tsx")


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _css():
    return _strip_comments(_read("styles", "lakelink-theme.css"))


def _block(src, start):
    """Source from `start` (which ends with '{') up to its matching close brace."""
    i = src.index(start)
    j = i + len(start) - 1
    assert src[j] == "{"
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError(start)


def _run(js):
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    return _run(js)


ROUTES = ["/", "/actions", "/hazards", "/topology", "/conduits", "/other"]


# --- pure helpers -------------------------------------------------------------

@needs_node
def test_dw161_loading_never_mock():
    out = _node(f"""out = {json.dumps(ROUTES)}.map((p) => [
  m.dataSourceBadgeLabel('loading', p), m.dataSourceBadgeClass('loading')]);""")
    for label, cls in out:
        assert label == "Checking data source"
        assert "mock" not in label.lower()
        assert "mock" not in cls.split()
        assert cls.split() == ["data-source-badge", "loading"]


@needs_node
def test_dw161_unavailable_never_mock():
    out = _node(f"""out = {json.dumps(ROUTES)}.map((p) => [
  m.dataSourceBadgeLabel('unavailable', p), m.dataSourceBadgeClass('unavailable')]);""")
    for label, cls in out:
        assert label == "Data source unavailable"
        assert "mock" not in cls.split()


@needs_node
def test_dw161_live_labels_unchanged():
    out = _node(f"out = {json.dumps(ROUTES)}.map((p) => m.dataSourceBadgeLabel('live', p));")
    assert out == ["Live Data", "Lakebase State", "Live Crosswalk", "Live Topology",
                   "Live v4 Coverage", "Live Data"]


@needs_node
def test_dw161_mock_only_when_explicit():
    out = _node("""out = [
  m.dataSourceBadgeLabel('mock', '/'), m.dataSourceBadgeClass('mock'),
  m.dataSourceFromHealth('live'), m.dataSourceFromHealth('mock'),
  m.dataSourceFromHealth(undefined), m.dataSourceFromHealth(null),
  m.dataSourceFromHealth(''), m.dataSourceFromHealth('LIVE'), m.dataSourceFromHealth(42),
];""")
    assert out == ["Mock Data", "data-source-badge mock", "live", "mock",
                   "unavailable", "unavailable", "unavailable", "unavailable", "unavailable"]


# --- real fetch effect from __root.tsx ----------------------------------------

def _effect_js():
    src = _root()
    at = src.index("BUG-DW-161")
    eff = _block(src[at:], "useEffect(() => {")
    body = eff[len("useEffect(() => {"):-1]
    return body


def _simulate(fetch_impl):
    body = _effect_js()
    js = f"""
import * as m from {json.dumps('file://' + _LIB)};
const dataSourceFromHealth = m.dataSourceFromHealth;
const states = [];
const setDataSource = (s) => states.push(s);
const fetch = {fetch_impl};
const effect = () => {{ {body} }};
const cleanup = effect();
await new Promise((r) => setTimeout(r, 20));
process.stdout.write(JSON.stringify({{states, hasCleanup: typeof cleanup === 'function'}}));
"""
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _ok(payload):
    return f"async () => ({{ ok: true, status: 200, json: async () => ({json.dumps(payload)}) }})"


@needs_node
@pytest.mark.parametrize("impl,expected", [
    (_ok({"data_source": "live"}), ["live"]),
    (_ok({"data_source": "mock"}), ["mock"]),
    (_ok({}), ["unavailable"]),
    ("async () => ({ ok: false, status: 500, json: async () => ({data_source: 'mock'}) })",
     ["unavailable"]),
    ("async () => { throw new Error('network'); }", ["unavailable"]),
    ("async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('html'); } })",
     ["unavailable"]),
])
def test_dw161_effect_states(impl, expected):
    out = _simulate(impl)
    assert out["states"] == expected
    assert out["hasCleanup"] is True


def test_dw161_root_initial_state_and_render():
    src = _strip_comments(_root())
    assert 'useState<DataSourceState>("loading")' in src
    m = re.search(r'<span className=\{([^}]*)\} role="status">\s*<span className="dot"', src)
    assert m, "data-source badge span not found"
    assert m.group(1).strip() == "dataSourceBadgeClass(dataSource)"
    assert "dataSourceBadgeLabel(dataSource, pathname)" in src
    # The old binary ternary that mapped every non-live value to mock is gone.
    assert '"live" : "mock"' not in src
    assert '"Mock Data"' not in src
    assert 'setDataSource("mock")' not in src


# --- CSS ----------------------------------------------------------------------

def _hex_lum(h):
    h = h.lstrip("#")
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _ratio(a, b):
    la, lb = sorted([_hex_lum(a), _hex_lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _token(css, name):
    m = re.search(r"--" + re.escape(name) + r":\s*(#[0-9A-Fa-f]{6})", css)
    assert m, name
    return m.group(1)


def _rule(css, selector):
    for m in re.finditer(r"(?m)^([^{}@]+)\{([^}]*)\}", css):
        sels = [s.strip() for s in m.group(1).split(",")]
        if selector in sels:
            return m.group(2)
    raise AssertionError(selector)


def _resolve(css, value):
    v = value.strip()
    m = re.fullmatch(r"var\(--([\w-]+)\)", v)
    return _token(css, m.group(1)) if m else v


@pytest.mark.parametrize("state", ["loading", "unavailable"])
def test_dw161_neutral_badge_contrast(state):
    css = _css()
    body = _rule(css, f".data-source-badge.{state}")
    bg = _resolve(css, re.search(r"background:\s*([^;]+);", body).group(1))
    fg = _resolve(css, re.search(r"(?<![-\w])color:\s*([^;]+);", body).group(1))
    assert bg.upper() == "#E8E8E8" and fg.upper() == "#4D4D4D"
    # 11px uppercase text is not large text, so 4.5:1 applies.
    assert _ratio(fg, bg) >= 4.5
    dot = _rule(css, f".data-source-badge.{state} .dot")
    assert _resolve(css, re.search(r"background:\s*([^;]+);", dot).group(1)).upper() == "#4D4D4D"
    # dot is non-text: 3:1 against the badge background
    assert _ratio("#4D4D4D", bg) >= 3.0


def test_dw161_neutral_badge_not_amber():
    css = _css()
    mock = _rule(css, ".data-source-badge.mock")
    for state in ("loading", "unavailable"):
        body = _rule(css, f".data-source-badge.{state}")
        assert "#FEF3C7" not in body.upper() and "#92400E" not in body.upper()
        assert body != mock


def test_dw161_forced_colors_border_covers_all_states():
    css = _css()
    blocks = []
    for mm in re.finditer(r"@media \(forced-colors: active\)\s*\{", css):
        blocks.append(_block(css[mm.start():], css[mm.start():mm.end()]))
    assert blocks
    fc_rules = [m.group(1) for b in blocks
                for m in re.finditer(r"(?m)^\s*\.data-source-badge\s*\{([^}]*)\}", b)]
    assert any("CanvasText" in r for r in fc_rules)
    # The forced-colors rule is on the base class, so every modifier inherits it.
    assert not re.search(r"\.data-source-badge\.(loading|unavailable)[^{]*\{[^}]*border:\s*none", css)


def test_dw161_no_lumen():
    hits = []
    for root in (UI, BACKEND):
        for dp, _, fs in os.walk(root):
            if "node_modules" in dp:
                continue
            for f in fs:
                if f.endswith((".ts", ".tsx", ".css", ".py")):
                    with open(os.path.join(dp, f), encoding="utf-8", errors="ignore") as fh:
                        if "lumen" in fh.read().lower():
                            hits.append(os.path.join(dp, f))
    assert hits == []
