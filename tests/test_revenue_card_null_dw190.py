"""BUG-DW-190: Home Revenue at Risk KPI card must not disappear when the value is null (binding, @designer S138 P235).

Before: scorecard-header.tsx wrapped the card in `{summary.total_revenue_at_risk_usd != null && (...)}`, so a null
value (allowed by backend/models.py) dropped the core business KPI silently and the 9-card skeleton collapsed to 8.
Now the card always renders; the null branch shows an aria-hidden em dash, a .kpi-caption 'Not available' and
aria-label 'Revenue at Risk: not available'. The non-null branch is unchanged (flag on or off).
Static source checks (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
HEADER = os.path.join(UI, "components", "dashboard", "scorecard-header.tsx")
CSS = os.path.join(UI, "styles", "lakelink-theme.css")
MODELS = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "backend", "models.py")
BANNED = "lu" + "men"


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _content_fn():
    src = _read(HEADER)
    start = src.index("function ScorecardHeaderContent()")
    end = src.index("export function ScorecardHeader()")
    return src[start:end]


def _card():
    """The single Revenue at Risk card (opening tag through its closing div)."""
    body = _content_fn()
    start = body.index("aria-label={revenueAtRisk == null")
    start = body.rindex('<div className="kpi-card critical"', 0, start)
    end = body.index("\n      </div>\n    </div>\n  );", start)
    return body[start:end]


def _branches():
    """Split the value-region ternary into (null_branch, value_branch); the label/badge is shared."""
    card = _card()
    m = re.search(r"\{revenueAtRisk == null \? \(", card)
    assert m, "revenue value region must be a null ternary, not a conditional guard"
    rest = card[m.end():]
    sep = rest.index("\n        ) : (\n")
    return rest[:sep], rest[sep:]


def _aria():
    card = _card()
    a = card.index("aria-label={revenueAtRisk == null")
    return card[a: card.index("`}>", a) + 3]


# (a) no conditional guard that drops the card
def test_no_null_and_guard():
    body = _content_fn()
    assert "total_revenue_at_risk_usd != null &&" not in body
    assert not re.search(r"revenue\w*\s*!=\s*null\s*&&", body, re.I)
    assert not re.search(r"revenue\w*\s*&&\s*\(", body, re.I)


def test_revenue_local_normalises_undefined():
    assert "const revenueAtRisk = summary.total_revenue_at_risk_usd ?? null;" in _content_fn()


def test_backend_still_allows_none():
    # The fix exists because the API contract allows None; if this changes, revisit the null branch.
    assert "total_revenue_at_risk_usd: float | None" in _read(MODELS)


# (b) null branch content
def test_null_branch_aria_label():
    aria = _aria()
    assert '? "Revenue at Risk: not available"' in aria
    assert 'role="group"' in _card()


def test_single_card_always_rendered():
    body = _content_fn()
    assert body.count("<span>Revenue at Risk</span>") == 1
    assert body.count('<div className="kpi-label">Revenue at Risk</div>') == 1


def test_null_branch_caption():
    nb, _ = _branches()
    assert '<div className="kpi-caption">Not available</div>' in nb


def test_null_branch_em_dash_aria_hidden():
    nb, _ = _branches()
    assert '<div className="kpi-value" aria-hidden="true">{"\\u2014"}</div>' in nb


def test_card_keeps_critical_border_and_badge_for_both_states():
    card = _card()
    assert card.startswith('<div className="kpi-card critical"')
    head = card[: card.index("{revenueAtRisk == null ? (")]
    assert "<InterimBadge variant={headerVariant} />" in head
    assert '<div className="kpi-label">Revenue at Risk</div>' in head


def test_null_branch_no_number_formatting():
    nb, _ = _branches()
    assert "formatMillions" not in nb and "toFixed" not in nb and "/mo" not in nb


# (c) non-null branch unchanged (flag on or off)
def test_value_branch_unchanged():
    _, vb = _branches()
    assert (': `Revenue at Risk: $${v4Kpis ? formatMillions(revenueAtRisk) : '
            '(revenueAtRisk / 1_000_000).toFixed(1)}M${v4Kpis ? " per month" : ""}`}') in _aria()
    assert '<div className="kpi-value">' in vb
    assert "${v4Kpis ? formatMillions(revenueAtRisk) : (revenueAtRisk / 1_000_000).toFixed(1)}M" in vb
    assert '{v4Kpis && <span className="kpi-sub">/mo</span>}' in vb
    assert "Not available" not in vb and "aria-hidden" not in vb


def test_skeleton_still_nine_cards():
    assert "Array.from({ length: 9 })" in _read(HEADER)


def test_kpi_caption_solid_iron():
    css = _read(CSS)
    m = re.search(r"\n\.kpi-caption \{([^}]*)\}", css)
    assert m and "color: #4D4D4D" in m.group(1)
    assert "opacity" not in m.group(1)


# (d) branding
def test_no_banned_brand():
    assert BANNED not in _read(HEADER).lower()
    assert BANNED not in _read(__file__).lower()
