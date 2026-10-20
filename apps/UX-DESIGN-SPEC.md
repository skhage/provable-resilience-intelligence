# Lakelink Fiber — Provable Resilience Intelligence App
## Binding UX Design Specification

**Author:** @designer · **Date:** 2026-10-19 · **Status:** BINDING  
**Task:** P3-APP-UX-REVIEW · **Priority:** HIGH  
**Applies to:** Resilience Scorecard app, Action Queue app, all UI surfaces in this project

> All findings in this document are **binding** per project charter.
> @app-developer MUST implement these requirements before any UX review can pass.

---

## 1. Brand Design Tokens

**BRANDING MANDATE:** Use "Lakelink Fiber" everywhere. Never "Lumen" or "Lumen Technologies".

### 1.1 Color Palette

| Token Name | Hex | Usage | Contrast Ratio (on white) |
| --- | --- | --- | --- |
| `--lf-dark-teal` | `#006272` | Primary actions, headers, nav background, link text | 7.14:1 ✅ AAA |
| `--lf-platinum` | `#E8E8E8` | Backgrounds, card surfaces, dividers | N/A (background) |
| `--lf-iron` | `#4D4D4D` | Body text, secondary labels | 7.75:1 ✅ AAA |
| `--lf-accent-orange` | `#F26522` | Accent: alerts, critical badges, CTAs | 3.07:1 ⚠️ Large text only |
| `--lf-white` | `#FFFFFF` | Text on dark-teal, card backgrounds | — |
| `--lf-risk-red` | `#D32F2F` | Critical resilience score (<40) | 5.73:1 ✅ AA |
| `--lf-risk-amber` | `#F9A825` | Moderate resilience score (40–69) | Use on dark bg only |
| `--lf-risk-green` | `#2E7D32` | Healthy resilience score (≥70) | 5.92:1 ✅ AA |

### 1.2 Contrast Rules (WCAG 2.1 AA)

* **Normal text (< 18pt):** minimum 4.5:1 contrast ratio
* **Large text (≥ 18pt bold or ≥ 24pt):** minimum 3:1 contrast ratio
* **Accent orange `#F26522` MUST NOT be used for normal-size text on white.** Use only for:
  * Large bold headings (≥ 18pt bold)
  * Icon badges with adjacent text labels
  * Filled buttons with white text (orange bg + white text = 3.07:1, acceptable for large UI controls only with `aria-label`)
* **All interactive elements** must have a visible focus indicator (3:1 contrast vs surrounding)

### 1.3 Typography

| Role | Font | Weight | Size | Line Height | Color |
| --- | --- | --- | --- | --- | --- |
| H1 (page title) | Inter | 700 | 28px | 1.3 | `--lf-dark-teal` |
| H2 (section) | Inter | 600 | 22px | 1.35 | `--lf-dark-teal` |
| H3 (card title) | Inter | 600 | 18px | 1.4 | `--lf-iron` |
| Body | Inter | 400 | 14px | 1.5 | `--lf-iron` |
| Caption / Label | Inter | 500 | 12px | 1.4 | `--lf-iron` at 80% opacity |
| Monospace (IDs, codes) | JetBrains Mono | 400 | 13px | 1.4 | `--lf-iron` |

### 1.4 Spacing Scale

`4px` base unit: `xs=4px`, `sm=8px`, `md=16px`, `lg=24px`, `xl=32px`, `xxl=48px`

---

## 2. Layout & Responsive Breakpoints

### 2.1 Grid System

| Breakpoint | Name | Columns | Gutter | Sidebar |
| --- | --- | --- | --- | --- |
| ≥1440px | Desktop XL | 12 | 24px | 280px collapsed to 64px |
| 1024–1439px | Desktop | 12 | 20px | 240px collapsed to 56px |
| 768–1023px | Tablet | 8 | 16px | Hidden (hamburger) |
| < 768px | Mobile | 4 | 12px | Hidden (hamburger) |

### 2.2 Page Structure

```
┌─────────────────────────────────────────────────────┐
│  Top Bar: Lakelink Fiber logo │ App title │ User    │
├──────┬──────────────────────────────────────────────┤
│ Side │  Breadcrumb: Portfolio > Service > Detail     │
│ Nav  ├──────────────────────────────────────────────┤
│      │  KPI Strip: 4 metric cards (responsive wrap) │
│      ├──────────────────────────────────────────────┤
│      │  Primary Content: Scorecard / Map / Table    │
│      ├──────────────────────────────────────────────┤
│      │  Secondary: Action Queue / Timeline          │
└──────┴──────────────────────────────────────────────┘
```

