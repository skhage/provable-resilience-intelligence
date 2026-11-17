"""BUG-QA-171: behavioural tests for RetryBoundary focus (follow-up to BUG-DW-178).

The focus decisions moved out of components/ui/retry-boundary.tsx into the pure module
lib/retry-focus.ts. These tests EXECUTE that module with Node (--experimental-strip-types;
no npm registry on serverless, so no React/jsdom) against a fake DOM with real
contains()/activeElement semantics, driving the same call sequence the component uses:

  click Retry  -> markRetryPending -> ErrorBoundary onReset -> handleBoundaryReset(reason)
  re-error     -> new RetryButton effect -> focusRetryButtonIfPending(flag, btn, container, document)
  success      -> RetryFocusProbe effect -> shouldScheduleRetryFocus -> rAF ->
                  focusContainerAfterRetry(flag, container, document)

The 4 QA cases + the late-resolve edge case (user moved focus outside while loading) +
StrictMode double effect. A wiring test pins the component to these helpers, so a refactor
that keeps strings but drops a helper call fails here.

Negative check: fails on 1e73b1d (no lib/retry-focus.ts; probe had no late-resolve guard).
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
LIB = os.path.join(UI, "lib", "retry-focus.ts")
COMPONENT = os.path.join(UI, "components", "ui", "retry-boundary.tsx")

# Fake DOM + a harness that mirrors the component's lifecycle using the real module.
HARNESS = r"""
import * as F from './m.ts';

class El {
  constructor(doc, name, parent = null) { this.doc = doc; this.name = name; this.parent = parent; this.attached = true; }
  contains(o) { for (let n = o; n; n = n.parent) { if (n === this) return true; } return false; }
  focus() { if (this.attached) this.doc.activeElement = this; }
  remove() { this.attached = false; if (this.doc.activeElement === this) this.doc.activeElement = this.doc.body; }
}
function world() {
  const doc = { activeElement: null, body: null };
  doc.body = new El(doc, 'body');
  doc.activeElement = doc.body;
  const container = new El(doc, 'container', doc.body);
  const outside = new El(doc, 'outside-link', doc.body);
  const frames = [];
  const raf = (cb) => { frames.push(cb); return frames.length; };
  const flush = () => { while (frames.length) frames.shift()(); };
  const flag = { current: false };
  let button = null;
  const api = {
    doc, container, outside, flag,
    get button() { return button; },
    // Fallback renders a new Retry button; its mount effect runs.
    mountFallback() {
      button = new El(doc, 'retry-button', container);
      F.focusRetryButtonIfPending(flag, button, container, doc);
    },
    // User clicks Retry: flag set, then resetErrorBoundary unmounts the fallback.
    clickRetry() {
      button.focus();
      F.markRetryPending(flag);
      F.handleBoundaryReset(flag, 'imperative-api');
      button.remove();
    },
    resetKeys() { F.handleBoundaryReset(flag, 'keys'); if (button) button.remove(); },
    // Children resolved: RetryFocusProbe effect (optionally StrictMode mount/unmount/mount).
    resolve({ strict = false } = {}) {
      const effect = () => F.shouldScheduleRetryFocus(flag) ? raf(() => F.focusContainerAfterRetry(flag, container, doc)) : 0;
      let id = effect();
      if (strict && id) { frames.splice(id - 1, 1); id = effect(); }
      else if (strict) { effect(); }
    },
    flush,
    active() { return doc.activeElement.name; },
  };
  return api;
}

const out = {};

// 1. First error: focus must not move (user is wherever they were).
{ const w = world(); w.outside.focus(); w.mountFallback();
  out.first_error = { active: w.active(), pending: w.flag.current }; }

// 1b. First error while focus is on body: still no move.
{ const w = world(); w.mountFallback(); out.first_error_body = w.active(); }

// 2. Retry -> re-error: the NEW Retry button takes focus.
{ const w = world(); w.mountFallback(); const old = w.button; w.clickRetry();
  const afterClick = w.active(); w.mountFallback();
  out.retry_reerror = { afterClick, active: w.active(), isNew: w.button !== old, pending: w.flag.current }; }

// 3. Retry -> success: container takes focus on the next frame, not synchronously.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.resolve();
  const beforeFrame = w.active(); w.flush();
  out.retry_success = { beforeFrame, active: w.active(), pending: w.flag.current }; }

// 4. resetKeys change (e.g. filter) after an error: no focus move on resolve.
{ const w = world(); w.mountFallback(); w.outside.focus(); w.resetKeys(); w.resolve(); w.flush();
  out.reset_keys = w.active(); }

// 4b. Retry clicked, then a resetKeys change before resolve: keys win, no focus move.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.resetKeys(); w.resolve(); w.flush();
  out.retry_then_keys = { active: w.active(), pending: w.flag.current }; }

