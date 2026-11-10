"""BUG-DW-163 regression tests — hazard crosswalk filter focus retention and result
announcement.

Acceptance criteria (from @designer S115, P172):
  (a) The <select id="xwalk-hazard-filter"> must NOT be a descendant of the
      Suspense fallback swap — i.e. it lives above (or outside) the <Suspense>
      boundary. setHazardFilter is called inside startTransition.
  (b) A polite live region (role="status") exists outside the table and will
      contain a status string matching 'Showing N rows for <label>'.
  (c) grep lumen = 0 in the source file.
  (d) The error-fallback container has role="alert".

These tests parse the TSX source as text (no JSX transpiler on serverless).
They are designed to FAIL on HEAD 22ed333 and PASS after the fix.
"""
import re
import pathlib
import pytest

_SRC = pathlib.Path(__file__).resolve().parent.parent / (
    "apps/resilience-scorecard/src/resilience_scorecard/ui/components/hazards/"
    "hazard-crosswalk-table.tsx"
)


@pytest.fixture(scope="module")
def source() -> str:
    return _SRC.read_text(encoding="utf-8")


# ---------- (a) select is above Suspense ----------------------------------


def test_select_above_suspense(source: str):
    """The <select id='xwalk-hazard-filter'> must appear BEFORE the first
    <Suspense in the file.  If it is inside the Suspense subtree, React
    will unmount it on suspension and the user loses focus."""
    sel_pos = source.find('id="xwalk-hazard-filter"')
    sus_pos = source.find("<Suspense")
    assert sel_pos != -1, "select element not found"
    assert sus_pos != -1, "Suspense boundary not found"
    assert sel_pos < sus_pos, (
        f"select (pos {sel_pos}) must appear before <Suspense (pos {sus_pos})"
    )


def test_filter_uses_start_transition(source: str):
    """setHazardFilter (or setCommittedFilter) must be called inside
    startTransition to keep the current table mounted during the fetch."""
    assert "startTransition" in source, "startTransition not found"
    # The pattern: startTransition(() => { ...setCommitted... or setHazard... })
    assert re.search(
        r"startTransition\s*\(\s*\(\)\s*=>\s*\{?", source
    ), "startTransition call pattern not found"


def test_useTransition_imported(source: str):
    """useTransition must be imported from React."""
    assert re.search(r'import\s+\{[^}]*useTransition[^}]*\}\s+from\s+["\x27]react["\x27]', source)


# ---------- (b) live region for result announcement -----------------------


def test_live_region_exists(source: str):
    """A polite live region (role='status') must exist outside the table."""
    assert 'role="status"' in source, "No role='status' live region found"


def test_status_text_format(source: str):
    """The status text must include 'Showing' and 'rows for' so screen readers
    announce count + filter label."""
    # The format string in the useEffect
    assert re.search(r'[\x27"`]Showing\s', source), (
        "Status text 'Showing ...' pattern not found"
    )
    assert re.search(r"rows\s+for", source), (
        "Status text '... rows for ...' pattern not found"
    )


# ---------- (c) branding: zero 'lumen' hits -------------------------------


def test_no_lumen_string(source: str):
    hits = [
        (i + 1, line)
        for i, line in enumerate(source.splitlines())
        if re.search(r"lumen", line, re.IGNORECASE)
    ]
    assert hits == [], f"'lumen' found on lines: {[h[0] for h in hits]}"


# ---------- (d) error fallback has role=alert -----------------------------


def test_error_fallback_role_alert(source: str):
    """The ErrorBoundary fallback container must carry role='alert' so a load
    failure is announced to assistive technology."""
    # Find the fallbackRender region
    fb_idx = source.find("fallbackRender")
    assert fb_idx != -1, "fallbackRender not found"
    fb_region = source[fb_idx : fb_idx + 400]
    assert 'role="alert"' in fb_region, (
        "role='alert' missing from error-fallback container"
    )


# ---------- aria-busy on scroll region ------------------------------------


def test_aria_busy_on_scroll_region(source: str):
    """The scroll region must have aria-busy={isPending} so assistive
    technology knows the table is being updated."""
    assert "aria-busy={isPending}" in source, (
        "aria-busy={isPending} not found on scroll region"
    )


# ---------- requestedFilter / committedFilter split -----------------------


def test_dual_filter_state(source: str):
    """The component should maintain separate requested and committed filter
    states so the <select> reflects the user's choice immediately while the
    query uses the deferred committed value."""
    assert "requestedFilter" in source, "requestedFilter state not found"
    assert "committedFilter" in source, "committedFilter state not found"
    assert 'value={requestedFilter}' in source, (
        "select should use requestedFilter for its value"
    )
    assert 'hazardFilter={committedFilter}' in source, (
        "CrosswalkTableContent should receive committedFilter"
    )
