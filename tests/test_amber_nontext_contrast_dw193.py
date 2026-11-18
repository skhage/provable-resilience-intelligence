"""BUG-DW-193: Medium Risk KPI stripe and fair score gauge used amber #F9A825 (1.97:1 white, 1.61:1 platinum).

Binding @designer S146 (WCAG 1.4.11 non-text contrast, 1.4.1 use of colour).
Fix: new --lf-risk-amber-strong #B45309 (5.02:1 white / 4.10:1 platinum) for .kpi-card.warning
and --score-fair; #F9A825 kept only for decorative dots. The gauge meter exposes its band label as
aria-valuetext. Static CSS resolver + WCAG contrast maths, no npm needed.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")
TABLE = os.path.join(UI, "components", "dashboard", "service-table.tsx")
BAND_TS = os.path.join(UI, "lib", "score-band.ts")
BANNED = "lu" + "men"
WHITE = "#FFFFFF"
PLATINUM = "#E8E8E8"
# @designer (c): orange brand stripe is out of scope. It passes on the white card interior (3.15:1)
# but is 2.57:1 against the platinum page; reported, not changed.
PLATINUM_EXEMPT_STRIPES = {"high"}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _root_vars(css):
    css = _strip_comments(css)
    m = re.search(r":root\s*\{(.*?)\n\}", css, flags=re.S)
    assert m, ":root block not found"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


def _resolve(value, vars_, depth=0):
    value = value.strip()
    assert depth < 10, "var() cycle: " + value
    m = re.fullmatch(r"var\((--[\w-]+)(?:\s*,\s*([^)]+))?\)", value)
    if m:
        # var(--x, fallback): the fallback only applies when --x is undefined
        name, fallback = m.group(1), m.group(2)
        return _resolve(vars_[name] if name in vars_ else fallback, vars_, depth + 1)
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), "unresolvable colour: " + value
    return value.upper()


def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _top_level_rules(css, selector_regex, prop):
    """Return {modifier: value} for top-level (non-@media) rules."""
    css = _strip_comments(css)
    out = {}
    depth = 0
    # walk braces so @media / @supports nested rules are skipped
    top = []
    buf = ""
    for ch in css:
        if ch == "{":
            depth += 1
        buf += ch
        if ch == "}":
            depth -= 1
            if depth == 0:
                top.append(buf)
                buf = ""
    for block in top:
        if block.lstrip().startswith("@"):
            continue
        sel, _, body = block.partition("{")
        for s in sel.split(","):
            m = re.fullmatch(selector_regex, s.strip())
            if m:
                pm = re.search(prop + r"\s*:\s*([^;]+);", body)
                if pm:
                    out[m.group(1)] = pm.group(1).strip()
    return out


@pytest.fixture(scope="module")
def css():
    return _read(CSS)


@pytest.fixture(scope="module")
def vars_(css):
    return _root_vars(css)


# --- known-answer checks on the contrast helper (WCAG reference values) ---
def test_contrast_helper_known_answers():
    assert round(_cr("#000000", "#FFFFFF"), 2) == 21.0
    assert round(_cr("#F9A825", WHITE), 2) == 1.97
    assert round(_cr("#F9A825", PLATINUM), 2) == 1.61
    assert round(_cr("#B45309", WHITE), 2) == 5.02
    assert round(_cr("#B45309", PLATINUM), 2) == 4.10


# --- (a) token ---
def test_strong_amber_token_defined(vars_):
    assert _resolve("var(--lf-risk-amber-strong)", vars_) == "#B45309"


def test_decorative_amber_kept(vars_):
    assert _resolve("var(--lf-risk-amber)", vars_) == "#F9A825"


def test_warning_stripe_uses_strong_amber(css):
    stripes = _top_level_rules(css, r"\.kpi-card\.([\w-]+)", "border-left-color")
    assert stripes.get("warning") == "var(--lf-risk-amber-strong)"


def test_score_fair_uses_strong_amber(vars_):
    assert vars_["--score-fair"].strip() == "var(--lf-risk-amber-strong)"


# --- every stripe >= 3:1 on white card interior; >= 3:1 on platinum page (orange exempt) ---
def test_every_kpi_stripe_contrast(css, vars_):
    stripes = _top_level_rules(css, r"\.kpi-card\.([\w-]+)", "border-left-color")
    assert {"critical", "high", "warning", "success"} <= set(stripes), stripes
    bad = []
    for mod, val in stripes.items():
        col = _resolve(val, vars_)
        if _cr(col, WHITE) < 3.0:
            bad.append((mod, col, "white", round(_cr(col, WHITE), 2)))
        if mod not in PLATINUM_EXEMPT_STRIPES and _cr(col, PLATINUM) < 3.0:
            bad.append((mod, col, "platinum", round(_cr(col, PLATINUM), 2)))
    assert not bad, bad


# --- every gauge-fill band >= 3:1 on the white gauge interior (DW-145) and fair also on platinum ---
def test_every_gauge_fill_contrast(css, vars_):
    fills = _top_level_rules(css, r"\.score-gauge \.gauge-fill\.([\w-]+)", "background")
    assert set(fills) == {"excellent", "good", "fair", "poor", "failing"}, fills
    bad = [(k, _resolve(v, vars_), round(_cr(_resolve(v, vars_), WHITE), 2))
           for k, v in fills.items() if _cr(_resolve(v, vars_), WHITE) < 3.0]
    assert not bad, bad
    fair = _resolve(fills["fair"], vars_)
    assert _cr(fair, PLATINUM) >= 3.0


def test_gauge_interior_is_white(css):
    bars = _top_level_rules(css, r"(\.score-gauge \.gauge-bar)", "background")
    assert bars.get(".score-gauge .gauge-bar") == "var(--lf-white)"


def test_no_nontext_use_of_pale_amber(css):
    """#F9A825 may only colour decorative dots; never a stripe, gauge fill or score token."""
    body = _strip_comments(css)
    uses = re.findall(r"([^{}]*)\{[^{}]*var\(--lf-risk-amber\)[^{}]*\}", body)
    sels = [u.strip() for u in uses]
    for s in sels:
        assert "kpi-card" not in s and "gauge-fill" not in s, s
    assert "--score-fair: var(--lf-risk-amber)" not in body


