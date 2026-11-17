"""BUG-DW-178: error-boundary Retry must not drop focus to <body> (WCAG 2.4.3, 3.2.1).

All 9 react-error-boundary fallbacks now use the shared components/ui/retry-boundary.tsx,
which focuses the new Retry button after a repeat failure, or the boundary container after a
successful retry, and never moves focus on a first error or a resetKeys-driven reset.

Negative check: these tests fail on f6074e6 (9 bare onClick={resetErrorBoundary}, no shared component).
"""
import os
import re
from pathlib import Path

import pytest

REPO = Path(os.environ.get("PRI_REPO", Path(__file__).resolve().parents[1]))
UI = REPO / "apps/resilience-scorecard/src/resilience_scorecard/ui"
COMPONENT = UI / "components/ui/retry-boundary.tsx"
CSS = UI / "styles/lakelink-theme.css"

SITES = {
    "routes/conduits.tsx": 1,
    "components/actions/action-queue-table.tsx": 1,
    "components/dashboard/product-catalog.tsx": 1,
    "components/dashboard/scorecard-header.tsx": 1,
    "components/dashboard/service-table.tsx": 1,
    "components/hazards/hazard-crosswalk-kpis.tsx": 1,
    "components/hazards/hazard-crosswalk-table.tsx": 1,
    "components/hazards/hazard-kpi-row.tsx": 1,
    "components/hazards/hazard-summary-table.tsx": 1,
}


def strip_comments(src: str) -> str:
    src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:\w\"'])//[^\n]*", "", src)


def read(rel: str) -> str:
    return strip_comments((UI / rel).read_text())


@pytest.mark.parametrize("rel,count", sorted(SITES.items()))
def test_site_uses_shared_retry_boundary(rel, count):
    src = read(rel)
    assert 'from "@/components/ui/retry-boundary"' in src
    assert len(re.findall(r"<RetryBoundary\b", src)) == count
    assert "{retryButton}" in src
    # The shared component owns ErrorBoundary + Suspense for these sites.
    assert "react-error-boundary" not in src
    assert "<ErrorBoundary" not in src


def test_no_bare_reset_error_boundary_anywhere():
    offenders = []
    for p in UI.rglob("*.tsx"):
        if p == COMPONENT:
            continue
        if re.search(r"onClick=\{resetErrorBoundary\}", strip_comments(p.read_text())):
            offenders.append(str(p.relative_to(UI)))
    assert offenders == []


def test_component_retry_pending_guard():
    src = strip_comments(COMPONENT.read_text())
    assert 'tabIndex={-1} className="retry-focus-target"' in src
    assert "retryPendingRef = useRef(false)" in src
    # BUG-QA-171: decisions moved to lib/retry-focus.ts (behaviour-tested in test_retry_focus_qa171.py).
    # Pending is set only by the user's Retry click, then the boundary resets.
    assert re.search(r"onClick=\{\(\) => \{\s*markRetryPending\(retryPendingRef\);\s*onRetry\(\);", src)
    # resetKeys resets (filter changes) never steal focus.
    assert "handleBoundaryReset(retryPendingRef, details.reason)" in src
    # Repeat failure: new Retry button focuses itself only when pending.
    assert "focusRetryButtonIfPending(retryPendingRef, buttonRef.current, containerRef.current, document)" in src
    # Success: probe inside Suspense focuses the container on the next frame.
    assert re.search(r"if \(!shouldScheduleRetryFocus\(retryPendingRef\)\) return;", src)
    assert "requestAnimationFrame" in src and "cancelAnimationFrame" in src
    assert "focusContainerAfterRetry(retryPendingRef, containerRef.current, document)" in src
    assert re.search(r"<Suspense fallback=\{loading\}>\s*<RetryFocusProbe", src)
    # No new live regions.
    assert "role=" not in src and "aria-live" not in src
    assert 'className="btn btn-outline"' in src and ">\n      Retry\n    </button>" in src


def test_roles_and_copy_preserved():
    assert 'role={announce ? "alert" : undefined}' in read("routes/conduits.tsx")
    for rel, copy in [
        ("components/dashboard/product-catalog.tsx", "Failed to load product catalog"),
        ("components/dashboard/scorecard-header.tsx", "Failed to load summary"),
        ("components/dashboard/service-table.tsx", "Failed to load service scores"),
        ("components/hazards/hazard-crosswalk-kpis.tsx", "Failed to load crosswalk summary"),
        ("components/hazards/hazard-crosswalk-table.tsx", "Failed to load crosswalk data"),
        ("components/hazards/hazard-kpi-row.tsx", "Failed to load hazard summary"),
        ("components/hazards/hazard-summary-table.tsx", "Failed to load hazard data"),
        ("components/actions/action-queue-table.tsx", "{ACTION_QUEUE_LOAD_ERROR}"),
    ]:
        src = read(rel)
        assert copy in src, rel
        assert 'role="alert"' in src, rel


def test_focus_ring_css():
    css = CSS.read_text()
    assert re.search(r"\.retry-focus-target:focus-visible \{\s*outline: 2px solid var\(--lf-dark-teal\);", css)
    assert ".retry-focus-target:focus-visible { outline-color: Highlight; }" in css


def test_lakelink_copy_only():
    assert "lumen" not in COMPONENT.read_text().lower()
