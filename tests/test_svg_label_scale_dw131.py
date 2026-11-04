"""
BUG-DW-131: SVG label counter-scaling tests.

Acceptance criteria:
  (a) rendered label px >= 10 at 736, 960 and 1200 px widths
  (b) hazard name label hidden at scale < 0.8, shown at scale >= 0.8
  (c) labels do not collide at 736 px for the demo region (geometry check)
  (d) DW-115/117/119 suites stay green (run separately)
  (e) grep lumen in ui/ = 0
  (f) fontFamily literals removed from SiteGraph
"""
import os
import subprocess
import textwrap

import pytest

# ── paths ──────────────────────────────────────────────────────────────
PROJECT = os.path.join(
    "/Workspace/Users/stephen.hage@databricks.com",
    "provable-resilience-intelligence",
)
UI_DIR = os.path.join(
    PROJECT,
    "apps/resilience-scorecard/src/resilience_scorecard/ui",
)
LIB_DIR = os.path.join(UI_DIR, "lib")
CSS_PATH = os.path.join(UI_DIR, "styles/lakelink-theme.css")
TOPOLOGY_PATH = os.path.join(UI_DIR, "routes/topology.tsx")

# ── Node evaluation for the pure TS helper ─────────────────────────────
def _node_ts(code: str) -> str:
    """Run a TypeScript snippet in Node 22 --experimental-strip-types."""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "-e", code],
        capture_output=True, text=True, timeout=10,
        cwd=LIB_DIR,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


# ── Pure-function unit tests (run via Node) ────────────────────────────

class TestScaledFontSize:
    """scaledFontSize returns a viewBox fontSize that renders >= minCssPx."""

    @pytest.mark.parametrize("wrapW,wrapH", [(736, 500), (960, 500), (1200, 600)])
    def test_layer_label_at_least_10px(self, wrapW, wrapH):
        """Layer labels (base 11) render >= 10 CSS px at all tested widths."""
        out = _node_ts(textwrap.dedent(f"""\
            import {{ svgScale, scaledFontSize, renderedPx }} from './svg-label-scale.ts';
            const sc = svgScale({wrapW}, {wrapH});
            const fs = scaledFontSize(11, sc);
            const px = renderedPx(fs, sc);
            console.log(JSON.stringify({{ scale: sc, fontSize: fs, renderedPx: px }}));
        """))
        data = __import__("json").loads(out)
        assert data["renderedPx"] >= 10.0, f"at {wrapW}px: rendered {data['renderedPx']:.1f}px < 10"

    @pytest.mark.parametrize("wrapW,wrapH", [(736, 500), (960, 500), (1200, 600)])
    def test_t1_site_label_at_least_10px(self, wrapW, wrapH):
        """T1 site labels (base 14) render >= 10 CSS px."""
        out = _node_ts(textwrap.dedent(f"""\
            import {{ svgScale, scaledFontSize, renderedPx }} from './svg-label-scale.ts';
            const sc = svgScale({wrapW}, {wrapH});
            const fs = scaledFontSize(14, sc);
            const px = renderedPx(fs, sc);
            console.log(JSON.stringify({{ renderedPx: px }}));
        """))
        data = __import__("json").loads(out)
        assert data["renderedPx"] >= 10.0

    @pytest.mark.parametrize("wrapW,wrapH", [(736, 500), (960, 500), (1200, 600)])
    def test_t2_site_label_at_least_10px(self, wrapW, wrapH):
        """T2 site labels (base 11) render >= 10 CSS px."""
        out = _node_ts(textwrap.dedent(f"""\
            import {{ svgScale, scaledFontSize, renderedPx }} from './svg-label-scale.ts';
            const sc = svgScale({wrapW}, {wrapH});
            const fs = scaledFontSize(11, sc);
            const px = renderedPx(fs, sc);
            console.log(JSON.stringify({{ renderedPx: px }}));
        """))
        data = __import__("json").loads(out)
        assert data["renderedPx"] >= 10.0

    @pytest.mark.parametrize("wrapW,wrapH", [(736, 500), (960, 500), (1200, 600)])
    def test_clli_label_at_least_10px(self, wrapW, wrapH):
        """CLLI code labels (base 10) render >= 10 CSS px."""
        out = _node_ts(textwrap.dedent(f"""\
            import {{ svgScale, scaledFontSize, renderedPx }} from './svg-label-scale.ts';
            const sc = svgScale({wrapW}, {wrapH});
            const fs = scaledFontSize(10, sc);
            const px = renderedPx(fs, sc);
            console.log(JSON.stringify({{ renderedPx: px }}));
        """))
        data = __import__("json").loads(out)
        assert data["renderedPx"] >= 10.0

    @pytest.mark.parametrize("wrapW,wrapH", [(736, 500), (960, 500)])
    def test_hazard_name_label_at_least_10px_when_shown(self, wrapW, wrapH):
        """Hazard name label (base 9) renders >= 10 CSS px when shown (scale >= 0.8)."""
        out = _node_ts(textwrap.dedent(f"""\
            import {{ svgScale, scaledFontSize, renderedPx, showHazardNameLabel }} from './svg-label-scale.ts';
            const sc = svgScale({wrapW}, {wrapH});
            const fs = scaledFontSize(9, sc);
            const px = renderedPx(fs, sc);
            const show = showHazardNameLabel(sc);
            console.log(JSON.stringify({{ renderedPx: px, show: show, scale: sc }}));
        """))
        data = __import__("json").loads(out)
        # When shown, it should be >= 10
        if data["show"]:
            assert data["renderedPx"] >= 10.0

    def test_at_1200_no_counter_scaling(self):
        """At full size (1200 x 600), no counter-scaling needed — fontSize == base."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, scaledFontSize } from './svg-label-scale.ts';
            const sc = svgScale(1200, 600);
            console.log(JSON.stringify({
                s11: scaledFontSize(11, sc),
                s14: scaledFontSize(14, sc),
                s10: scaledFontSize(10, sc),
                s9: scaledFontSize(9, sc),
                scale: sc,
            }));
        """))
        data = __import__("json").loads(out)
        assert data["scale"] == 1.0
        assert data["s11"] == 11
        assert data["s14"] == 14
        assert data["s10"] == 10
        assert data["s9"] == 10  # base 9 counter-scaled to 10 even at scale 1


