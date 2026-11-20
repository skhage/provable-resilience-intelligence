"""P297-APP-NPM-ERESOLVE-FIX: the app's npm install must resolve with strict peer deps,
and tsc --noEmit must be clean.

Root cause (P292 preflight at a600107): @tanstack/router-plugin ^1.95.0 floated to
1.169.0, which peer-requires vite >=6.0.0 and @tanstack/react-router ^1.170.46, while
package.json pinned vite ^5.4.11. Databricks Apps runs `npm install` at deploy, so the
first deploy would have failed with ERESOLVE. The fix moves to vite 6 and pins the router
pair with tilde ranges so a future router-plugin release cannot float past the tested
peer set. No .npmrc legacy-peer-deps workaround.

The floating router upgrade also made 10 tsc errors visible (search params now required
on links, EscapeNode vs HTMLElement, RefObject | null, PathHop.site_a_region). The
source-shape tests below lock those fixes; test_tsc_clean runs the real compiler when
node_modules exists (CI or a /tmp build copy) and is skipped otherwise.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "apps" / "resilience-scorecard"
_PKG = _APP / "package.json"
_UI = _APP / "src" / "resilience_scorecard" / "ui"


def _pkg() -> dict:
    return json.loads(_PKG.read_text())


def _all_deps() -> dict[str, str]:
    p = _pkg()
    return {**p.get("dependencies", {}), **p.get("devDependencies", {})}


def _parse(rng: str) -> tuple[str, tuple[int, int, int]]:
    m = re.fullmatch(r"([~^]?)(\d+)\.(\d+)\.(\d+)", rng.strip())
    assert m, f"unsupported range {rng!r}; use ^x.y.z or ~x.y.z"
    return m.group(1), (int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _max_major(rng: str) -> int:
    op, (maj, _mi, _pa) = _parse(rng)
    return maj  # ^ and ~ both stay inside the major for maj >= 1


# --- dependency ranges -------------------------------------------------------


def test_vite_is_v6_for_router_plugin_peer():
    deps = _all_deps()
    _op, (maj, _mi, _pa) = _parse(deps["vite"])
    assert maj >= 6, "router-plugin 1.169 peer-requires vite >=6.0.0 (ERESOLVE on vite 5)"


def test_vite_range_stays_on_major_6():
    # vite 7 is untested here (plugin-react 4 allows it, but the build was verified on 6.4.6)
    assert _max_major(_all_deps()["vite"]) == 6


def test_router_pair_pinned_with_tilde():
    deps = _all_deps()
    for name in ("@tanstack/router-plugin", "@tanstack/react-router"):
        op, _v = _parse(deps[name])
        assert op == "~", f"{name} must use a ~ range so new minors cannot change peer reqs"


def test_react_router_satisfies_router_plugin_peer():
    _op, v = _parse(_all_deps()["@tanstack/react-router"])
    assert v >= (1, 170, 46), "router-plugin 1.169.0 peer-requires @tanstack/react-router ^1.170.46"


def test_plugin_react_allows_vite_6():
    _op, (maj, _mi, _pa) = _parse(_all_deps()["@vitejs/plugin-react"])
    assert maj == 4  # 4.x peer: vite ^4.2 || ^5 || ^6 || ^7


def test_types_node_present_for_vite_config():
    # vite.config.ts imports node:url / node:path
    assert "@types/node" in _pkg().get("devDependencies", {})


def test_no_legacy_peer_deps_workaround():
    npmrc = _APP / ".npmrc"
    if npmrc.exists():
        txt = npmrc.read_text()
        assert "legacy-peer-deps" not in txt and "force" not in txt


def test_build_script_unchanged():
    assert _pkg()["scripts"]["build"] == "vite build"


# --- tsc fixes (source shape) -----------------------------------------------


def test_topology_search_params_optional():
    src = (_UI / "routes" / "topology.tsx").read_text()
    assert re.search(r"interface TopologySearch \{\s*service\?: string;\s*hazard\?: string;\s*\}", src)
    assert "): TopologySearch =>" in src
    # no unchecked casts of URL params
    assert "search.service as string" not in src and "search.hazard as string" not in src
    assert 'typeof search.service === "string"' in src


def test_conduits_search_params_optional_with_default():
    src = (_UI / "routes" / "conduits.tsx").read_text()
    assert re.search(r"interface ConduitsSearch \{\s*coverage\?: CoverageFilter;\s*region\?: string;\s*\}", src)
    assert "): ConduitsSearch =>" in src
    assert 'const DEFAULT_COVERAGE: CoverageFilter = "REAL_SEGMENTED";' in src
    assert "const { coverage = DEFAULT_COVERAGE, region } = useSearch(" in src


def test_route_files_keep_single_export():
    # TanStack code-splitting: the search types must not add a second export
    for name in ("topology.tsx", "conduits.tsx"):
        src = (_UI / "routes" / name).read_text()
        assert re.findall(r"(?m)^export ", src) == ["export "], name


def test_escape_node_uses_method_syntax():
    src = (_UI / "lib" / "topology-data-state.ts").read_text()
    block = src[src.index("export interface EscapeNode {"):]
    block = block[: block.index("}") + 1]
    assert "contains?(other: unknown): boolean;" in block
    assert "=>" not in block, "property-function syntax rejects HTMLElement under strictFunctionTypes"


def test_path_hop_has_site_a_region():
    src = (_UI / "routes" / "topology.tsx").read_text()
    block = src[src.index("interface PathHop {"):]
    block = block[: block.index("\n}")]
    assert "site_a_region?: string | null;" in block
    models = (_APP / "src" / "resilience_scorecard" / "backend" / "models.py").read_text()
    assert "site_a_region: str | None" in models


def test_banner_ref_type_assignable_to_div_ref():
    src = (_UI / "routes" / "topology.tsx").read_text()
    assert "bannerRef?: React.RefObject<HTMLDivElement>;" in src
    # Hook params (e.g. the focus-trap helper's `ref:` arg) may keep the | null form; only
    # the prop passed to <div ref={...}> must not.
    assert "bannerRef?: React.RefObject<HTMLDivElement | null>" not in src


# --- real compiler (only where deps are installed) --------------------------


@pytest.mark.skipif(
    not (_APP / "node_modules" / ".bin" / "tsc").exists() or shutil.which("node") is None,
    reason="node_modules not installed (run npm install in a build copy)",
)
def test_tsc_clean():
    r = subprocess.run(
        [str(_APP / "node_modules" / ".bin" / "tsc"), "--noEmit", "-p", "tsconfig.json"],
        cwd=_APP,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
