"""BUG-DW-128: /conduits status-region polish (binding, @designer S76).

(a) conduitResultMessage(1, ...) uses subject-verb agreement: '1 conduit matches.'
(b) The persistent page status region is the single announcer for the Conduits boundary:
    LoadingRegion announce={false} renders the skeleton without role=status, and Boundary
    announce={false} drops role=alert from the error fallback (visible text + Retry kept).
    The legend boundary and every other LoadingRegion user stay announced.
Static source checks plus Node known-answer evaluation (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
UI = os.path.join(ROOT, "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui")
ROUTE = os.path.join(UI, "routes", "conduits.tsx")
STATUS_TS = os.path.join(UI, "lib", "conduits-status.ts")
LOADING = os.path.join(UI, "components", "ui", "loading-region.tsx")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _node_ts(ts_path, expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(ts_path, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write("import * as M from './m.ts';\nconsole.log(JSON.stringify(" + expr + "));\n")
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def _boundary_src():
    src = _read(ROUTE)
    return src[src.index("function Boundary("):src.index("function ConduitCoveragePage")]


def _page_src():
    src = _read(ROUTE)
    return src[src.index("function ConduitCoveragePage"):]


def _loading_fn():
    src = _read(LOADING)
    return src[src.index("export function LoadingRegion"):src.index("export default LoadingRegion")]


# ---------- (a) copy: subject-verb agreement ----------

@pytest.mark.parametrize("n,expected_prefix", [
    (1, "1 conduit matches."),
    (0, "0 conduits match."),
    (2, "2 conduits match."),
    (1914, "1,914 conduits match."),
])
def test_result_message_subject_verb(n, expected_prefix):
    out = _node_ts(STATUS_TS, 'M.conduitResultMessage(' + str(n) + ', "All", null)')
    assert out.startswith(expected_prefix), out
    assert out == expected_prefix + " Coverage: All. Region: All regions."


def test_singular_never_reads_conduit_match():
    out = _node_ts(STATUS_TS, 'M.conduitResultMessage(1, "Real segmented (default)", "Central")')
    assert "1 conduit match." not in out
    assert out == "1 conduit matches. Coverage: Real segmented. Region: Central."


# ---------- (b) LoadingRegion announce prop ----------

def test_loading_region_announce_defaults_true():
    fn = _loading_fn()
    assert re.search(r"\{\s*label,\s*className,\s*children,\s*announce = true\s*\}", fn)
    assert "announce?: boolean;" in _read(LOADING)


def test_loading_region_silent_branch_has_no_status_role():
    fn = _loading_fn()
    m = re.search(r"if \(!announce\) \{\s*return (<div[^;]*?</div>);\s*\}", fn, re.S)
    assert m, "silent branch not found"
    silent = m.group(1)
    assert silent == "<div className={className}>{children}</div>"
    assert "role=" not in silent and "aria-live" not in silent and "sr-only" not in silent
    # The announced branch comes after the silent early return and still carries role=status.
    announced = fn[m.end():]
    assert '<div role="status" aria-live="polite" aria-atomic="true" className={className}>' in announced
    assert '<span className="sr-only">{announcement}</span>' in announced


def test_loading_region_effect_skips_timer_when_silent():
    fn = _loading_fn()
    eff = re.search(r"useEffect\(\(\) => \{(.*?)\}, \[label, announce\]\);", fn, re.S)
    assert eff, "effect must depend on [label, announce]"
    body = eff.group(1)
    assert body.lstrip().startswith("if (!announce) return;")
    # Hooks stay unconditional: useState/useEffect come before the early return.
    assert fn.index("useEffect(") < fn.index("if (!announce) {")
    assert fn.index("useState(") < fn.index("if (!announce) {")


def test_other_loading_region_users_unchanged():
    users = []
    for p in glob.glob(os.path.join(UI, "**", "*.tsx"), recursive=True):
        if os.path.abspath(p) in (os.path.abspath(LOADING), os.path.abspath(ROUTE)):
            continue
        src = _read(p)
        for tag in re.findall(r"<LoadingRegion\b[^>]*>", src):
            users.append((p, tag))
    assert len(users) >= 9, users
    for p, tag in users:
        assert "announce" not in tag, (p, tag)


# ---------- (b) Boundary announce prop ----------

def test_boundary_announce_defaults_true_and_gates_roles():
    b = _boundary_src()
    assert "announce = true," in b
    assert "announce?: boolean;" in b
    assert '<div className="data-table error-fallback" role={announce ? "alert" : undefined}>' in b
    assert 'role="alert"' not in b
    assert "<LoadingRegion label={`Loading ${label.toLowerCase()}`} announce={announce}>" in b


def test_error_fallback_keeps_visible_text_and_retry():
    b = _boundary_src()
    fb = re.search(r"fallbackRender=\{\(\{ resetErrorBoundary \}\) => \((.*?</div>)\s*\)\}", b, re.S)
    assert fb
    body = fb.group(1)
    assert "<p>Failed to load {label.toLowerCase()}</p>" in body
    btn = re.search(r"<button([^>]*)>\s*Retry\s*</button>", body)
    assert btn, "Retry button missing"
    # Retry stays a real focusable button, independent of announce.
    assert "onClick={resetErrorBoundary}" in btn.group(1)
    assert "announce" not in btn.group(1) and "disabled" not in btn.group(1) and "tabIndex" not in btn.group(1)


def test_only_conduits_boundary_is_silent():
    page = _page_src()
    m = re.search(r'<Boundary\s+label="Conduits"(.*?)>\s*<ConduitListAndMap', page, re.S)
    assert m and "announce={false}" in m.group(1)
    # Legend boundary keeps the default (announced) behaviour.
    assert '<Boundary label="Coverage legend">' in page
    assert page.count("announce={false}") == 1


def test_single_announcer_model_per_state():
    """Model the live regions present in each Conduits state; exactly one announcer each."""
    page = _page_src()
    b = _boundary_src()
    persistent = 1 if re.search(r'filter-result-count" role="status"', page) else 0
    silent = "announce={false}" in re.search(r'<Boundary\s+label="Conduits"(.*?)>', page, re.S).group(1)
    # Loading: persistent status + LoadingRegion status iff announce.
    loading_regions = persistent + (0 if silent else 1)
    # Error: persistent status + fallback alert iff announce.
    alert_gated = 'role={announce ? "alert" : undefined}' in b
    error_regions = persistent + (0 if (silent and alert_gated) else 1)
    assert loading_regions == 1
    assert error_regions == 1
    # And the page setters still produce the loading / failure messages.
    assert "onError={announceFailure}" in page and "onRetry={announceLoading}" in page


def test_brand_no_legacy_name():
    legacy = "lum" + "en"
    for p in (ROUTE, STATUS_TS, LOADING):
        assert legacy not in _read(p).lower(), p
