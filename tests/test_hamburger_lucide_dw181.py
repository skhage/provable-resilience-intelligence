"""BUG-DW-181 regression tests: header hamburger toggle uses Lucide Menu/X, not Unicode glyphs.

Acceptance (from @designer S131, BRAND-GUIDE section 6):
  1. routes/__root.tsx has no U+2630 / U+2715 (escaped or literal) and no emoji/dingbat code points.
  2. Menu and X are imported from lucide-react and rendered at size 24, strokeWidth 1.5, aria-hidden.
  3. The button keeps aria-label toggle, aria-expanded, aria-controls="main-nav" and the ref.
  4. CSS keeps the 44px min target, the white focus ring and the HC (transparent 1px) border.
  5. lucide-react is a declared dependency; no banned brand string in the touched files.
These tests fail on HEAD 615cf93 and pass after the fix.
"""
import json
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_APP = _ROOT / "apps/resilience-scorecard"
_UI = _APP / "src/resilience_scorecard/ui"
_ROOT_TSX = _UI / "routes/__root.tsx"
_CSS = _UI / "styles/lakelink-theme.css"
_PKG = _APP / "package.json"

_GLYPHS = re.compile("[\u2600-\u27BF\U0001F300-\U0001FAFF\u2630\u2715]")
_BANNED = "lu" + "men"


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def _hamburger_button(src: str) -> str:
    start = src.index('className="nav-hamburger"')
    start = src.rindex("<button", 0, start)
    end = src.index("</button>", start)
    return src[start:end]


def _css_block(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"missing CSS block {selector}"
    return m.group(1)


def test_no_escaped_hamburger_glyphs():
    src = _read(_ROOT_TSX).lower()
    assert "u2630" not in src
    assert "u2715" not in src


def test_no_literal_icon_glyphs():
    src = _read(_ROOT_TSX)
    hits = [(src.count("\n", 0, m.start()) + 1, hex(ord(m.group()))) for m in _GLYPHS.finditer(src)]
    assert hits == [], f"icon glyph code points in __root.tsx: {hits}"


def test_lucide_menu_x_imported():
    src = _read(_ROOT_TSX)
    m = re.search(r'import\s*\{([^}]*)\}\s*from\s*"lucide-react"', src)
    assert m, "lucide-react import missing"
    names = {n.strip() for n in m.group(1).split(",") if n.strip()}
    assert {"Menu", "X"} <= names


def test_button_renders_menu_and_x():
    btn = _hamburger_button(_read(_ROOT_TSX))
    assert re.search(r"navOpen\s*\?\s*\(\s*<X\b", btn), "open state must render <X>"
    assert re.search(r":\s*\(\s*<Menu\b", btn), "closed state must render <Menu>"


def test_icon_props_size_stroke_decorative():
    btn = _hamburger_button(_read(_ROOT_TSX))
    icons = re.findall(r"<(?:Menu|X)\b[^>]*/>", btn)
    assert len(icons) == 2
    for tag in icons:
        assert "size={24}" in tag, tag
        assert "strokeWidth={1.5}" in tag, tag
        assert re.search(r'aria-hidden=(\{true\}|"true")', tag), tag


def test_button_has_no_text_children():
    btn = _hamburger_button(_read(_ROOT_TSX))
    body = btn[btn.index(">", btn.index("aria-label")) + 1:]
    stripped = re.sub(r"<(?:Menu|X)\b[^>]*/>", "", body)
    stripped = re.sub(r"[{}()?:\s]|navOpen", "", stripped)
    assert stripped == "", f"unexpected text children: {stripped!r}"


def test_button_a11y_attributes_preserved():
    btn = _hamburger_button(_read(_ROOT_TSX))
    assert "ref={hamburgerRef}" in btn
    assert "aria-expanded={navOpen}" in btn
    assert 'aria-controls="main-nav"' in btn
    assert '"Close navigation menu"' in btn and '"Open navigation menu"' in btn


def test_css_target_size_and_hc_border_preserved():
    block = _css_block(_read(_CSS), ".nav-hamburger")
    assert "min-width: 44px" in block
    assert "min-height: 44px" in block
    assert "border: 1px solid transparent" in block
    assert "color: var(--lf-white)" in block


def test_css_white_focus_ring_preserved():
    block = _css_block(_read(_CSS), ".nav-hamburger:focus-visible")
    assert "outline: 2px solid var(--lf-white)" in block


def test_lucide_dependency_declared():
    deps = json.loads(_read(_PKG)).get("dependencies", {})
    assert "lucide-react" in deps


def test_no_banned_brand_string():
    for p in (_ROOT_TSX, pathlib.Path(__file__)):
        assert _BANNED not in _read(p).lower(), p
