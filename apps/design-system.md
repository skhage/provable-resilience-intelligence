# Lakelink Fiber Design System

**Project:** Provable Resilience Intelligence  
**Author:** @designer  
**Created:** 2026-10-23  
**Status:** BINDING — All new UI work must follow these patterns.  
**CEO Directive:** Never use "Lumen" or "Lumen Technologies". All assets use **"Lakelink Fiber"**.  
**Source of truth:** `lakelink-theme.css` (1244 lines) + this document.  
**Companion:** `BRAND-GUIDE.md` (color ratios, forbidden terms), `UX-DESIGN-SPEC.md`, `TOPOLOGY-VIS-SPEC.md`, `HAZARD-VIS-SPEC.md`.

---

## 1. Brand Identity

| Property | Value |
| --- | --- |
| Company | Lakelink Fiber |
| Product | Provable Resilience Intelligence |
| Voice | Technical, confident, precise. Data-driven, not aspirational. Concrete metrics over vague assurances. |
| Page title pattern | `{Route Name} \| Lakelink Fiber` |
| Dashboard title pattern | `Lakelink Fiber — {Subtitle}` |
| Genie space pattern | `{Audience} Resilience Intelligence` |

---

## 2. Color Tokens

All colors are defined as CSS custom properties on `:root` in `lakelink-theme.css`.

### 2.1 Primary Palette

| Name | Hex | Token | Usage | WCAG on White |
| --- | --- | --- | --- | --- |
| Dark Teal | `#006272` | `--lf-dark-teal` | Headers, nav, buttons, links, headings, focus rings | 7.14:1 AAA |
| Platinum | `#E8E8E8` | `--lf-platinum` | Page background, stripe rows, dividers | — |
| Iron | `#4D4D4D` | `--lf-iron` | Body text, labels, captions | 7.75:1 AAA |
| Accent Orange | `#F26522` | `--lf-accent-orange` | Alerts, critical badges, CTAs | 3.07:1 ⚠️ Large text only |
| White | `#FFFFFF` | `--lf-white` | Text on dark-teal, card backgrounds | — |

### 2.2 Extended Teal Ramp

| Name | Hex | Token | Usage |
| --- | --- | --- | --- |
| Teal Light | `#00839A` | `--lf-dark-teal-light` | Hover states, secondary accents |
| Teal Hover | `#004D5A` | `--lf-dark-teal-hover` | Active/pressed states |
| Warm Gold | `#FFCC80` | `--lf-accent-warm-gold` | Brand accent on dark-teal header (4.75:1 AA) |

### 2.3 Risk / Severity Palette

| Severity | Hex | Token | Tinted BG | Dark Text |
| --- | --- | --- | --- | --- |
| Critical | `#D32F2F` | `--lf-risk-red` | `#FEE2E2` | `#991B1B` (6.80:1) |
| High | `#F26522` | `--lf-accent-orange` | `#FFEDD5` | `#9A3412` (6.38:1) |
| Medium | `#F9A825` | `--lf-risk-amber` | `#FEF3C7` | `#92400E` (6.37:1) |
| Low | `#2E7D32` | `--lf-risk-green` | `#DCFCE7` | `#166534` (6.49:1) |

### 2.4 Resilience Score Gradient

| Rating | Range | Token | Hex |
| --- | --- | --- | --- |
| Excellent | ≥ 85 | `--score-excellent` | `#2E7D32` |
| Good | 70–84 | `--score-good` | `#65A30D` |
| Fair | 55–69 | `--score-fair` | `#F9A825` |
| Poor | 40–54 | `--score-poor` | `#EA580C` |
| Failing | < 40 | `--score-failing` | `#D32F2F` |

### 2.5 Path Diversity Ratings

| Grade | Text | Background | Ratio |
| --- | --- | --- | --- |
| A | `#166534` | `#DCFCE7` | 6.49:1 |
| B | `#3F6212` | `#ECFCCB` | 6.52:1 |
| C | `#92400E` | `#FEF3C7` | 6.37:1 |
| D | `#9A3412` | `#FFEDD5` | 6.38:1 |
| F | `#991B1B` | `#FEE2E2` | 6.80:1 |

### 2.6 Hazard Type Colors

