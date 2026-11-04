"""
BUG-DW-133: SiteGraph drill-in clipped most T1/T2 sites off the 1200 viewBox while they
stayed keyboard-focusable.

Fix (designer option 2): per-tier cap (T1 18, T2 22) with pinned sites first, then
conduit_count desc; hidden sites are not rendered; visible 'Showing N of M' note plus a
'Show all sites' list.

Acceptance:
  (a) fixture 171 T1 + 76 T2: every rendered position inside [r, 1200 - r] (and y in [r, 600 - r])
  (b) tab-order count (rendered focusable nodes) == visible count == positions placed
  (c) live region sizes (Central/East/Southeast/West) all fit
  (d) pinned sites always drawn when the row can hold them; most connected first otherwise
  (e) visible copy + svg name reflect what is drawn; unchanged wording when nothing is hidden
  (f) source wiring: SiteGraph renders siteCap.visible only; old layoutSites removed
  (g) no 'lumen' in new/changed files
"""
import json
import os
import re
import subprocess
import textwrap

import pytest

PROJECT = "/Workspace/Users/stephen.hage@databricks.com/provable-resilience-intelligence"
UI_DIR = os.path.join(PROJECT, "apps/resilience-scorecard/src/resilience_scorecard/ui")
LIB_DIR = os.path.join(UI_DIR, "lib")
LAYOUT_PATH = os.path.join(LIB_DIR, "site-graph-layout.ts")
TOPOLOGY_PATH = os.path.join(UI_DIR, "routes/topology.tsx")
CSS_PATH = os.path.join(UI_DIR, "styles/lakelink-theme.css")

