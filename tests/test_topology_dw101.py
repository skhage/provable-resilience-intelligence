"""BUG-DW-101: path-trace stats shared-SRLG qualifier uses the aria-hidden / sr-only split (spec 6.3).

The visible '(metro/access)' must never reach the accessibility tree as text; speech says
'metro and access'. Mirrors the conduit panel SRLG heading pattern.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.path.join(
    HERE, "..", "apps", "resilience-scorecard", "src", "resilience_scorecard", "ui", "routes", "topology.tsx"
)


def _src():
    with open(TOPO, encoding="utf-8") as f:
        return f.read()


def _stats_block(src):
    m = re.search(r'<span className="path-trace-stats">(.*?)\n\s*</span>\n', src, re.S)
    assert m, "path-trace-stats span not found"
    # cut at the sharedConduitStat line so the block covers only the SRLG clause region
    return m.group(1)


def test_no_inline_metro_access_in_template_literal():
    block = _stats_block(_src())
    # The old bug: METRO_ACCESS interpolated inside a text template literal
    assert "shared SRLGs${" not in block
    for lit in re.findall(r"`[^`]*`", block):
        if "aria-hidden" in lit:
            continue
        assert "${METRO_ACCESS}" not in lit or lit == "`\\u00A0${METRO_ACCESS}`", lit


def test_qualifier_split_aria_hidden_and_sr_only():
    block = _stats_block(_src())
    assert '<span aria-hidden="true">{`\\u00A0${METRO_ACCESS}`}</span>' in block
    assert '<span className="sr-only">{` ${METRO_ACCESS_SPOKEN}`}</span>' in block


def test_every_metro_access_render_is_aria_hidden():
    """File-wide: each JSX render of ${METRO_ACCESS} sits inside an aria-hidden span."""
    src = _src()
    for m in re.finditer(r"\$\{METRO_ACCESS\}", src):
        line_start = src.rfind("\n", 0, m.start()) + 1
        line = src[line_start: src.find("\n", m.end())]
        assert 'aria-hidden="true"' in line, line.strip()


def test_qualifier_only_when_partial_and_count_preserved():
    block = _stats_block(_src())
    assert 'bbCoverage === "partial" && (' in block
    assert "{` · ${formatCount(diversity.shared_srlg_count)} shared SRLGs`}" in block
    # v3 (no coverage flag) branch unchanged
    assert "` · ${diversity.shared_srlg_count} shared SRLGs`" in block


def test_spoken_form_constant():
    lib = os.path.join(os.path.dirname(TOPO), "..", "lib", "bb-srlg-disclosure.ts")
    with open(lib, encoding="utf-8") as f:
        t = f.read()
    assert 'export const METRO_ACCESS_SPOKEN = "metro and access";' in t
    assert "/" not in re.search(r'METRO_ACCESS_SPOKEN = "([^"]*)"', t).group(1)