| Type | Text | Background | Ratio |
| --- | --- | --- | --- |
| Severe Weather | `#7C2D12` | `#FFF7ED` | 8.83:1 AAA |
| Earthquake | `#581C87` | `#FAF5FF` | 10.14:1 AAA |
| Flood | `#1E3A5F` | `#EFF6FF` | 10.57:1 AAA |
| Wildfire | `#991B1B` | `#FEF2F2` | 7.60:1 AAA |
| Dig Ticket | `#854D0E` | `#FEFCE8` | 6.62:1 AA |

### 2.7 Diversity Status (Topology)

| Status | Hex | Token |
| --- | --- | --- |
| Full | `#16A34A` | `--lf-diversity-full` |
| Partial | `#D97706` | `--lf-diversity-partial` |
| Single | `#DC2626` | `--lf-diversity-single` |
| Unknown | `#9CA3AF` | `--lf-diversity-unknown` |

### 2.8 Dashboard Chart Palette (AI/BI)

Sequential order: `#006272` → `#F26522` → `#16A34A` → `#6B7280` → `#00839A`

---

## 3. Typography

### 3.1 Font Stacks

| Role | Token | Stack |
| --- | --- | --- |
| Primary | `--font-primary` | `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` |
| Monospace | `--font-mono` | `'JetBrains Mono', 'Fira Code', monospace` |

### 3.2 Type Scale

| Role | Font | Weight | Size | Line Height | Color |
| --- | --- | --- | --- | --- | --- |
| H1 (page title) | Inter | 700 | 28px | 1.3 | `--lf-dark-teal` |
| H2 (section) | Inter | 600 | 22px | 1.35 | `--lf-dark-teal` |
| H3 (card/panel title) | Inter | 600 | 18px | 1.4 | `--lf-iron` |
| Body | Inter | 400 | 14px | 1.5 | `--lf-iron` |
| Caption / Label | Inter | 500 | 12px | 1.4 | `--lf-iron` @ 80% |
| Monospace (IDs, codes) | JetBrains Mono | 400 | 13px | 1.4 | `--lf-iron` |
| KPI label | Inter | 500 | 12px | 1.4 | `--lf-iron` @ 80%, uppercase, 0.05em tracking |
| KPI value | Inter | 600 | 22px | 1.35 | `--lf-dark-teal` |
| Header brand | Inter | 700 | 18px (15px mobile) | 1.3 | `--lf-accent-warm-gold` |

### 3.3 Responsive Adjustments

| Element | Desktop | Mobile (<768px) |
| --- | --- | --- |
| Header h1 / brand-accent | 18px | 15px |
| Section header h2 | 22px | 18px |

---

## 4. Spacing Scale

**Base unit:** 4px

| Token | Value | Common Use |
| --- | --- | --- |
| `--space-xs` | 4px | Tight gaps, label margins |
| `--space-sm` | 8px | Inner padding, button gaps |
| `--space-md` | 16px | Card padding, section gaps |
| `--space-lg` | 24px | Page padding, section margins |
| `--space-xl` | 32px | Large separations |
| `--space-xxl` | 48px | Empty-state padding |

---

## 5. Elevation (Shadows)

| Level | Token | CSS | Usage |
| --- | --- | --- | --- |
| Card | `--shadow-card` | `0 1px 3px rgba(0,0,0,0.08)` | KPI cards, data tables, legends |
| Dropdown | `--shadow-dropdown` | `0 4px 12px rgba(0,0,0,0.12)` | Header, menus, popovers, toasts |
| Modal | `--shadow-modal` | `0 8px 24px rgba(0,0,0,0.16)` | Detail panels, dialogs |

---

## 6. Border Radius

| Token | Value | Usage |
| --- | --- | --- |
| `--radius-sm` | 4px | Buttons, tabs, inputs, small UI |
| `--radius-md` | 8px | Cards, tables, panels, canvas wraps |
| `--radius-lg` | 16px | Data-source badge |
| `--radius-full` | 9999px | Badges (pill shape), rating pills |

---

## 7. Layout

| Token / Value | Usage |
| --- | --- |
| `--sidebar-width: 240px` | Reserved for sidebar (future use) |
| `--header-height: 56px` | Sticky app header height |
| `max-width: 1400px` | Page content container (centered) |
| `max-width: 100%` | Content below 1440px |

---

## 8. Component Patterns

### 8.1 App Shell

