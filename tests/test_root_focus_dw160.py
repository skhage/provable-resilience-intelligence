"""BUG-DW-160: root layout focus management (WCAG 2.4.3 Focus Order).

(a) Escape on the open hamburger nav returns focus to the hamburger when focus was in
    the nav or on the button, instead of dropping it to <body>.
(b) A client-side route change moves focus to <main id=main-content> (skipped on first
    mount and when only the query string changes).
Behavioral checks extract the real handler/effect source from routes/__root.tsx and run
it in Node against a fake DOM. Pure helpers in ui/lib/root-focus.ts are run in Node too.
Project: Lakelink Fiber - Provable Resilience Intelligence
"""

import json
import os
import re
import shutil
import subprocess

import pytest

UI = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "apps", "resilience-scorecard", "src",
    "resilience_scorecard", "ui"))
BACKEND = os.path.join(os.path.dirname(UI), "backend")
_LIB = os.path.join(UI, "lib", "root-focus.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _root():
    return _read("routes", "__root.tsx")


def _block(src, start):
    """Source from `start` (which ends with '{') up to its matching close brace."""
    i = src.index(start)
    j = i + len(start) - 1
    assert src[j] == "{"
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError(start)


def _run(js):
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    return _run(js)


# --- pure helpers -------------------------------------------------------------

@needs_node
def test_dw160_escape_restore_decision():
    out = _node("""
const btn = {n: 'btn'}; const link = {n: 'link'}; const other = {n: 'other'};
const nav = { contains: (x) => x === link };
out = [
  m.navEscapeShouldRestoreFocus(link, nav, btn),
  m.navEscapeShouldRestoreFocus(btn, nav, btn),
  m.navEscapeShouldRestoreFocus(other, nav, btn),
  m.navEscapeShouldRestoreFocus(null, nav, btn),
  m.navEscapeShouldRestoreFocus(link, null, btn),
  m.navEscapeShouldRestoreFocus(btn, null, null),
];""")
    assert out == [True, True, False, False, False, False]


@needs_node
def test_dw160_route_change_decision():
    out = _node("""out = [
  m.shouldFocusMainOnRouteChange(null, '/'),
  m.shouldFocusMainOnRouteChange('/', '/'),
  m.shouldFocusMainOnRouteChange('/', '/actions'),
  m.shouldFocusMainOnRouteChange('/actions', '/topology'),
  m.navLinkClickShouldFocusMain('/actions', '/actions'),
  m.navLinkClickShouldFocusMain('/', '/actions'),
  m.MAIN_CONTENT_ID,
];""")
    assert out == [False, False, True, True, True, False, "main-content"]


@needs_node
def test_dw160_focus_main_content_helper():
    out = _node("""
const log = [];
const main = { focus() { log.push('main'); } };
const doc = { getElementById: (id) => (id === 'main-content' ? main : null) };
const empty = { getElementById: () => null };
out = [m.focusMainContent(doc), m.focusMainContent(empty), log];""")
    assert out == [True, False, ["main"]]


# --- (a) Escape handler: real source from __root.tsx --------------------------

def _escape_js():
    src = _root()
    effect_at = src.index("// BUG-DW-029")
    h = _block(src[effect_at:], "const handleEscape = (e: KeyboardEvent) => {")
    return h.replace("(e: KeyboardEvent)", "(e)")


def _simulate_escape(focus, key="Escape"):
    handler = _escape_js()
    js = f"""
import * as m from {json.dumps('file://' + _LIB)};
const navEscapeShouldRestoreFocus = m.navEscapeShouldRestoreFocus;
const log = {{ setNavOpen: [], focused: [], order: [] }};
const mk = (name) => ({{ name, focus() {{ log.focused.push(name); log.order.push('focus:' + name);
  globalThis.document.activeElement = this; }} }});
const hamburger = mk('hamburger');
const link = mk('link');
const outside = mk('outside');
const nav = {{ contains: (x) => x === link }};
const hamburgerRef = {{ current: hamburger }};
const navRef = {{ current: nav }};
const setNavOpen = (v) => {{ log.setNavOpen.push(v); log.order.push('setNavOpen:' + v);
  // closing hides the nav links: a focused link loses focus to body
  if (v === false && globalThis.document.activeElement === link)
    globalThis.document.activeElement = {{ name: 'body' }}; }};
const F = {json.dumps(focus)};
globalThis.document = {{ activeElement: F === 'link' ? link : F === 'hamburger' ? hamburger
  : F === 'outside' ? outside : {{ name: 'body' }} }};
{handler};
handleEscape({{ key: {json.dumps(key)} }});
log.final = globalThis.document.activeElement.name;
process.stdout.write(JSON.stringify(log));
"""
    return _run(js)


@needs_node
def test_dw160_escape_from_nav_link_returns_focus_to_hamburger():
    log = _simulate_escape("link")
    assert log["setNavOpen"] == [False]
    assert log["focused"] == ["hamburger"]
    assert log["final"] == "hamburger"


@needs_node
def test_dw160_escape_on_hamburger_keeps_focus_there():
    log = _simulate_escape("hamburger")
    assert log["setNavOpen"] == [False]
    assert log["final"] == "hamburger"


@needs_node
def test_dw160_escape_with_focus_elsewhere_does_not_steal_focus():
    log = _simulate_escape("outside")
    assert log["setNavOpen"] == [False]  # DW-029: Escape still closes the nav
    assert log["focused"] == []
    assert log["final"] == "outside"


@needs_node
def test_dw029_non_escape_key_is_ignored():
    log = _simulate_escape("link", key="Enter")
    assert log["setNavOpen"] == [] and log["focused"] == []


def test_dw160_escape_decision_read_before_close():
    h = _escape_js()
    assert h.index("navEscapeShouldRestoreFocus(") < h.index("setNavOpen(false)")
    assert h.index("setNavOpen(false)") < h.index("hamburgerRef.current?.focus()")


def test_dw029_escape_listener_still_gated_on_nav_open():
    src = _root()
    eff = src[src.index("// BUG-DW-029"):]
    eff = eff[:eff.index("}, [navOpen]);")]
    assert "if (!navOpen) return;" in eff
    assert 'document.addEventListener("keydown", handleEscape)' in eff
    assert 'document.removeEventListener("keydown", handleEscape)' in eff


def test_dw160_refs_attached_to_hamburger_and_nav():
    src = _root()
    # attributes contain arrow functions (`=>`), so the tag ends at a line holding only `>`
    btn = re.search(r"<button\b.*?\n\s*>", src, flags=re.S).group(0)
    assert "ref={hamburgerRef}" in btn and 'className="nav-hamburger"' in btn
    nav = re.search(r"<nav\b.*?\n\s*>", src, flags=re.S).group(0)
    assert "ref={navRef}" in nav and 'id="main-nav"' in nav


# --- (b) route-change effect: real source from __root.tsx ---------------------

def _route_effect_body():
    src = _root()
    i = src.index("const prev = prevPathRef.current;")
    j = src.index("}, [pathname]);", i)
    return src[i:j]


def _simulate_routes(paths):
    body = _route_effect_body()
    js = f"""
import * as m from {json.dumps('file://' + _LIB)};
const shouldFocusMainOnRouteChange = m.shouldFocusMainOnRouteChange;
const focusMainContent = m.focusMainContent;
const log = {{ focused: [] }};
const frames = new Map(); let nextId = 1;
globalThis.requestAnimationFrame = (fn) => {{ const id = nextId++; frames.set(id, fn); return id; }};
globalThis.cancelAnimationFrame = (id) => {{ frames.delete(id); }};
const flush = () => {{ const fs = [...frames.values()]; frames.clear(); fs.forEach((f) => f()); }};
const main = {{ focus() {{ log.focused.push(currentPath); }} }};
globalThis.document = {{ getElementById: (id) => (id === 'main-content' ? main : null) }};
const prevPathRef = {{ current: null }};
let currentPath = null;
function effect(pathname) {{ {body} }}
let cleanup;
for (const p of {json.dumps(paths)}) {{
  if (p === '<strict-remount>') {{ if (cleanup) cleanup(); cleanup = effect(currentPath); continue; }}
  if (cleanup) cleanup();
  currentPath = p;
  cleanup = effect(p);
  flush();
}}
process.stdout.write(JSON.stringify(log));
"""
    return _run(js)


@needs_node
def test_dw160_no_focus_move_on_first_mount():
    assert _simulate_routes(["/"])["focused"] == []


@needs_node
def test_dw160_no_focus_move_on_strict_mode_double_mount():
    assert _simulate_routes(["/actions", "<strict-remount>"])["focused"] == []


@needs_node
def test_dw160_route_change_focuses_main():
    log = _simulate_routes(["/", "/actions", "/topology"])
    assert log["focused"] == ["/actions", "/topology"]


@needs_node
def test_dw160_same_pathname_rerender_does_not_move_focus():
    # e.g. /topology?service=X -> /topology?service=Y keeps the pathname
    log = _simulate_routes(["/", "/topology", "/topology"])
    assert log["focused"] == ["/topology"]


def test_dw160_route_effect_uses_raf_and_cleanup():
    body = _route_effect_body()
    assert "requestAnimationFrame(() => focusMainContent(document))" in body
    assert "return () => cancelAnimationFrame(frame);" in body
    src = _root()
    assert "const pathname = routerState.location.pathname;" in src
    assert "const prevPathRef = useRef<string | null>(null);" in src


# --- nav link clicks ----------------------------------------------------------

def test_dw160_every_nav_link_uses_focus_aware_close():
    src = _root()
    nav = src[src.index('<nav'):src.index('</nav>')]
    links = re.findall(r"<Link\b(.*?)\n\s*>", nav, flags=re.S)
    assert len(links) == 5
    for attrs in links:
        to = re.search(r'to="([^"]+)"', attrs).group(1)
        assert f'onClick={{() => onNavLinkClick("{to}")}}' in attrs, to
    assert "setNavOpen(false)}" not in nav


def test_dw160_nav_link_click_handler_shape():
    src = _root()
    h = _block(src, "const onNavLinkClick = (to: string) => {")
    assert "navOpen && navLinkClickShouldFocusMain(to, pathname)" in h
    assert h.index("navLinkClickShouldFocusMain(") < h.index("setNavOpen(false)")
    assert "requestAnimationFrame(() => focusMainContent(document))" in h


# --- regressions + brand ------------------------------------------------------

def test_dw149_main_target_unchanged():
    src = _root()
    m = re.search(r"<main\b[^>]*>", src).group(0)
    assert 'id="main-content"' in m and "tabIndex={-1}" in m
    css = _read("styles", "lakelink-theme.css")
    assert re.search(r"#main-content:focus\s*\{[^}]*outline:\s*none", css)


def test_dw160_brand_no_old_name():
    for base in (UI, BACKEND):
        for dp, _, fs in os.walk(base):
            if "node_modules" in dp or "__pycache__" in dp:
                continue
            for f in fs:
                if f.endswith((".ts", ".tsx", ".css", ".py")):
                    with open(os.path.join(dp, f), encoding="utf-8", errors="ignore") as fh:
                        assert "lumen" not in fh.read().lower(), os.path.join(dp, f)