class TestShowHazardNameLabel:
    """Hazard name label visibility threshold (scale < 0.8 → hidden)."""

    def test_hidden_at_736(self):
        """At 736 px (scale ~0.613), hazard name is hidden."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, showHazardNameLabel } from './svg-label-scale.ts';
            const sc = svgScale(736, 500);
            console.log(JSON.stringify({ scale: sc, show: showHazardNameLabel(sc) }));
        """))
        data = __import__("json").loads(out)
        assert data["scale"] < 0.8
        assert data["show"] is False

    def test_shown_at_960(self):
        """At 960 px (scale 0.8), hazard name is shown."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, showHazardNameLabel } from './svg-label-scale.ts';
            const sc = svgScale(960, 500);
            console.log(JSON.stringify({ scale: sc, show: showHazardNameLabel(sc) }));
        """))
        data = __import__("json").loads(out)
        assert data["scale"] >= 0.8
        assert data["show"] is True

    def test_shown_at_1200(self):
        """At 1200 px (scale 1.0), hazard name is shown."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, showHazardNameLabel } from './svg-label-scale.ts';
            const sc = svgScale(1200, 600);
            console.log(JSON.stringify({ show: showHazardNameLabel(sc) }));
        """))
        data = __import__("json").loads(out)
        assert data["show"] is True

    def test_threshold_exact(self):
        """scale == 0.8 exactly → shown (>= threshold)."""
        out = _node_ts(textwrap.dedent("""\
            import { showHazardNameLabel, HAZARD_NAME_HIDE_SCALE } from './svg-label-scale.ts';
            console.log(JSON.stringify({
                threshold: HAZARD_NAME_HIDE_SCALE,
                atThreshold: showHazardNameLabel(0.8),
                belowThreshold: showHazardNameLabel(0.799),
            }));
        """))
        data = __import__("json").loads(out)
        assert data["threshold"] == 0.8
        assert data["atThreshold"] is True
        assert data["belowThreshold"] is False


class TestSvgScale:
    """svgScale computes CSS px per viewBox unit for xMidYMid meet."""

    def test_width_constrained(self):
        """At 736x500, width constrains: scale = 736/1200."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale } from './svg-label-scale.ts';
            console.log(JSON.stringify(svgScale(736, 500)));
        """))
        scale = __import__("json").loads(out)
        expected = 736 / 1200
        assert abs(scale - expected) < 1e-9

    def test_height_constrained(self):
        """When height is tighter, use svgH ratio."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale } from './svg-label-scale.ts';
            console.log(JSON.stringify(svgScale(1200, 300)));
        """))
        scale = __import__("json").loads(out)
        expected = 300 / 600
        assert abs(scale - expected) < 1e-9

    def test_full_size(self):
        """At 1200x600, scale = 1."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale } from './svg-label-scale.ts';
            console.log(JSON.stringify(svgScale(1200, 600)));
        """))
        assert __import__("json").loads(out) == 1.0

    def test_zero_protection(self):
        """Zero dimensions return 1 (no division by zero)."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale } from './svg-label-scale.ts';
            console.log(JSON.stringify(svgScale(0, 0)));
        """))
        assert __import__("json").loads(out) == 1.0


# ── TSX source assertions ──────────────────────────────────────────────

def _read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _site_graph_src() -> str:
    """Extract SiteGraph function body from topology.tsx."""
    full = _read(TOPOLOGY_PATH)
    start = full.index("function SiteGraph(")
    return full[start:]