```
┌───────────────────── App Header (56px, sticky, dark-teal) ────────────┐
│  [Brand Accent] Lakelink Fiber — Provable Resilience   [Nav Tabs]  [●]│
├───────────────────────────────────────────────────────────────────────┤
│  <main id="main-content" class="page-content">                       │
│    ┌─ Section ──────────────────────────────────────────────────┐    │
│    │  <h2>Section Title</h2>                                    │    │
│    │  <Component />                                             │    │
│    └────────────────────────────────────────────────────────────┘    │
│  </main>                                                             │
└───────────────────────────────────────────────────────────────────────┘
```

* Skip-nav link: first element, visually hidden until focused (WCAG 2.4.1)
* Header: `role="banner"`, sticky top, `z-index: 100`
* Main: `id="main-content"`, `role="main"`
* Nav: `role="navigation"`, `aria-label="Main navigation"`
* Page titles: set per-route via `document.title` (WCAG 2.4.2)
* `document.documentElement.lang = "en"` set in root layout

### 8.2 KPI Cards

```css
.kpi-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  min-height: 96px (80px mobile);
  box-shadow: card;
  border-left: 4px solid [severity color];
}
```

* Grid: `repeat(auto-fit, minmax(200px, 1fr))` → 2-col tablet, 1-col mobile
* Structure: `.kpi-label` (12px uppercase) → `.kpi-value` (22px teal) → optional `.kpi-sub`
* Severity variants: `.critical`, `.high`, `.warning`, `.success` set left border color
* Accessibility: each card has `role="group"` + `aria-label` describing metric + value
* Loading: `aria-busy="true"` with skeleton placeholders matching card count

### 8.3 Data Tables

```css
.data-table { background: white; border-radius: 8px; box-shadow: card; overflow: hidden; }
.data-table th { background: dark-teal; color: white; 12px uppercase; }
.data-table tbody tr:nth-child(even) { background: platinum; }
.data-table tbody tr:hover { background: teal @ 5%; }
```

* Sortable headers: `th[aria-sort]` with cursor pointer, focus-visible ring
* Horizontal scroll on tablet: `overflow-x: auto; min-width: 700px`
* Pagination: `.pagination-bar` at bottom with page controls + page-size select
* Empty state: centered icon + message + hint text
* Expandable rows: `.hazard-detail-row` with teal 3% background

### 8.4 Badges

```css
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}
```

**Tinted-bg + dark-text pattern** (WCAG AA compliant):  
* `.critical` → `#FEE2E2` bg, `#991B1B` text  
* `.high` → `#FFEDD5` bg, `#9A3412` text  
* `.medium` → `#FEF3C7` bg, `#92400E` text  
* `.low` → `#DCFCE7` bg, `#2E7D32` text  

Status variants: `.pending`, `.in_progress`, `.completed`, `.cancelled`  
Hazard variants: `.severe_weather`, `.earthquake`, `.flood`, `.wildfire`, `.dig_ticket`

### 8.5 Rating Pills

```css
.rating-pill {
  width: 28px (44px mobile);
  height: 28px (44px mobile);
  border-radius: 50%;
  font-size: 13px;
  font-weight: 700;
  text-align: center;
}
```

Grades A–F use tinted-bg + dark-text pattern (see §2.5). Mobile enlarges to 44px for touch targets.

### 8.6 Buttons

| Variant | Class | Background | Text | Border |
| --- | --- | --- | --- | --- |
| Primary | `.btn-primary` | `--lf-dark-teal` | white | none |
| Outline | `.btn-outline` | transparent | `--lf-dark-teal` | 1px teal |
| Danger | `.btn-danger` | `--lf-risk-red` | white | none |

* Base: `min-height: 36px` (44px on mobile), `border-radius: 4px`
* Disabled: `opacity: 0.5`, `cursor: not-allowed`, `pointer-events: none`
* Focus: `2px solid dark-teal, 2px offset`

### 8.7 Score Gauge (inline)

```css
.score-gauge { display: inline-flex; align-items: center; gap: 8px; }
.gauge-bar { width: 60px (40px mobile); height: 8px; border-radius: 4px; background: platinum; }
.gauge-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
```

Fill color classes: `.excellent`, `.good`, `.fair`, `.poor`, `.failing`

### 8.8 Toast Notifications

* Fixed bottom-right, `z-index: 1000`
* Base: dark-teal bg, white text, dropdown shadow
* Variants: `.success` (green), `.error` (red)
* Slide-in animation: `translateX(100%) → translateX(0)`

### 8.9 Filter Bar

```css
.filter-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.filter-select { padding: 6px 12px; border-radius: 6px; border: 1px solid platinum; }
```