// 5. Late resolve: user moved focus OUTSIDE while loading -> focus left alone, flag consumed.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.outside.focus(); w.resolve(); w.flush();
  out.late_resolve_moved = { active: w.active(), pending: w.flag.current }; }

// 5b. Late re-error after user moved outside -> new Retry button does not steal focus.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.outside.focus(); w.mountFallback();
  out.late_reerror_moved = { active: w.active(), pending: w.flag.current }; }

// 5c. Focus moved to the container itself (inside) during load -> still focuses container.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.container.focus(); w.resolve(); w.flush();
  out.inside_ok = w.active(); }

// 6. StrictMode double effect still focuses exactly once, and a later resolve does nothing.
{ const w = world(); w.mountFallback(); w.clickRetry(); w.resolve({ strict: true }); w.flush();
  const first = w.active(); w.outside.focus(); w.resolve(); w.flush();
  out.strict = { first, second: w.active() }; }

// 7. Initial load success with no Retry: nothing scheduled.
{ const w = world(); w.resolve(); out.initial_scheduled = F.shouldScheduleRetryFocus(w.flag); w.flush(); out.initial = w.active(); }

// Pure guard known answers.
{ const w = world();
  out.guard = {
    body: F.userMovedFocusAway(w.doc, w.container),
    nullDoc: F.userMovedFocusAway(null, w.container),
    self: (w.container.focus(), F.userMovedFocusAway(w.doc, w.container)),
    outside: (w.outside.focus(), F.userMovedFocusAway(w.doc, w.container)),
    noContainer: F.userMovedFocusAway(w.doc, null),
  }; }

console.log(JSON.stringify(out));
"""


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def run():
    assert os.path.exists(LIB), "lib/retry-focus.ts missing"
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    d = tempfile.mkdtemp()
    shutil.copy(LIB, os.path.join(d, "m.ts"))
    main = os.path.join(d, "main.ts")
    with open(main, "w") as f:
        f.write(HARNESS)
    r = subprocess.run([node, "--experimental-strip-types", "--no-warnings", main],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 and "strip-types" in r.stderr:
        pytest.skip("node lacks --experimental-strip-types")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def test_first_error_does_not_move_focus(run):
    assert run["first_error"] == {"active": "outside-link", "pending": False}
    assert run["first_error_body"] == "body"


def test_retry_then_reerror_focuses_new_retry_button(run):
    r = run["retry_reerror"]
    assert r["afterClick"] == "body"  # old button unmounted: the bug DW-178 fixed
    assert r == {"afterClick": "body", "active": "retry-button", "isNew": True, "pending": False}


def test_retry_then_success_focuses_container_next_frame(run):
    assert run["retry_success"] == {"beforeFrame": "body", "active": "container", "pending": False}


def test_reset_keys_never_moves_focus(run):
    assert run["reset_keys"] == "outside-link"
    assert run["retry_then_keys"] == {"active": "body", "pending": False}


def test_late_resolve_respects_user_focus(run):
    assert run["late_resolve_moved"] == {"active": "outside-link", "pending": False}
    assert run["late_reerror_moved"] == {"active": "outside-link", "pending": False}
    assert run["inside_ok"] == "container"


def test_strict_mode_focuses_once(run):
    assert run["strict"] == {"first": "container", "second": "outside-link"}


def test_initial_load_schedules_nothing(run):
    assert run["initial_scheduled"] is False
    assert run["initial"] == "body"


def test_guard_known_answers(run):
    assert run["guard"] == {"body": False, "nullDoc": False, "self": False, "outside": True, "noContainer": True}


def test_component_wires_helpers():
    src = _read(COMPONENT)
    assert 'from "@/lib/retry-focus"' in src
    assert "handleBoundaryReset(retryPendingRef, details.reason)" in src
    assert re.search(r"onClick=\{\(\) => \{\s*markRetryPending\(retryPendingRef\);\s*onRetry\(\);", src)
    assert "focusRetryButtonIfPending(retryPendingRef, buttonRef.current, containerRef.current, document)" in src
    assert re.search(r"if \(!shouldScheduleRetryFocus\(retryPendingRef\)\) return;\s*const frame = requestAnimationFrame\(\(\) => \{\s*focusContainerAfterRetry\(retryPendingRef, containerRef\.current, document\);", src)
    # No inline flag writes or direct .focus() left in the component: all decisions go through the lib.
    assert "retryPendingRef.current =" not in src
    assert ".focus()" not in src


def test_lib_is_pure_and_on_brand():
    src = _read(LIB)
    assert "from \"react\"" not in src and "from 'react'" not in src
    assert "Lakelink Fiber" in src
    banned = "lu" + "men"
    assert banned not in src.lower() and banned not in _read(COMPONENT).lower()