CANVAS_W, CANVAS_H = 1200, 600
R_T1, R_T2 = 20, 14


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _node_ts(code: str):
    r = subprocess.run(
        ["node", "--experimental-strip-types", "-e", code],
        capture_output=True, text=True, timeout=20, cwd=LIB_DIR,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


def _fixture_js(n1: int, n2: int) -> str:
    # deterministic conduit counts: T1 i -> (i * 7) % 23, T2 i -> (i * 5) % 11
    return textwrap.dedent(f"""\
        const sites = [];
        for (let i = 0; i < {n1}; i++) sites.push({{ site_id: 'T1-' + String(i).padStart(3, '0'), tier: 'tier_1', conduit_count: (i * 7) % 23 }});
        for (let i = 0; i < {n2}; i++) sites.push({{ site_id: 'T2-' + String(i).padStart(3, '0'), tier: 'tier_2', conduit_count: (i * 5) % 11 }});
        sites.push({{ site_id: 'X-1', tier: null, conduit_count: 99 }});
    """)


def _run_cap(n1, n2, pinned=()):
    pinned_js = json.dumps(list(pinned))
    return _node_ts(
        "import { capSites, layoutVisibleSites, siteCapNote, siteGraphAriaLabel } from './site-graph-layout.ts';\n"
        + _fixture_js(n1, n2)
        + textwrap.dedent(f"""\
            const cap = capSites(sites, new Set({pinned_js}));
            const pos = layoutVisibleSites(cap.visible);
            const out = [];
            for (const s of cap.visible) {{ const p = pos.get(s.site_id); out.push({{ id: s.site_id, tier: s.tier, cc: s.conduit_count, x: p ? p.x : null, y: p ? p.y : null }}); }}
            console.log(JSON.stringify({{
              t1: cap.t1, t2: cap.t2, hidden: cap.hidden.length, pinnedNotShown: cap.pinnedNotShown,
              placed: pos.size, visible: out, note: siteCapNote(cap),
              aria: siteGraphAriaLabel('Southeast', cap, sites.length, 40, 300),
              hiddenIds: cap.hidden.map((s) => s.site_id),
            }}));
        """)
    )


# ── (a)(b) the mandated fixture ─────────────────────────────────────────

class TestFixture171x76:
    def setup_method(self):
        self.d = _run_cap(171, 76)

    def test_caps(self):
        assert self.d["t1"] == {"shown": 18, "total": 171}
        assert self.d["t2"] == {"shown": 22, "total": 76}
        assert self.d["hidden"] == (171 - 18) + (76 - 22)

    def test_every_position_inside_viewbox(self):
        for v in self.d["visible"]:
            r = R_T1 if v["tier"] == "tier_1" else R_T2
            assert v["x"] is not None, v
            assert r <= v["x"] <= CANVAS_W - r, v
            assert r <= v["y"] <= CANVAS_H - r, v

    def test_tab_order_count_equals_visible_count(self):
        # Each visible site renders exactly one <g tabIndex=0>; hidden sites render nothing.
        assert self.d["placed"] == len(self.d["visible"]) == 40

    def test_no_overlap_min_spacing(self):
        for tier, min_sp in (("tier_1", 60), ("tier_2", 50)):
            xs = sorted(v["x"] for v in self.d["visible"] if v["tier"] == tier)
            gaps = [b - a for a, b in zip(xs, xs[1:])]
            assert min(gaps) >= min_sp - 1e-9

    def test_untiered_site_excluded(self):
        ids = {v["id"] for v in self.d["visible"]}
        assert "X-1" not in ids and "X-1" not in self.d["hiddenIds"]

    def test_most_connected_first(self):
        t1_cc = sorted((v["cc"] for v in self.d["visible"] if v["tier"] == "tier_1"), reverse=True)
        # 171 sites with (i*7)%23 -> values 0..22, each ~7-8 times; top 18 are all 22 or 21 or 20
        assert min(t1_cc) >= 20

    def test_note_copy(self):
        assert self.d["note"] == "Showing 18 of 171 backbone sites and 22 of 76 regional sites, most connected first."

    def test_aria_label_states_what_is_drawn(self):
        a = self.d["aria"]
        assert a.startswith("Southeast topology: showing 40 of 248 sites")
        assert "(18 of 171 backbone, 22 of 76 regional)" in a
        assert "40 of 300 conduits drawn" in a


def test_old_layout_clipped_documented():
    """Known answer for the bug: the old one-row formula only kept 19 T1 / 23 T2 inside 0-1200."""
    def inside(n, min_sp):
        sp = max(min_sp, 1100 / n)
        return sum(1 for i in range(n) if 50 + i * sp + sp / 2 <= 1200)
    assert inside(171, 60) == 19
    assert inside(76, 50) == 23


# ── (c) live region sizes ──────────────────────────────────────────────

@pytest.mark.parametrize("region,n1,n2", [
    ("Central", 112, 61), ("East", 104, 65), ("Southeast", 171, 75), ("West", 170, 76),
    ("small", 10, 5), ("edge", 18, 22), ("edge+1", 19, 23), ("one", 1, 1),
])
def test_live_and_edge_sizes_fit(region, n1, n2):
    d = _run_cap(n1, n2)
    assert d["t1"]["shown"] == min(n1, 18)
    assert d["t2"]["shown"] == min(n2, 22)
    assert d["placed"] == len(d["visible"])
    for v in d["visible"]:
        r = R_T1 if v["tier"] == "tier_1" else R_T2
        assert r <= v["x"] <= CANVAS_W - r


def test_nothing_hidden_keeps_original_copy():
    d = _run_cap(10, 5)
    assert d["note"] is None
    assert d["hidden"] == 0
    assert d["aria"] == "Southeast topology: 16 sites (10 backbone, 5 regional), 300 conduits"


# ── (d) pinning ────────────────────────────────────────────────────────

def test_pinned_low_connectivity_sites_are_drawn():
    # T1-000 has conduit_count 0 and T2-000 has 0: never in the top N without a pin
    d = _run_cap(171, 76, pinned=["T1-000", "T2-000"])
    ids = {v["id"] for v in d["visible"]}
    assert {"T1-000", "T2-000"} <= ids
    assert d["t1"]["shown"] == 18 and d["t2"]["shown"] == 22
    assert d["pinnedNotShown"] == 0
    unpinned = _run_cap(171, 76)
    assert "T1-000" not in {v["id"] for v in unpinned["visible"]}


def test_pins_beyond_capacity_are_counted():
    pins = [f"T1-{i:03d}" for i in range(25)]
    d = _run_cap(171, 76, pinned=pins)
    t1_ids = {v["id"] for v in d["visible"] if v["tier"] == "tier_1"}
    assert t1_ids <= set(pins) and len(t1_ids) == 18
    assert d["pinnedNotShown"] == 7


def test_visible_keeps_api_order():
    d = _run_cap(171, 76)
    t1 = [v["id"] for v in d["visible"] if v["tier"] == "tier_1"]
    assert t1 == sorted(t1)
    xs = [v["x"] for v in d["visible"] if v["tier"] == "tier_1"]
    assert xs == sorted(xs)


# ── (f) source wiring ──────────────────────────────────────────────────

def _site_graph_block(src: str) -> str:
    start = src.index("function SiteGraph(")
    end = src.index("\nfunction ", start + 10)
    return src[start:end]


def test_old_layout_removed():
    src = _read(TOPOLOGY_PATH)
    assert "function layoutSites(" not in src
    assert "t1Spacing" not in src and "t2Spacing" not in src


def test_site_graph_renders_capped_sites_only():
    block = _site_graph_block(_read(TOPOLOGY_PATH))
    assert "siteCap.visible.map((s) =>" in block
    assert "{sites.map(" not in block
    assert "layoutVisibleSites(siteCap.visible)" in block
    assert "aria-label={siteGraphAriaLabel(" in block


def test_page_wires_cap_and_hops_shown():
    src = _read(TOPOLOGY_PATH)
    assert "capSites(sites, pinnedSiteIds)" in src
    assert "siteCap={siteCap}" in src
    assert "isMobile ? sites : siteCap.visible" in src
    pinned = src[src.index("const pinnedSiteIds = useMemo"):]
    pinned = pinned[: pinned.index("}, [")]
    for needle in ("selectedSite.site_id", "span_site_a_id", "span_site_z_id",
                   "selectedConduit.site_a_id", "selectedConduit.site_z_id"):
        assert needle in pinned


def test_site_cap_bar_disclosure_semantics():
    src = _read(TOPOLOGY_PATH)
    bar = src[src.index("function SiteCapBar("):src.index("function SiteGraph(")]
    assert 'aria-expanded={open}' in bar
    assert 'aria-controls="site-cap-list"' in bar
    assert 'id="site-cap-list"' in bar
    assert 'aria-pressed={isSelected}' in bar
    assert 'type="button"' in bar
    assert "tabIndex" not in bar  # native buttons only
    assert "[...cap.visible, ...cap.hidden]" in bar  # Show all = every tiered site
    assert not re.search(r"\\u[0-9A-Fa-f]{4}", bar)  # no literal escapes in JSX text


def test_bar_rendered_outside_canvas_wrap():
    src = _read(TOPOLOGY_PATH)
    i_bar = src.index("<SiteCapBar")
    i_wrap = src.index('<div className="topo-canvas-wrap">', i_bar)
    assert i_wrap > i_bar
    assert "hasHiddenSites(siteCap)" in src[i_bar - 200:i_bar]


# ── CSS ────────────────────────────────────────────────────────────────

def _rule(css: str, sel: str) -> str:
    m = re.search(r"(?m)^" + re.escape(sel) + r"\s*\{([^}]*)\}", css)
    assert m, sel
    return m.group(1)


def test_css_note_and_targets():
    css = _read(CSS_PATH)
    note = _rule(css, ".site-cap-note")
    assert "font-size: 12px" in note and "var(--lf-iron)" in note
    assert "min-height: 44px" in _rule(css, ".site-cap-toggle")
    assert "min-height: 44px" in _rule(css, ".site-cap-item")
    assert "overflow-y: auto" in _rule(css, ".site-cap-list")


def _rel_lum(hex_):
    h = hex_.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted((_rel_lum(a), _rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("fg,bg,minimum", [
    ("#4D4D4D", "#FFFFFF", 4.5),  # note / meta on white
    ("#4D4D4D", "#E8E8E8", 4.5),  # meta on hover/pressed platinum
    ("#006272", "#E8E8E8", 4.5),  # name on pressed platinum
    ("#006272", "#FFFFFF", 4.5),  # toggle text
])
def test_contrast(fg, bg, minimum):
    assert _contrast(fg, bg) >= minimum


# ── (g) branding ──────────────────────────────────────────────────────

def test_no_lumen_in_changed_files():
    for p in (LAYOUT_PATH, TOPOLOGY_PATH, CSS_PATH):
        assert "lumen" not in _read(p).lower(), p
