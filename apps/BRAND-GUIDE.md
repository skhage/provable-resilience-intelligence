# Lakelink Fiber — Brand Guide
## Provable Resilience Intelligence Project

**Author:** @designer · **Date:** 2026-10-20 · **Status:** BINDING  
**Scope:** All project assets — apps, dashboards, notebooks, Genie spaces, metric views, documentation  
**CEO Directive:** Never use "Lumen" or "Lumen Technologies". All assets use **"Lakelink Fiber"**.

---

## 1. Brand Identity

**Company:** Lakelink Fiber  
**Tagline:** Provable Resilience Intelligence  
**Voice:** Technical, confident, precise. Data-driven, not aspirational. Use concrete metrics over vague assurances.

---

## 2. Color System

### 2.1 Primary Palette

| Swatch | Name | Hex | CSS Variable | Usage |
| --- | --- | --- | --- | --- |
| 🟢 | Dark Teal | `#006272` | `--lf-dark-teal` | Primary brand. Headers, nav, buttons, link text, headings |
| ⬜ | Platinum | `#E8E8E8` | `--lf-platinum` | Backgrounds, card surfaces, dividers, stripe rows |
| ⬛ | Iron | `#4D4D4D` | `--lf-iron` | Body text, secondary labels, captions |
| 🟠 | Accent Orange | `#F26522` | `--lf-accent-orange` | Alerts, critical badges, CTAs. **Large text/icons only on white** |
| ⬜ | White | `#FFFFFF` | `--lf-white` | Text on dark backgrounds, card backgrounds |

### 2.2 Extended Teal Ramp

| Name | Hex | CSS Variable | Usage |
| --- | --- | --- | --- |
| Teal Light | `#00839A` | `--lf-dark-teal-light` | Hover states, secondary accents |
| Teal Dark | `#004D5A` | `--lf-dark-teal-hover` | Active/pressed states, depth |

### 2.3 Risk / Severity Palette

| Severity | Hex | CSS Variable | Background Tint |
| --- | --- | --- | --- |
| Critical | `#D32F2F` | `--lf-risk-red` | `#FEE2E2` |
| High | `#F26522` | `--lf-accent-orange` | `#FFEDD5` |
| Medium | `#F9A825` | `--lf-risk-amber` | `#FEF3C7` |
| Low / Healthy | `#2E7D32` | `--lf-risk-green` | `#DCFCE7` |

### 2.4 Resilience Score Gradient

| Rating | Hex | CSS Variable | Score Range |
| --- | --- | --- | --- |
| Excellent | `#2E7D32` | `--score-excellent` | ≥ 85 |
| Good | `#65A30D` | `--score-good` | 70–84 |
| Fair | `#F9A825` | `--score-fair` | 55–69 |
| Poor | `#EA580C` | `--score-poor` | 40–54 |
| Failing | `#D32F2F` | `--score-failing` | < 40 |

### 2.5 Path Diversity Ratings

| Grade | Color | Description |
| --- | --- | --- |
| A | `#16A34A` | Fully diverse — no shared conduit, SRLG, or site risk |
| B | `#65A30D` | Diverse with minor shared infrastructure |
| C | `#D97706` | Partial diversity — some shared risk |
| D | `#EA580C` | Poor diversity — significant shared risk |
| F | `#DC2626` | No diversity — single path or critical SRLG overlap |

### 2.6 Contrast Requirements (WCAG 2.1 AA)

| Pairing | Ratio | Verdict |
| --- | --- | --- |
| Dark Teal on White | 7.14:1 | ✅ AAA |
| Iron on White | 7.75:1 | ✅ AAA |
| White on Dark Teal | 7.14:1 | ✅ AAA |
| Orange on White | 3.07:1 | ⚠️ Large text only (≥18pt bold or ≥24pt) |
| Critical Red on White | 5.73:1 | ✅ AA |
| Healthy Green on White | 5.92:1 | ✅ AA |

**Rules:**
* Orange `#F26522` MUST NOT be used for normal-size text on white
* Always pair color with a secondary cue (icon, pattern, text label) — never rely on color alone
* All interactive elements need visible focus ring (2px solid dark-teal, 2px offset)

---

## 3. Typography

| Role | Font | Weight | Size | Line Height | Color |
| --- | --- | --- | --- | --- | --- |
| H1 (page title) | Inter | 700 | 28px | 1.3 | Dark Teal |
| H2 (section) | Inter | 600 | 22px | 1.35 | Dark Teal |
| H3 (card title) | Inter | 600 | 18px | 1.4 | Iron |
| Body | Inter | 400 | 14px | 1.5 | Iron |
| Caption / Label | Inter | 500 | 12px | 1.4 | Iron @ 80% opacity |
| Monospace (IDs, codes) | JetBrains Mono | 400 | 13px | 1.4 | Iron |

