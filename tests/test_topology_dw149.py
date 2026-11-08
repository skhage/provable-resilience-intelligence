"""BUG-DW-149: one Escape has exactly one effect on /topology; skip-link target is focusable.

Behavioral checks extract the real keydown handlers from routes/topology.tsx (useFocusTrap
and the page-level shortcut handler), strip their few type annotations, and run them in
Node against a fake DOM that dispatches to listeners in registration order. Listeners on
the panel (target phase) run before listeners on document (bubble), as in a browser.
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
_LIB = os.path.join(UI, "lib", "topology-data-state.ts")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def _block(src, start):
    """Source of the arrow function starting at `start`, up to its matching close brace."""
    i = src.index(start)
    j = src.index("{", i + len(start) - 1)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError(start)


def _strip_types(js):
    js = js.replace("(e: KeyboardEvent)", "(e)")
    js = js.replace(" as HTMLElement | null", "")
    js = js.replace("<HTMLElement>", "")
    return js


def _parts(src):
    """(trap handler js, trap has panel listener, page handler js) from topology.tsx source."""
    hook = _block(src, "function useFocusTrap(")
    trap = _strip_types(_block(hook, "const handleKeyDown = (e: KeyboardEvent) => {"))
    on_panel = 'el.addEventListener("keydown", handleKeyDown)' in hook
    on_doc = 'document.addEventListener("keydown", handleKeyDown)' in hook
    i = src.index("// Keyboard shortcuts (\u00a77.1)")
    page = _strip_types(_block(src[i:], "const handler = (e: KeyboardEvent) => {"))
    return trap, on_panel, on_doc, page


def _simulate(src, scenario):
    trap, on_panel, on_doc, page = _parts(src)
    js = f"""
import * as m from {json.dumps('file://' + _LIB)};
const S = {json.dumps(scenario)};
const log = {{ onClose: 0, setSelectedConduit: [], setSelectedSite: [], setSelectedRegion: [],
  overlays: 0, focused: [] }};
const panel = S.panel ? {{
  id: 'panel', tagName: 'DIV',
  getAttribute: (n) => (n === 'aria-modal' ? (S.panel.modal ? 'true' : null) : null),
  contains: (t) => !!t && t.inPanel === true,
  closest: (sel) => (sel.includes('dialog') ? panel : null),
  querySelectorAll: () => kids,
  querySelector: () => kids[0],
}} : null;
const mk = (name, inPanel) => ({{ name, inPanel, tagName: 'BUTTON',
  hasAttribute: () => false,
  focus() {{ log.focused.push(name); globalThis.document.activeElement = this; }},
  closest: (sel) => (inPanel && panel && sel.includes('dialog') ? panel
    : (!inPanel && sel.includes('topo-canvas-wrap') ? {{}} : null)),
}});
const kids = [mk('close', true), mk('last', true)];
const graph = mk('graph', false);
const body = {{ name: 'body', tagName: 'BODY', closest: () => null }};
const target = S.focus === 'close' ? kids[0] : S.focus === 'last' ? kids[1]
  : S.focus === 'graph' ? graph : body;
const docListeners = [];
globalThis.document = {{
  activeElement: target,
  addEventListener: (t, fn) => docListeners.push(fn),
  querySelector: (sel) => (panel && S.panel.modal && sel.includes('aria-modal') ? panel : null),
}};
// --- trap factory (real handler source) ---
const FOCUSABLE_SELECTOR = 'button';
const trapShouldHandleEscape = m.trapShouldHandleEscape;
function makeTrap(el, onClose) {{ {trap}; return handleKeyDown; }}
// --- page factory (real handler source) ---
const pageEscapeShouldYield = m.pageEscapeShouldYield;
const overlayShortcutFor = m.overlayShortcutFor;
const SHORTCUT_SCOPE_SELECTOR = m.SHORTCUT_SCOPE_SELECTOR;
function makePage(selectedConduit, selectedSite, selectedRegion) {{
  const setSelectedConduit = (v) => log.setSelectedConduit.push(v);
  const setSelectedSite = (v) => log.setSelectedSite.push(v);
  const setSelectedRegion = (v) => log.setSelectedRegion.push(v);
  const setOverlays = () => {{ log.overlays += 1; }};
  {page};
  return handler;
}}
const pageFn = makePage(S.conduit, S.site, S.region);
const panelListeners = [];
if (panel) {{
  const trapFn = makeTrap(panel, () => {{ log.onClose += 1; }});
  if ({json.dumps(on_panel)}) panelListeners.push(trapFn);
  if ({json.dumps(on_doc)}) {{
    if (S.order === 'trap_first') {{ docListeners.push(trapFn); docListeners.push(pageFn); }}
    else {{ docListeners.push(pageFn); docListeners.push(trapFn); }}
  }} else docListeners.push(pageFn);
}} else docListeners.push(pageFn);
const ev = {{ key: S.key, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false,
  target, defaultPrevented: false, propagationStopped: false,
  preventDefault() {{ this.defaultPrevented = true; }},
  stopPropagation() {{ this.propagationStopped = true; }} }};