### 8.10 Data Source Badge

* Pill shape (16px radius), 11px uppercase
* `.mock`: amber tinted bg + amber text + amber dot
* `.live`: green tinted bg + green text + green dot
* `role="status"` for screen readers

---

## 9. Topology Components

### 9.1 Toolbar

* Sticky below header (`top: --header-height`), `z-index: 50`
* White background, card shadow, bottom radius
* Button groups with 1px platinum dividers
* All buttons 44×44px min (touch target)

### 9.2 Canvas

* `.topo-canvas-wrap`: platinum bg, 8px radius, min-height 500px (300px mobile)
* SVG fills 100% width/height

### 9.3 Nodes

* Region nodes: hover → orange stroke (3px), focus → dark-teal stroke (3px)
* Site nodes: same hover pattern
* SRLG highlight: `drop-shadow` pulse animation (2s ease-in-out, infinite)

### 9.4 Legend Panel

* Absolute bottom-left in canvas, card shadow
* Min 200px, max 280px
* Responsive: relative layout on tablet+
* Collapsible with collapse button

### 9.5 Detail Side Panel

* Absolute right, 400px width (100% on tablet, full-height on mobile)
* Slide-in animation (translateX)
* Sticky header with close button (44×44px)
* `role="dialog"`, auto-focus, Escape-to-close

### 9.6 Breadcrumb

* Flex row with separator chevrons
* Button links: teal text, hover teal 6% bg

---

## 10. Accessibility Checklist

### 10.1 Color & Contrast