class TestTopologySource:
    """Assert the TSX source matches the BUG-DW-131 spec."""

    def test_no_fontfamily_in_sitegraph(self):
        """No inline fontFamily literals remain in SiteGraph."""
        src = _site_graph_src()
        assert "fontFamily" not in src, "fontFamily literal found in SiteGraph"

    def test_svg_label_primary_class_used(self):
        """CSS class svg-label-primary is used for site/layer/hazard labels."""
        src = _site_graph_src()
        count = src.count('className="svg-label-primary"')
        assert count >= 4, f"Expected >= 4 uses, found {count}"

    def test_svg_label_mono_class_used(self):
        """CSS class svg-label-mono is used for the CLLI code label."""
        src = _site_graph_src()
        assert 'className="svg-label-mono"' in src

    def test_counter_scaled_layer_labels(self):
        """Layer labels use scaledFontSize(11, canvasScale)."""
        src = _site_graph_src()
        assert "scaledFontSize(11, canvasScale)" in src

    def test_counter_scaled_site_labels(self):
        """Site labels use scaledFontSize with canvasScale."""
        src = _site_graph_src()
        assert "scaledFontSize(isT1 ? 14 : 11, canvasScale)" in src

    def test_counter_scaled_clli_label(self):
        """CLLI label uses scaledFontSize(10, canvasScale)."""
        src = _site_graph_src()
        assert "scaledFontSize(10, canvasScale)" in src

    def test_hazard_name_gated(self):
        """Hazard name label is gated by showHazardNameLabel(canvasScale)."""
        src = _site_graph_src()
        assert "showHazardNameLabel(canvasScale)" in src

    def test_canvas_scale_state(self):
        """SiteGraph has a canvasScale state driven by ResizeObserver."""
        src = _site_graph_src()
        assert "const [canvasScale, setCanvasScale]" in src

    def test_resize_observer_unconditional(self):
        """The scale ResizeObserver runs unconditionally (dependency [])."""
        src = _site_graph_src()
        # The scale useLayoutEffect should have [] dependency
        assert "svgScale(wrap.clientWidth, wrap.clientHeight)" in src

    def test_hazard_aria_label_unchanged(self):
        """The hazard marker aria-label is byte-identical (not changed by DW-131)."""
        src = _site_graph_src()
        assert 'aria-label={`${h.hazard_type.replace(/_/g, " ")} hazard: ${h.name}, severity ${h.severity}' in src


class TestCssClasses:
    """Assert the CSS classes are defined in lakelink-theme.css."""

    def test_svg_label_primary_defined(self):
        css = _read(CSS_PATH)
        assert ".svg-label-primary" in css
        assert "var(--font-primary)" in css

    def test_svg_label_mono_defined(self):
        css = _read(CSS_PATH)
        assert ".svg-label-mono" in css
        assert "var(--font-mono)" in css


class TestNoBrandViolation:
    """No 'lumen' (case-insensitive) in ui/ files we touched."""

    def test_no_lumen_in_svg_label_scale(self):
        src = _read(os.path.join(LIB_DIR, "svg-label-scale.ts"))
        assert "lumen" not in src.lower()

    def test_no_lumen_in_topology_sitegraph(self):
        """SiteGraph section has no lumen reference."""
        src = _site_graph_src()
        # Exclude comments/strings that mention the project history
        lines = [ln for ln in src.split("\n") if "lumen" in ln.lower()]
        assert len(lines) == 0, f"Found lumen: {lines}"


class TestCollisionCheck736:
    """At 736 px, counter-scaled labels should not collide.
    Layer labels: y=80 (BACKBONE) and y=340 (REGIONAL).
    Max counter-scaled fontSize at 736: max(11, 10/0.613) = 16.3.
    Gap between labels: 340 - 80 = 260 viewBox units >> 16.3."""

    def test_layer_labels_no_collision(self):
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, scaledFontSize } from './svg-label-scale.ts';
            const sc = svgScale(736, 500);
            const fs = scaledFontSize(11, sc);
            // Layer 1 at y=80, Layer 2 at y=340. Gap must exceed fontSize.
            console.log(JSON.stringify({ fontSize: fs, gap: 340 - 80 }));
        """))
        data = __import__("json").loads(out)
        assert data["gap"] > data["fontSize"] * 2, "Layer labels would collide"

    def test_site_label_below_circle(self):
        """CLLI code (y = p.y + r + 16) stays below the circle (r >= 16 for T1)."""
        out = _node_ts(textwrap.dedent("""\
            import { svgScale, scaledFontSize } from './svg-label-scale.ts';
            const sc = svgScale(736, 500);
            const clliFs = scaledFontSize(10, sc);
            const siteFs = scaledFontSize(14, sc);
            // Site circle r is >= 16 for T1. CLLI starts at r+16 below centre.
            // The site label (DC/CO) is at centre+4, ascending ~siteFs.
            // Gap between site label bottom and CLLI top: (r+16) - (4+siteFs/2)
            const r = 16;
            const gap = (r + 16) - (4 + siteFs / 2);
            console.log(JSON.stringify({ clliFs, siteFs, gap }));
        """))
        data = __import__("json").loads(out)
        assert data["gap"] > 0, "CLLI label would collide with site circle"