if (target.inPanel) for (const fn of panelListeners) fn(ev);
// stopPropagation on the panel stops the bubble to document; on document it does not
// stop the other document listeners (only stopImmediatePropagation would).
if (!(target.inPanel && ev.propagationStopped && panelListeners.length)) {{
  for (const fn of docListeners) fn(ev);
}}
process.stdout.write(JSON.stringify(log));
"""
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


_ORDERS = ("trap_first", "page_first")


def _src():
    return _read("routes", "topology.tsx")


# --- behavioral: designer's two required scenarios, both listener orders ---------------

@needs_node
@pytest.mark.parametrize("order", _ORDERS)
def test_dw149_mobile_modal_one_escape_closes_once_and_keeps_region(order):
    log = _simulate(_src(), {"key": "Escape", "panel": {"modal": True}, "focus": "close",
                             "conduit": None, "site": None, "region": "West", "order": order})
    assert log["onClose"] == 1, log
    assert log["setSelectedRegion"] == [] and log["setSelectedSite"] == [], log
    assert log["setSelectedConduit"] == [], log


@needs_node
@pytest.mark.parametrize("order", _ORDERS)
def test_dw149_desktop_site_panel_escape_clears_only_the_site(order):
    # Desktop site panel onClose is () => setSelectedSite(null) (route wiring); the page
    # handler must not also act, so region stays selected.
    log = _simulate(_src(), {"key": "Escape", "panel": {"modal": False}, "focus": "close",
                             "conduit": None, "site": "SITE-1", "region": "West",
                             "order": order})
    assert log["onClose"] == 1, log
    assert log["setSelectedRegion"] == [] and log["setSelectedSite"] == [], log


@needs_node
@pytest.mark.parametrize("order", _ORDERS)
def test_dw149_modal_escape_with_focus_on_body_still_closes_once(order):
    log = _simulate(_src(), {"key": "Escape", "panel": {"modal": True}, "focus": "body",
                             "conduit": None, "site": None, "region": "West", "order": order})
    assert log["onClose"] == 1, log
    assert log["setSelectedRegion"] == [], log


@needs_node
@pytest.mark.parametrize("order", _ORDERS)
def test_dw149_desktop_panel_escape_from_graph_drills_out_one_level(order):
    # Focus outside a non-modal panel: the page handler keeps its conduit > site > region
    # order and the trap stays out, so exactly one level closes.
    log = _simulate(_src(), {"key": "Escape", "panel": {"modal": False}, "focus": "graph",
                             "conduit": None, "site": "SITE-1", "region": "West",
                             "order": order})
    assert log["onClose"] == 0, log
    assert log["setSelectedSite"] == [None], log
    assert log["setSelectedRegion"] == [], log


@needs_node
def test_dw149_no_dialog_escape_behavior_unchanged():
    log = _simulate(_src(), {"key": "Escape", "panel": None, "focus": "graph",
                             "conduit": "CDT-1", "site": "SITE-1", "region": "West",
                             "order": "trap_first"})
    assert log["setSelectedConduit"] == [None], log
    assert log["setSelectedSite"] == [] and log["setSelectedRegion"] == [], log


@needs_node
@pytest.mark.parametrize("order", _ORDERS)
def test_dw149_tab_wrap_runs_once(order):
    log = _simulate(_src(), {"key": "Tab", "panel": {"modal": True}, "focus": "last",
                             "conduit": None, "site": None, "region": "West", "order": order})
    assert log["focused"] == ["close"], log
    assert log["onClose"] == 0 and log["overlays"] == 0, log


# --- pure helpers --------------------------------------------------------------------

def _node(body):
    js = (f"import * as m from {json.dumps('file://' + _LIB)};\nlet out;\n{body}\n"
          "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run([NODE, "--input-type=module", "-e", js],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_dw149_helper_truth_tables():
    out = _node("""