# --- (b) every band has a text label (WCAG 1.4.1) ---
def test_every_band_has_label():
    ts = _read(BAND_TS)
    for key, label in [("excellent", "Excellent"), ("good", "Good"), ("fair", "Fair"), ("poor", "Poor")]:
        assert '{ min: ' in ts and f'key: "{key}", label: "{label}"' in ts
    assert 'key: "failing", label: "Failing"' in ts


def test_gauge_exposes_band_label():
    src = _read(TABLE)
    gauge = src[src.index("function ScoreGauge"):src.index("const PAGE_SIZES")]
    assert "const band = scoreBand(score);" in gauge
    assert "aria-valuetext={`${score.toFixed(1)} out of 100, ${band.label}`}" in gauge
    assert "gauge-fill ${band.key}" in gauge


# --- BUG-DW-194: regression guard, pale amber only via --lf-risk-amber on the mock-badge dot ---
PALE_AMBER = "#F9A825"
PALE_AMBER_TOKEN = "--lf-risk-amber"
PALE_AMBER_CONSUMERS = {".data-source-badge.mock .dot"}


def test_only_decorative_token_resolves_to_pale_amber(vars_):
    offenders = []
    for name, val in vars_.items():
        if name == PALE_AMBER_TOKEN:
            continue
        try:
            col = _resolve(val, vars_)
        except AssertionError:
            continue  # non-colour token (sizes, fonts, shadows)
        if col == PALE_AMBER:
            offenders.append(name)
    assert not offenders, offenders


def test_dead_rating_tokens_removed(vars_):
    assert not [n for n in vars_ if n.startswith("--rating-")], "dead --rating-* tokens are back"


def test_pale_amber_consumer_allowlist(css):
    body = _strip_comments(css)
    sels = set()
    for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", body):
        if re.search(r"var\(" + re.escape(PALE_AMBER_TOKEN) + r"\)", m.group(2)) or PALE_AMBER.lower() in m.group(2).lower():
            sel = m.group(1).strip()
            if not sel.startswith(":root"):
                sels.add(sel)
    assert sels <= PALE_AMBER_CONSUMERS, sels - PALE_AMBER_CONSUMERS


def test_no_ts_consumer_of_rating_or_pale_amber():
    hits = []
    for d, _, files in os.walk(UI):
        if "node_modules" in d:
            continue
        for f in files:
            if f.endswith((".ts", ".tsx")):
                src = _read(os.path.join(d, f))
                if "--rating-" in src or PALE_AMBER.lower() in src.lower():
                    hits.append(f)
    assert not hits, hits


def test_gauge_band_announced_once():
    """title on the role=meter span doubles the band as an accessible description."""
    src = _read(TABLE)
    gauge = src[src.index("function ScoreGauge"):src.index("const PAGE_SIZES")]
    meter_open = gauge[gauge.index('role="meter"'):gauge.index(">", gauge.index("aria-label="))]
    assert "title=" not in meter_open
    assert '<span className="gauge-bar" aria-hidden="true" title={band.label}>' in gauge


# --- branding ---
def test_brand_grep_zero():
    for p in (CSS, TABLE, __file__):
        assert BANNED not in _read(p).lower(), p