* WCAG 2.1 AA minimum: 4.5:1 for normal text, 3:1 for large text
* Orange (#F26522) → large text/icons only on white (3.07:1)
* Always pair color with secondary cue (icon, pattern, text label)
* All badge text uses dark-on-tinted pattern for ≥4.5:1 ratio

### 10.2 Focus Management

* Global visible focus ring: `2px solid dark-teal, 2px offset`
* Header nav links: `2px solid white, 2px offset` (on dark bg)
* Escape key closes hamburger nav and detail panels
* Skip-nav link is first focusable element

### 10.3 Touch Targets

* Minimum: 44×44px on mobile for all interactive elements
* Desktop minimum: 24×24px (WCAG 2.5.8)
* Buttons: 36px min-height desktop → 44px mobile
* Rating pills: 28px desktop → 44px mobile
* Pagination buttons: 44×44px mobile

### 10.4 ARIA Patterns

| Pattern | ARIA | Where Used |
| --- | --- | --- |
| KPI card | `role="group"` + `aria-label="{Metric}: {Value}"` | scorecard-header |
| Navigation | `role="navigation"` + `aria-label="Main navigation"` | __root |
| Current page | `aria-current="page"` | active nav link |
| Hamburger | `aria-expanded`, `aria-controls`, `aria-label` | nav toggle |
| Sort header | `aria-sort="ascending\|descending\|none"` | table headers |
| Toggle switch | `role="switch"` + `aria-checked` | topology overlays |
| Loading skeleton | `aria-busy="true"` + `aria-label` | Suspense fallbacks |
| Detail panel | `role="dialog"` + auto-focus + Escape | topology panel |
| Data source | `role="status"` | header badge |
| Decorative icons | `aria-hidden="true"` | SVG decorations |
| Informational SVG | `role="img"` + `aria-label` | topology graph |

### 10.5 Motion

* `@media (prefers-reduced-motion: reduce)` — all animations/transitions set to 0.01ms
* Explicit disable for hazard-pulse animation
* Skeleton pulse, toast slide-in, panel slide-in all respect reduced-motion

### 10.6 Semantic HTML

* `<html lang="en">` set in root layout
* `<header role="banner">`, `<main role="main">`, `<nav>`
* `<section aria-label="...">` for each content section
* Descriptive `<title>` per route (WCAG 2.4.2)

---

## 11. Responsive Breakpoints

| Breakpoint | Width | Layout Changes |
| --- | --- | --- |
| XL (Desktop) | ≥ 1440px | `max-width: 1400px` centered container |
| Desktop | 1024–1439px | `max-width: 100%` full-width container |
| Tablet | 768–1023px | Hamburger nav, 2-col KPI grid, table horizontal scroll, full-width detail panel (50vh from bottom), relative legend |
| Mobile | < 768px | 1-col KPI grid, compact header (15px), full-height detail panel, 44px touch targets, compact toolbar, reduced canvas min-height (300px) |

---

## 12. Iconography

| Property | Value |
| --- | --- |
| Library | Lucide React |
| Stroke | 1.5px |
| Inline size | 16px |
| Button size | 20px |
| Standalone size | 24px |
| Color | Inherit from parent text |

Hazard icon sizing by severity:
* Critical: 24×24px + pulse animation (2s ease-in-out)
* Major: 20×20px
* Moderate/Minor: 16×16px

---

## 13. Animation Catalog

| Name | Duration | Easing | Usage |
| --- | --- | --- | --- |
| `hazard-pulse` | 2s | ease-in-out, infinite | Critical severity hazard icons |
| `srlg-pulse` | 2s | ease-in-out, infinite | SRLG highlight drop-shadow |
| `toast-slide-in` | 0.3s | ease | Toast notification entry |
| `panel-slide-in` | 0.2s | ease | Detail panel entry |
| `skeleton-pulse` | 1.5s | ease-in-out, infinite | Loading skeleton placeholders |

All animations are disabled under `prefers-reduced-motion: reduce`.

---

## 14. Naming Conventions

| Asset Type | Convention | Example |
| --- | --- | --- |
| CSS variables | `--lf-{semantic-name}` | `--lf-dark-teal`, `--lf-accent-orange` |
| CSS classes | lowercase kebab-case | `.kpi-card`, `.data-table`, `.topo-toolbar` |
| React components | PascalCase | `ScorecardHeader`, `ServiceTable`, `HazardCrosswalkTable` |
| Route files | lowercase kebab-case | `index.tsx`, `actions.tsx`, `hazards.tsx`, `topology.tsx` |
| API endpoints | `/api/{resource}` | `/api/scores`, `/api/actions`, `/api/health` |
| Utility classes | short kebab-case | `.ml-auto`, `.mt-lg`, `.mb-md`, `.text-sm`, `.text-caption` |

---

## 15. Forbidden Terms

| Forbidden | Replacement |
| --- | --- |
| Lumen | Lakelink Fiber |
| Lumen Technologies | Lakelink Fiber |
| `lumen` (in variable names) | `lf` or `lakelink` |
| `--lf-lumen-*` | `--lf-accent-*` or `--lf-{semantic}` |

---

## 16. File Inventory

| File | Lines | Purpose |
| --- | --- | --- |
| `lakelink-theme.css` | 1244 | Single CSS source of truth — all tokens, components, responsive rules |
| `__root.tsx` | 130 | App shell: header, nav, skip-nav, route titles, lang |
| `index.tsx` | 59 | Dashboard route: scorecard KPIs + hazard summary + service table + product catalog |
| `actions.tsx` | 33 | Action queue route |
| `hazards.tsx` | 45 | Hazard exposure crosswalk route |
| `topology.tsx` | ~800 | Network topology visualization route |
| `scorecard-header.tsx` | 111 | KPI header with Suspense + ErrorBoundary pattern |
| `service-table.tsx` | — | Per-service resilience table with score gauges |
| `action-queue-table.tsx` | — | Action queue with Lakebase state management |
| `hazard-crosswalk-*.tsx` | — | Hazard KPIs, summary table, crosswalk matrix |

---

## 17. Bug Tracker

### Resolved (verified 2026-10-23)

Filed session 16, fixed by @app-developer in P14-UX-TOPO-POLISH, verified by @designer session 17:

| Bug | Severity | Fix | Verification |
| --- | --- | --- | --- |
| BUG-DW-042 | Medium | `.detail-label` → `#5c5c5c` (5.12:1) | CSS line 1184 ✅ |
| BUG-DW-043 | Medium | `.legend-section-title` → `#5c5c5c` (5.12:1) | CSS line 1038 ✅ |
| BUG-DW-044 | Medium | `.topo-legend-collapse-btn` padding 6px 4px, min-height 24px | CSS line 1069-1070 ✅ |
| BUG-DW-045 | Low | Extracted to `.panel-section-title`, `.panel-conduit-item` classes | CSS lines 1244-1264 ✅ |
| BUG-DW-046 | Low | Extracted to `.topo-loading` class | CSS lines 1266-1274 ✅ |

### Open

None. All known bugs are resolved.

---

*This document is the canonical reference for all Lakelink Fiber UX work. When in doubt, match the patterns here. @designer findings based on this system are binding.*
