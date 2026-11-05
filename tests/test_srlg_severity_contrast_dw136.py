"""BUG-DW-136: SRLG severity badge text meets WCAG 2.1 1.4.3 (>=4.5:1, 12px/700 is not large text).

Ruling: low badge colour #6B7280 -> #4B5563 on #F3F4F6. Critical/high/medium rules unchanged.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1]
       / "apps/resilience-scorecard/src/resilience_scorecard/ui/styles/lakelink-theme.css")

EXPECTED = {
    "critical": ("#FEE2E2", "#991B1B"),
    "high": ("#FEF3C7", "#92400E"),
    "medium": ("#E8E8E8", "#4D4D4D"),
    "low": ("#F3F4F6", "#4B5563"),
}


def _strip_comments(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def _rules(severity):
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    sel = re.escape(f'.srlg-severity-badge[data-severity="{severity}"]')
    return re.findall(r"(?m)^" + sel + r"\s*\{([^}]*)\}", css)


def _decl(body, prop):
    m = re.findall(r"(?:^|;|\s)" + prop + r"\s*:\s*([^;]+);", body)
    assert len(m) == 1, (prop, body)
    return m[0].strip().upper()


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_helper_known_answers():
    assert round(_contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(_contrast("#6B7280", "#F3F4F6"), 2) == 4.39  # designer's measured failing value


def test_low_badge_colour_is_4b5563():
    rules = _rules("low")
    assert len(rules) == 1
    assert _decl(rules[0], "color") == "#4B5563"
    assert _decl(rules[0], "background") == "#F3F4F6"


@pytest.mark.parametrize("severity", sorted(EXPECTED))
def test_every_severity_badge_meets_aa_normal_text(severity):
    (body,) = _rules(severity)
    bg, fg = _decl(body, "background"), _decl(body, "color")
    assert (bg, fg) == EXPECTED[severity]
    assert _contrast(fg, bg) >= 4.5, (severity, fg, bg, _contrast(fg, bg))


def test_base_badge_typography_unchanged():
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    (body,) = re.findall(r"(?m)^\.srlg-severity-badge\s*\{([^}]*)\}", css)
    assert _decl(body, "font-size") == "12PX"
    assert _decl(body, "font-weight") == "700"
    assert _decl(body, "letter-spacing") == "0.5PX"