**Font stack:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`  
**Mono stack:** `'JetBrains Mono', 'Fira Code', monospace`

---

## 4. Spacing & Layout

**Base unit:** 4px

| Token | Value | CSS Variable |
| --- | --- | --- |
| xs | 4px | `--space-xs` |
| sm | 8px | `--space-sm` |
| md | 16px | `--space-md` |
| lg | 24px | `--space-lg` |
| xl | 32px | `--space-xl` |
| xxl | 48px | `--space-xxl` |

**Border Radius:** `--radius: 8px` (cards, buttons, badges)  
**Container:** max-width 1400px, centered  
**Header:** 56px height, sticky, dark-teal background  

---

## 5. Elevation

| Level | Shadow | Usage |
| --- | --- | --- |
| Card | `0 1px 3px rgba(0,0,0,0.08)` | KPI cards, data tables |
| Dropdown | `0 4px 12px rgba(0,0,0,0.12)` | Menus, popovers |
| Modal | `0 8px 24px rgba(0,0,0,0.16)` | Dialogs, overlays |

---

## 6. Iconography

**Library:** Lucide React  
**Stroke:** 1.5px  
**Size:** 16px inline, 20px in buttons, 24px standalone  
**Color:** Inherit from parent text color

---

## 7. Component Patterns

### KPI Cards
* Left border: 4px, colored by severity/score
* Background: white on platinum page background
* Structure: label (caption) → value (H2 size, teal) → optional trend delta

### Data Tables
* Sticky header: dark-teal background, white text, uppercase 12px labels
* Alternating rows: white / platinum
* Hover: teal at 5% opacity
* Sortable: visible ▲/▼ indicator

### Badges
* Pill shape (border-radius: 12px)
* Tinted background + saturated text (see §2.3)
* Uppercase, 12px, 600 weight

### Buttons
* Primary: dark-teal fill, white text
* Outline: transparent fill, teal border + text
* Danger: critical-red fill, white text
* Minimum touch target: 44×44px on mobile

---

## 8. Dashboard Applications

Dashboards built in AI/BI use the same color system:
* Header markdown: reference Lakelink Fiber, use `#006272` for emphasis
* Chart palette: `#006272` → `#F26522` → `#16A34A` → `#6B7280` → `#00839A`
* KPI counters: teal for positive, red for critical
* Every dashboard MUST embed a Genie agent (CEO semantic modeling mandate)

---

## 9. Naming Conventions

| Asset | Pattern | Example |
| --- | --- | --- |
| CSS variables | `--lf-{semantic-name}` | `--lf-dark-teal`, `--lf-accent-orange` |
| CSS classes | lowercase kebab-case | `.kpi-card`, `.data-table` |
| React components | PascalCase | `ScorecardHeader`, `ServiceTable` |
| API endpoints | `/api/{resource}` | `/api/scores`, `/api/actions` |
| Dashboard title | "Lakelink Fiber — {Subtitle}" | "Lakelink Fiber — Provable Resilience Scorecard" |
| Genie space | "{Audience} Resilience Intelligence" | "Service Assurance Resilience Intelligence" |

---

## 10. Forbidden Terms

Per CEO branding mandate, the following MUST NEVER appear in any produced asset:

| Forbidden | Replacement |
| --- | --- |
| Lumen | Lakelink Fiber |
| Lumen Technologies | Lakelink Fiber |
| lumen (in variable names) | lf or lakelink |
| --lf-lumen-* | --lf-accent-* or --lf-{semantic} |

---

## 11. Accessible Text Colors (§2.7)

**Added 2026-10-20 Session 5** — All computed ratios verified against WCAG 2.1 AA (≥4.5:1 normal text).

### 11.1 Badge Severity Text (dark-on-tinted)

The raw risk colors from §2.3 fail WCAG AA when used as small text on their tinted backgrounds.
Use these darker variants for badge text (12px/600 weight):

| Badge | Text Hex | CSS Variable | Background | Ratio |
| --- | --- | --- | --- | --- |
| Critical | `#991B1B` | `--lf-risk-red-dark` | `#FEE2E2` | 6.80:1 ✅ |
| High | `#9A3412` | `--lf-risk-orange-dark` | `#FFEDD5` | 6.38:1 ✅ |
| Medium | `#92400E` | `--lf-risk-amber-dark` | `#FEF3C7` | 6.37:1 ✅ |
| Low | `#166534` | (existing `--lf-risk-green` works) | `#DCFCE7` | 6.49:1 ✅ |

### 11.2 Path Diversity Rating Pills (tinted pattern)

Switch from solid-bg + white-text to tinted-bg + dark-text for WCAG compliance:

| Grade | Text Hex | Background Hex | Ratio |
| --- | --- | --- | --- |
| A | `#166534` | `#DCFCE7` | 6.49:1 ✅ |
| B | `#3F6212` | `#ECFCCB` | 6.52:1 ✅ |
| C | `#92400E` | `#FEF3C7` | 6.37:1 ✅ |
| D | `#9A3412` | `#FFEDD5` | 6.38:1 ✅ |
| F | `#991B1B` | `#FEE2E2` | 6.80:1 ✅ |

### 11.3 Brand Accent on Dark Header

Orange `#F26522` on dark-teal `#006272` = 2.23:1 — **fails ALL WCAG levels**.
Use one of these for the `.brand-accent` text on the dark-teal header:

| Option | Hex | Ratio | Notes |
| --- | --- | --- | --- |
| **Recommended:** Warm light orange | `#FFCC80` | 4.75:1 ✅ AA | Retains orange brand warmth |
| Safe fallback: White | `#FFFFFF` | 7.02:1 ✅ AAA | Maximum contrast |
| Alternative: Platinum | `#E8E8E8` | 5.73:1 ✅ AA | Subtle differentiation |

---

*This brand guide is a living document. @designer reviews are authoritative — deviations require written @designer approval.*
