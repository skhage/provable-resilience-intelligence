"""BUG-DW-095: /conduits status region accuracy + mobile corridor labels (binding, @designer S39).

1) The persistent .filter-result-count status must not keep the previous filter's count while the
   new query is suspended, nor after the error fallback shows (WCAG 4.1.3 / 3.3.1).
2) SVG .corridor-count xN labels are hidden at <=480px; the HTML .corridor-summary caption stays.
3) Region fallback copy matches the option label 'All regions'.
Static source checks plus Node known-answer evaluation of the pure copy module (no npm on serverless).
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

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
CSS_PATH = os.path.join(UI, "styles", "lakelink-theme.css")


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


def _select_block(src, select_id):
    m = re.search(r'<select\s+id="' + re.escape(select_id) + r'"(.*?)</select>', src, re.S)
    assert m, select_id
    return m.group(1)


def _page_src():
    src = _read(ROUTE)
    i = src.index("function ConduitCoveragePage")
    return src[i:]


# ---------- (1) status copy: known answers ----------

def test_status_constants():
    d = _node_ts(STATUS_TS, "{a:M.ALL_REGIONS_LABEL, l:M.CONDUITS_LOADING_MSG, f:M.CONDUITS_FAILED_MSG}")
    assert d == {"a": "All regions", "l": "Loading conduits\u2026", "f": "Conduits failed to load."}


@pytest.mark.parametrize("args,expected", [
    ('1, "Real segmented (default)", undefined', "1 conduit matches. Coverage: Real segmented. Region: All regions."),
    ('0, "All", null', "0 conduits match. Coverage: All. Region: All regions."),
    ('1914, "Inventory only", "Central"', "1,914 conduits match. Coverage: Inventory only. Region: Central."),
    ('2, "All", ""', "2 conduits match. Coverage: All. Region: All regions."),
])
def test_result_message_known_answers(args, expected):
    assert _node_ts(STATUS_TS, "M.conduitResultMessage(" + args + ")") == expected


def test_route_uses_status_module_and_no_inline_copy():
    src = _read(ROUTE)
    assert 'from "@/lib/conduits-status"' in src
    assert "conduitResultMessage(conduits.length, FILTER_LABELS[coverage], region)" in src
    assert "all regions" not in src  # lowercase fallback removed (item 3)
    assert '<option value="">{ALL_REGIONS_LABEL}</option>' in src
    assert '"Loading conduits' not in src and '"Conduits failed' not in src


# ---------- (1) loading announced before navigate on both filters ----------

@pytest.mark.parametrize("select_id", ["coverage-filter", "region-filter"])
def test_filter_change_announces_loading_before_navigate(select_id):
    block = _select_block(_page_src(), select_id)
    m = re.search(r"onChange=\{\(e\)\s*=>\s*\{(.*?)\}\}\s*>", block, re.S)
    assert m, "onChange must be a block body"
    body = m.group(1)
    assert "announceLoading();" in body and "navigate(" in body
    assert body.index("announceLoading();") < body.index("navigate(")


def test_page_setters_map_to_constants():
    page = _page_src()
    assert "const announceLoading = () => setResultMessage(CONDUITS_LOADING_MSG);" in page
    assert "const announceFailure = () => setResultMessage(CONDUITS_FAILED_MSG);" in page


# ---------- (1) error + retry + filter-change wiring on the Conduits boundary ----------

def test_conduits_boundary_wires_error_retry_and_reset_keys():
    page = _page_src()
    m = re.search(r'<Boundary\s+label="Conduits"(.*?)>\s*<ConduitListAndMap', page, re.S)
    assert m, "Conduits boundary not found"
    attrs = m.group(1)
    assert "onError={announceFailure}" in attrs
    assert "onRetry={announceLoading}" in attrs
    assert "resetKeys={[coverage, region]}" in attrs
    # The legend boundary is unchanged: its failure must not overwrite the conduit count.
    assert re.search(r'<Boundary label="Coverage legend">', page)


def test_boundary_forwards_props_to_error_boundary():
    src = _read(ROUTE)
    b = src[src.index("function Boundary("):src.index("function ConduitCoveragePage")]
    assert "resetKeys={resetKeys}" in b
    assert re.search(r"onError=\{onError \? \(\) => onError\(\) : undefined\}", b)
    reset = re.search(r"onReset=\{\(\) => \{(.*?)\}\}", b, re.S)
    assert reset and "reset();" in reset.group(1) and "onRetry?.();" in reset.group(1)
    assert reset.group(1).index("reset();") < reset.group(1).index("onRetry?.();")


def test_status_region_stays_persistent_and_outside_boundary():
    page = _page_src()
    status = re.search(r'<p className="text-caption filter-result-count" role="status" aria-live="polite" '
                       r'aria-atomic="true">', page)
    assert status
    assert status.start() < page.index('<Boundary\n          label="Conduits"')


# ---------- (2) mobile corridor labels ----------

def _media_blocks(css, query):
    out = []
    pat = re.compile(r"@media\s*" + re.escape(query) + r"\s*\{")
    for m in pat.finditer(css):
        depth, j = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        out.append(css[m.end():j - 1])
    return out


def test_corridor_count_hidden_at_480_only():
    css = re.sub(r"/\*.*?\*/", "", _read(CSS_PATH), flags=re.S)
    blocks = _media_blocks(css, "(max-width: 480px)")
    assert any(re.search(r"\.corridor-count\s*\{\s*display:\s*none;?\s*\}", b) for b in blocks)
    base = re.search(r"(?m)^\.corridor-count\s*\{([^}]*)\}", css).group(1)
    assert "display" not in base  # labels stay at >=481px
    # The caption that carries the same information is never hidden.
    assert not re.search(r"\.corridor-summary[^{]*\{[^}]*display:\s*none", css)


def test_corridor_hide_cross_check_tinycss2():
    tinycss2 = pytest.importorskip("tinycss2")
    rules = tinycss2.parse_stylesheet(_read(CSS_PATH), skip_comments=True, skip_whitespace=True)
    hit = False
    for r in rules:
        if r.type == "at-rule" and r.lower_at_keyword == "media" and \
                tinycss2.serialize(r.prelude).strip() == "(max-width: 480px)":
            for q in tinycss2.parse_rule_list(r.content, skip_comments=True, skip_whitespace=True):
                if q.type == "qualified-rule" and tinycss2.serialize(q.prelude).strip() == ".corridor-count":
                    decls = tinycss2.parse_declaration_list(q.content, skip_comments=True, skip_whitespace=True)
                    hit |= any(d.type == "declaration" and d.lower_name == "display"
                               and tinycss2.serialize(d.value).strip() == "none" for d in decls)
    assert hit


def test_brand_no_legacy_name():
    for p in (ROUTE, STATUS_TS, __file__):
        assert "lu" + "men" not in _read(p).lower()
