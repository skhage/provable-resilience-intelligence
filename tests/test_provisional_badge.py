"""Tests for P68-APP-PROVISIONAL-BADGE (V4-KPI-COPY-SPEC S7).

S7.7 acceptance checks:
1. Flag off or no KEPT_V3_PROVISIONAL rows: no PROVISIONAL text, UI identical.
2. Partial mode: PROVISIONAL on exactly the S7.2 surfaces. Never both INTERIM+PROVISIONAL.
3. aria-label, tooltip and page note match S7.3/S7.4 byte for byte.
4. No hard-coded KPI numbers.
5. grep lumen over ui/ returns 0; no banned words in new copy.
6. At 320px the badge wraps and the page note wraps without truncating.
"""
import json
import os
import re
import subprocess
import sys

BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "apps", "resilience-scorecard", "src", "resilience_scorecard",
)
UI_DIR = os.path.join(BASE, "ui")
PROVISIONAL_TS = os.path.join(UI_DIR, "lib", "provisional-disclosure.ts")


def _scan_dir(directory, pattern):
    hits = []
    rx = re.compile(pattern, re.IGNORECASE)
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                text = open(fpath, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append((fpath, i, line.strip()))
    return hits


def _load_provisional_module():
    text = open(PROVISIONAL_TS).read()
    text = re.sub(r"^import .+?;$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^export type .+?;$", "", text, flags=re.MULTILINE)
    text = text.replace("export ", "")
    text = re.sub(r":\s*Record<[^>]+>", "", text)
    text = re.sub(r":\s*BadgeVariant\s*\|\s*null", "", text)
    text = re.sub(r":\s*boolean", "", text)
    text = re.sub(r":\s*string\[\]", "", text)
    text = re.sub(r":\s*string", "", text)
    text = re.sub(r":\s*unknown", "", text)
    text = re.sub(r':\s*"[^"]+"\s*\|\s*"[^"]+"', "", text)
    return text


def _node_eval(js_code):
    result = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError("Node error: " + result.stderr)
    return result.stdout.strip()


def test_no_lumen_in_ui():
    hits = _scan_dir(UI_DIR, r"\blumen\b")
    assert hits == [], "'lumen' found in ui/: " + str(hits)


def test_no_banned_words_in_provisional_copy():
    text = open(PROVISIONAL_TS).read()
    banned = re.findall(r"\b(worse|declined|dropped|deteriorated|regression)\b", text, re.IGNORECASE)
    assert banned == [], "Banned word(s): " + str(banned)


def test_provisional_copy_verbatim():
    mod = _load_provisional_module()
    js = mod + '\nconsole.log(JSON.stringify({label:PROVISIONAL_LABEL,aria:PROVISIONAL_ARIA,tooltip:PROVISIONAL_TOOLTIP,info:PROVISIONAL_INFO_LABEL,note:PROVISIONAL_PAGE_NOTE,legend:PROVISIONAL_HAZARD_LEGEND}));'
    d = json.loads(_node_eval(js))
    assert d["label"] == "Provisional"
    assert d["aria"] == "Provisional figure, v3 hazard model, update pending"
    assert d["tooltip"] == (
        "Hazard exposure, risk bands and resilience scores still use the v3 hazard model. "
        "Network topology and conduits already show the v4 build. "
        "These figures will be updated after the v4 hazard re-derive passes QA."
    )
    assert d["info"] == "About provisional figures"
    assert d["note"] == (
        "Provisional: hazard exposure on this page uses the v3 hazard model. "
        "Topology and conduits use the v4 build."
    )
    assert d["legend"] == "Hazard overlay: provisional (v3 hazard model)"


def test_badge_variant_flag_off():
    mod = _load_provisional_module()
    js = mod + '\nconst s=["scorecard_header","service_table","hazards_page","actions_page","topology_hazard_legend"];const o=["resilience_score_snapshot","proactive_action"];console.log(JSON.stringify(s.map(x=>badgeVariant(false,"INTERIM",o,x))));'
    assert json.loads(_node_eval(js)) == [None, None, None, None, None]


def test_badge_variant_no_provisional_objects():
    mod = _load_provisional_module()
    js = mod + '\nconsole.log(JSON.stringify([badgeVariant(true,"INTERIM",[],"scorecard_header"),badgeVariant(true,"INTERIM",[],"hazards_page"),badgeVariant(true,"FINAL",[],"scorecard_header")]));'
    d = json.loads(_node_eval(js))
    assert d[0] == "interim"
    assert d[1] == "interim"
    assert d[2] is None


def test_badge_variant_partial_mode():
    mod = _load_provisional_module()
    js = mod + '\nconst o=["resilience_score_snapshot","hazard_span_intersection","hazard_span_proximity","proactive_action"];console.log(JSON.stringify({h:badgeVariant(true,"INTERIM",o,"scorecard_header"),t:badgeVariant(true,"INTERIM",o,"service_table"),hz:badgeVariant(true,"INTERIM",o,"hazards_page"),a:badgeVariant(true,"INTERIM",o,"actions_page"),tl:badgeVariant(true,"INTERIM",o,"topology_hazard_legend")}));'
    d = json.loads(_node_eval(js))
    assert d["h"] == "provisional"
    assert d["t"] == "provisional"
    assert d["hz"] == "provisional"
    assert d["a"] == "provisional"
    assert d["tl"] == "provisional"


def test_is_provisional_surface_mapping():
    mod = _load_provisional_module()
    js = mod + '\nconsole.log(JSON.stringify({hs:isProvisional("scorecard_header",["resilience_score_snapshot"]),hh:isProvisional("scorecard_header",["hazard_span_proximity"]),ts:isProvisional("service_table",["resilience_score_snapshot"]),hz:isProvisional("hazards_page",["hazard_span_proximity"]),aa:isProvisional("actions_page",["proactive_action"]),tl:isProvisional("topology_hazard_legend",["hazard_span_proximity"]),cx:isProvisional("conduits_page",["resilience_score_snapshot"])}));'
    d = json.loads(_node_eval(js))
    assert d["hs"] is True
    assert d["hh"] is False
    assert d["ts"] is True
    assert d["hz"] is True
    assert d["aa"] is True
    assert d["tl"] is True
    assert d["cx"] is False


def test_show_provisional_page_note():
    mod = _load_provisional_module()
    js = mod + '\nconst o=["hazard_span_proximity","proactive_action"];console.log(JSON.stringify({ho:showProvisionalPageNote(true,o,"hazards_page"),ao:showProvisionalPageNote(true,o,"actions_page"),hf:showProvisionalPageNote(false,o,"hazards_page"),he:showProvisionalPageNote(true,[],"hazards_page")}));'
    d = json.loads(_node_eval(js))
    assert d["ho"] is True
    assert d["ao"] is True
    assert d["hf"] is False
    assert d["he"] is False


def test_show_provisional_hazard_legend():
    mod = _load_provisional_module()
    js = mod + '\nconsole.log(JSON.stringify({y:showProvisionalHazardLegend(true,["hazard_span_intersection"]),n:showProvisionalHazardLegend(true,["resilience_score_snapshot"]),o:showProvisionalHazardLegend(false,["hazard_span_intersection"])}));'
    d = json.loads(_node_eval(js))
    assert d["y"] is True
    assert d["n"] is False
    assert d["o"] is False


def test_provisional_page_note_css_wrap():
    css_path = os.path.join(UI_DIR, "styles", "lakelink-theme.css")
    css = open(css_path).read()
    m = re.search(r"\.provisional-page-note\s*\{([^}]+)\}", css)
    assert m, ".provisional-page-note not found in CSS"
    block = m.group(1)
    assert "white-space" in block and "normal" in block
    assert "word-wrap" in block or "overflow-wrap" in block
    assert "14px" in block


def test_interim_badge_wrap_rule():
    css_path = os.path.join(UI_DIR, "styles", "lakelink-theme.css")
    css = open(css_path).read()
    m = re.search(r"\.kpi-label-row--interim\s*\{([^}]+)\}", css)
    assert m, ".kpi-label-row--interim not found"
    assert "flex-wrap" in m.group(1) and "wrap" in m.group(1)


def test_no_hardcoded_numbers_in_provisional():
    text = open(PROVISIONAL_TS).read()
    for n in ["61.5", "848", "2932", "2,932", "48.4"]:
        assert n not in text, "Hard-coded " + n + " in provisional-disclosure.ts"


def test_never_both_badges():
    mod = _load_provisional_module()
    js = mod + '\nconsole.log(JSON.stringify(["scorecard_header","service_table"].map(s=>badgeVariant(true,"INTERIM",["resilience_score_snapshot"],s)).every(r=>r==="provisional")));'
    assert _node_eval(js) == "true"


def test_interim_badge_has_variant_prop():
    path = os.path.join(UI_DIR, "components", "ui", "interim-badge.tsx")
    text = open(path).read()
    assert "variant" in text
    assert "provisional" in text.lower()
    assert "COPY[variant]" in text


def test_cutover_manifest_model():
    sys.path.insert(0, os.path.join(BASE, ".."))
    try:
        from resilience_scorecard.backend.models import CutoverManifestOut
        m = CutoverManifestOut()
        assert m.cutover_mode is None
        assert m.provisional_objects == []
        m2 = CutoverManifestOut(cutover_mode="PARTIAL", provisional_objects=["resilience_score_snapshot"])
        assert m2.cutover_mode == "PARTIAL"
        assert m2.provisional_objects == ["resilience_score_snapshot"]
    finally:
        sys.path.pop(0)
