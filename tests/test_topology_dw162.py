"""BUG-DW-162: topology side-panel icons are Lucide (aria-hidden) with a visible hazard type label.

WCAG 1.1.1 / 1.3.1 / 1.4.11 (designer FINDING-08). Source-level checks on routes/topology.tsx,
components/hazards/hazard-type-cell.tsx and styles/lakelink-theme.css.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import os
import re

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _strip_comments(src):
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _panels():
    """SiteDetailPanel + EdgeDetailPanel source (up to the next section separator)."""
    src = _read("routes", "topology.tsx")
    start = src.index("function SiteDetailPanel(")
    edge = src.index("function EdgeDetailPanel(")
    end = src.index("// -------", edge)
    return _strip_comments(src[start:end])


def _css():
    return _read("styles", "lakelink-theme.css")


def test_panel_jsx_has_no_emoji():
    # Glyphs inside an aria-hidden span are decorative and allowed (e.g. the close button X).
    visible = re.sub(r'<span aria-hidden="true">[^<]*</span>', "", _panels())
    hits = EMOJI.findall(visible)
    assert hits == [], f"emoji left in side-panel JSX: {hits}"


def test_panel_has_no_emoji_fallback():
    assert '?? "\u26a0' not in _panels()
    assert "SRLG_ICONS[" not in _panels()
    assert "HAZARD_ICONS[" not in _panels()


def test_hazard_rows_use_hazard_type_cell_with_alert_triangle_fallback():
    p = _panels()
    assert "<HazardTypeCell type={h.hazard_type} fallbackIcon={AlertTriangle} />" in p
    src = _read("routes", "topology.tsx")
    assert re.search(r'import \{ HazardTypeCell \} from "@/components/hazards/hazard-type-cell"', src)


def test_hazard_type_cell_renders_visible_label_and_hidden_icon():
    cell = _read("components", "hazards", "hazard-type-cell.tsx")
    assert '"aria-hidden": true' in cell
    assert "fallbackIcon?: LucideIcon" in cell
    assert "HAZARD_ICONS[type] ?? fallbackIcon ?? HelpCircle" in cell
    # visible text label is rendered next to the icon
    assert re.search(r"/>\s*\{label\}", cell)


def test_srlg_rows_use_lucide_icon_component():
    p = _panels()
    assert "<SrlgPanelIcon type={s.srlg_type} />" in p
    src = _read("routes", "topology.tsx")
    m = re.search(r"const SRLG_PANEL_ICONS: Record<string, LucideIcon> = \{(.*?)\};", src, re.S)
    assert m, "SRLG_PANEL_ICONS map missing"
    keys = set(re.findall(r"(\w+):", m.group(1)))
    labels = re.search(r"const SRLG_LABELS: Record<string, string> = \{(.*?)\};", src, re.S)
    assert keys == set(re.findall(r"(\w+):", labels.group(1)))
    assert "SRLG_PANEL_ICONS[type] ?? AlertTriangle" in src
    props = re.search(r"const PANEL_ICON_PROPS = \{(.*?)\}", src).group(1)
    assert "size: 16" in props and "strokeWidth: 1.5" in props and '"aria-hidden": true' in props


def test_lucide_imports_are_named_imports():
    src = _read("routes", "topology.tsx")
    imp = re.search(r'import \{([^}]*)\} from "lucide-react";', src).group(1)
    names = {n.strip() for n in imp.split(",")}
    assert {"AlertTriangle", "Building2", "Landmark", "Link2", "Mountain", "TrainFront", "Zap"} <= names
    # Lucide 'Link' would shadow the router Link; panel uses Link2
    assert "Link" not in names


def test_panel_icon_color_iron_and_forced_colors():
    css = _css()
    base = re.search(r"\.panel-conduit-item \.panel-type-icon,\s*\.panel-conduit-item \.hazard-type-cell svg \{([^}]*)\}", css)
    assert base and "color: var(--lf-iron)" in base.group(1)
    fc = re.search(r"@media \(forced-colors: active\) \{\s*\.panel-conduit-item \.panel-type-icon,\s*\.panel-conduit-item \.hazard-type-cell svg \{\s*color: CanvasText;", css)
    assert fc, "forced-colors CanvasText rule missing for panel icons"


def _lum(hexc):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def test_iron_contrast_meets_non_text_minimum():
    iron = _lum("#4D4D4D")
    for bg in ("#FFFFFF", "#E8E8E8"):
        ratio = (_lum(bg) + 0.05) / (iron + 0.05)
        assert ratio >= 3.0, (bg, ratio)


def test_no_lumen_in_touched_files():
    for parts in (("routes", "topology.tsx"), ("components", "hazards", "hazard-type-cell.tsx"),
                  ("styles", "lakelink-theme.css")):
        assert "lumen" not in _read(*parts).lower(), parts