const inside = { inPanel: true };
const outside = { inPanel: false };
const panel = (modal) => ({ getAttribute: (n) => (n === 'aria-modal' && modal ? 'true' : null),
  contains: (t) => !!t && t.inPanel === true });
const esc = (dp = false) => ({ key: 'Escape', defaultPrevented: dp });
const inDialog = { closest: (s) => (s === m.DIALOG_SELECTOR ? {} : null) };
const notInDialog = { closest: () => null };
const modalDoc = { querySelector: (s) => (s === m.MODAL_DIALOG_SELECTOR ? {} : null) };
const emptyDoc = { querySelector: () => null };
out = {
  trapInside: m.trapShouldHandleEscape(esc(), inside, panel(false)),
  trapOutsideNonModal: m.trapShouldHandleEscape(esc(), outside, panel(false)),
  trapOutsideModal: m.trapShouldHandleEscape(esc(), outside, panel(true)),
  trapHandled: m.trapShouldHandleEscape(esc(true), inside, panel(true)),
  trapTab: m.trapShouldHandleEscape({ key: 'Tab' }, inside, panel(true)),
  trapNoPanel: m.trapShouldHandleEscape(esc(), inside, null),
  yieldPrevented: m.pageEscapeShouldYield(esc(true), notInDialog, emptyDoc),
  yieldInDialog: m.pageEscapeShouldYield(esc(), inDialog, emptyDoc),
  yieldModalOpen: m.pageEscapeShouldYield(esc(), notInDialog, modalDoc),
  yieldNone: m.pageEscapeShouldYield(esc(), notInDialog, emptyDoc),
  yieldNullTarget: m.pageEscapeShouldYield(esc(), null, null),
};""")
    assert out == {
        "trapInside": True, "trapOutsideNonModal": False, "trapOutsideModal": True,
        "trapHandled": False, "trapTab": False, "trapNoPanel": False,
        "yieldPrevented": True, "yieldInDialog": True, "yieldModalOpen": True,
        "yieldNone": False, "yieldNullTarget": False,
    }


# --- static wiring -------------------------------------------------------------------

def test_dw149_focus_trap_registers_a_single_listener():
    hook = _block(_src(), "function useFocusTrap(")
    assert hook.count("addEventListener(") == 1
    assert 'document.addEventListener("keydown", handleKeyDown)' in hook
    assert "el.addEventListener" not in hook
    assert hook.count("removeEventListener(") == 1


def test_dw149_trap_marks_escape_handled():
    trap = _block(_block(_src(), "function useFocusTrap("),
                  "const handleKeyDown = (e: KeyboardEvent) => {")
    i = trap.index("trapShouldHandleEscape(e, e.target, el)")
    assert trap.index("e.preventDefault()", i) < trap.index("onClose()", i)
    assert "e.stopPropagation()" in trap


def test_dw149_page_escape_yields_first():
    src = _src()
    i = src.index("// Keyboard shortcuts (\u00a77.1)")
    page = _block(src[i:], "const handler = (e: KeyboardEvent) => {")
    y = page.index("pageEscapeShouldYield(e, target, document)")
    assert y < page.index("setSelectedConduit(null)")
    assert y < page.index('target?.tagName === "INPUT"')


def test_dw149_skip_link_target_is_programmatically_focusable():
    root = _read("routes", "__root.tsx")
    m = re.search(r"<main\b[^>]*>", root)
    assert m and 'id="main-content"' in m.group(0)
    assert "tabIndex={-1}" in m.group(0)
    assert '<a href="#main-content" className="skip-nav">' in root


def test_dw149_main_focus_outline_scoped_to_main_only():
    css = re.sub(r"/\*.*?\*/", "", _read("styles", "lakelink-theme.css"), flags=re.S)
    rules = {m.group(1).strip(): m.group(2) for m in
             re.finditer(r"([^{}]+)\{([^{}]*)\}", css)}
    assert "outline: none" in rules.get("#main-content:focus", "")
    # The global ring for controls is untouched.
    ring = [b for s, b in rules.items() if "[tabindex]:focus-visible" in s]
    assert ring and "outline: 2px solid var(--lf-dark-teal)" in ring[0]
    # No rule removes outlines from main via :focus-visible.
    assert not any("main" in s and ":focus-visible" in s and "outline: none" in b
                   for s, b in rules.items())


def test_dw149_brand_clean():
    for parts in (("routes", "topology.tsx"), ("routes", "__root.tsx"),
                  ("lib", "topology-data-state.ts"), ("styles", "lakelink-theme.css")):
        assert "lumen" not in _read(*parts).lower(), parts