* Top bar: 56px height, `--lf-dark-teal` background, white text
* Side nav: dark-teal gradient, white nav items, active = `--lf-accent-orange` left border
* Content area: `--lf-platinum` background, white cards with 8px border-radius, `box-shadow: 0 1px 3px rgba(0,0,0,0.08)`

---

## 3. Component Specifications

### 3.1 Resilience Score Badge

* Circular gauge (120px diameter on desktop, 80px on mobile)
* Score 0–100 displayed center, 28px bold
* Ring color: `--lf-risk-red` (< 40), `--lf-risk-amber` (40–69), `--lf-risk-green` (≥ 70)
* `role="meter"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`, `aria-label="Resilience score: {n} out of 100"`

### 3.2 KPI Metric Card

* 4-card strip, equal width, responsive wrap to 2x2 below 1024px, stack on mobile
* Structure: label (caption) → value (H2 size, `--lf-dark-teal`) → trend arrow + delta
* Min-height: 96px; padding: `md` all sides
* `role="group"`, `aria-label="{metric name}: {value}"`

### 3.3 Data Table

* Sticky header row with `--lf-dark-teal` background, white text
* Alternating row stripes: white / `--lf-platinum`
* Sortable columns: visible sort indicator (▲/▼), `aria-sort` attribute
* Row hover: light teal tint (`#006272` at 5% opacity)
* Pagination: 25 rows default, selector for 10/25/50/100
* **Keyboard:** all interactive cells reachable via Tab, sort via Enter/Space

### 3.4 Action Queue Item

* Card list, each card: severity badge (left) + title + service ID + timestamp + assignee
* Severity badge: uses risk colors, min 44×44px touch target
* Swipe-to-dismiss on mobile (with undo toast, 5s timeout)
* `role="listitem"`, full card is keyboard-focusable

### 3.5 Map View (Geospatial)

* Use Mapbox GL JS or Deck.gl
* Default center: continental US, zoom 4
* Path overlays: conduit/span polylines colored by resilience score
* Hazard overlays: semi-transparent polygons (wildfire=red, flood=blue, weather=amber)
* **A11y:** All map data must have a parallel table view toggle. Maps are `role="img"` with `aria-label` summary.

---

## 4. Accessibility Requirements (WCAG 2.1 AA)

### 4.1 Mandatory Checklist

- [ ] All images/icons have `alt` text or `aria-label`
- [ ] Color is never the sole means of conveying information (add icons/text alongside)
- [ ] Focus order follows visual reading order (left-to-right, top-to-bottom)
- [ ] All interactive elements have visible focus ring (2px solid `--lf-dark-teal`, 2px offset)
- [ ] Touch targets ≥ 44×44px on mobile
- [ ] Form inputs have associated `<label>` elements
- [ ] Error messages are announced via `aria-live="polite"`
- [ ] Modals trap focus and return focus on close
- [ ] Data visualizations provide text alternatives
- [ ] Page has proper heading hierarchy (single H1, sequential H2/H3)
- [ ] `lang="en"` on `<html>` element
- [ ] No content flashes more than 3 times per second
- [ ] Reduced-motion media query respected for animations

### 4.2 Screen Reader Landmarks

```html
<header role="banner">        <!-- Top bar -->
<nav role="navigation">        <!-- Side nav -->
<main role="main">             <!-- Content area -->
  <section aria-label="KPIs">  <!-- Metric strip -->
  <section aria-label="...">   <!-- Each content region -->
</main>
```

---

## 5. Interaction Patterns

### 5.1 Loading States

* Skeleton screens (not spinners) for initial page load
* Pulse animation on `--lf-platinum` → white gradient
* Inline loading indicators for table data refresh
* `aria-busy="true"` on loading containers

### 5.2 Error States

* Inline error banners: `--lf-risk-red` left border, light red background
* Retry button with exponential backoff (1s, 2s, 4s)
* Empty state: illustration + "No data available" + suggested action

### 5.3 Notifications

* Toast notifications: bottom-right, auto-dismiss 5s, manual dismiss always available
* Critical alerts: sticky banner at top, requires explicit dismiss
* All toasts have `role="alert"` or `role="status"`

---

## 6. Performance Targets

| Metric | Target |
| --- | --- |
| First Contentful Paint | < 1.5s |
| Largest Contentful Paint | < 2.5s |
| Cumulative Layout Shift | < 0.1 |
| First Input Delay | < 100ms |
| Bundle size (gzipped) | < 250KB JS, < 50KB CSS |

---

## 7. Review Findings

### FINDING-01: No App Scaffold Exists (2026-10-19)

**Severity:** CRITICAL — **RESOLVED (2026-10-20)**  
**Status:** P3-APP-SCAFFOLD completed by @app-developer. 14-file scaffold delivered with FastAPI backend + React/TypeScript frontend.  
**Tasks filed:** P3-APP-SCAFFOLD-BRAND, P3-APP-SCAFFOLD-A11Y, P3-APP-SCAFFOLD-RESPONSIVE

### FINDING-02: Missing ARIA Landmarks & Roles (2026-10-20)

**Severity:** HIGH  
**Status:** OPEN — filed as UX-REM-A11Y-LANDMARKS  
**Details:**
* Route pages (`index.tsx`, `actions.tsx`) lack `role="banner"` on `<header>`, `role="navigation"` on `<nav>`, `role="main"` on `<main>`
* `ScoreGauge` component has no `role="meter"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label`
* KPI cards lack `role="group"` and `aria-label="{metric}: {value}"`
* Sortable `<th>` in `service-table.tsx` missing `aria-sort`, `role="columnheader"`, keyboard Enter/Space handler
* Filter buttons in `action-queue-table.tsx` missing `aria-pressed` toggle state
* No skip-navigation link for keyboard users
* `<html lang="en">` not declared

### FINDING-03: No Visible Focus Indicators (2026-10-20)

**Severity:** HIGH  
**Status:** OPEN — filed as UX-REM-A11Y-FOCUS  
**Details:** Theme CSS has zero `:focus-visible` styles. Spec mandates `outline: 2px solid var(--lf-dark-teal); outline-offset: 2px` on all interactive elements.

### FINDING-04: Touch Targets Below 44×44px Minimum (2026-10-20)

**Severity:** MEDIUM  
**Status:** OPEN — filed as UX-REM-A11Y-TOUCH  
**Details:** `.btn` padding `6px 14px` yields ~30px height. `.rating-pill` is 28×28px. Both fail WCAG 2.1 AA 44×44px mobile touch target.

### FINDING-05: Zero Responsive Breakpoints (2026-10-20)

**Severity:** HIGH  
**Status:** OPEN — filed as UX-REM-RESPONSIVE  
**Details:**
* `lakelink-theme.css` has zero `@media` queries despite spec defining 4 breakpoints
* Nav tabs overflow on narrow screens — no hamburger menu for tablet/mobile
* 9-column service table has no horizontal scroll wrapper — overflows on mobile
* No `@media (prefers-reduced-motion: reduce)` for gauge transitions

### FINDING-06: Duplicated Header/Nav Across Routes (2026-10-20)

**Severity:** MEDIUM  
**Status:** OPEN — filed as UX-REM-LAYOUT-ROOT  
**Details:** Both `index.tsx` and `actions.tsx` render identical `<header>` + `<nav>`. Must extract to a shared root layout component (`_root.tsx` or `_layout.tsx`) to enforce consistency and DRY.

### FINDING-07: Missing Pagination & Empty States (2026-10-20)

**Severity:** MEDIUM  
**Status:** OPEN — filed as UX-REM-TABLE-UX  
**Details:**
* Service table has no pagination (spec: 25 rows default, 10/25/50/100 selector)
* No empty-state design when filters return zero rows
* No toast/notification when action status is updated

### FINDING-08: Emoji Icons Instead of Lucide (2026-10-20)

**Severity:** LOW  
**Status:** OPEN — filed as UX-REM-ICONS  
**Details:** `ACTION_TYPE_ICONS` in `action-queue-table.tsx` uses emoji (🔀🛠️📨). Emojis render inconsistently across OS/browser. Replace with Lucide React icons per brand guide.

### FINDING-09: Inline Styles Instead of CSS Classes (2026-10-20)

**Severity:** LOW  
**Status:** OPEN — filed as UX-REM-CSS-HYGIENE  
**Details:** Several components use inline `style={{}}` props. Convert to theme CSS utility classes for maintainability and consistency.

---

## Appendix A: CSS Custom Properties Template

```css
:root {
  /* Lakelink Fiber Brand */
  --lf-dark-teal: #006272;
  --lf-platinum: #E8E8E8;
  --lf-iron: #4D4D4D;
  --lf-accent-orange: #F26522;
  --lf-white: #FFFFFF;

  /* Risk Severity */
  --lf-risk-red: #D32F2F;
  --lf-risk-amber: #F9A825;
  --lf-risk-green: #2E7D32;

  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-xxl: 48px;

  /* Typography */
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Elevation */
  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.08);
  --shadow-dropdown: 0 4px 12px rgba(0, 0, 0, 0.12);
  --shadow-modal: 0 8px 24px rgba(0, 0, 0, 0.16);

  /* Border */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --radius-full: 9999px;
}
```

---

*This specification is a living document. @designer reviews are authoritative — deviations require written @designer approval.*