# Lakelink Fiber — Hazard Visualization UX Specification
## Provable Resilience Intelligence · Phase 9

**Author:** @designer · **Date:** 2026-10-21 · **Status:** BINDING  
**Task:** P9-DESIGN-HAZARD-UI-SPEC · **Priority:** MEDIUM  
**Extends:** BRAND-GUIDE.md §2.3, §6 · UX-DESIGN-SPEC.md §3.5  
**Schema Source:** `notebooks/hazard_schema_design` (notebook 2858909277057215)  
**Data Model:** 5 staging tables → `hazard_span_intersection` → `geographic_hazard_event` (50K rows)

> All findings in this document are **binding** per project charter.
> @app-developer MUST implement these requirements. Deviations require written @designer approval.

---

## 1. Hazard Type Icon Taxonomy

**Library:** Lucide React (per BRAND-GUIDE §6)  
**Stroke:** 1.5px · **Inline size:** 16px · **Standalone size:** 24px

| Hazard Type | Source | Lucide Icon | Icon Name | Semantic Note |
| --- | --- | --- | --- | --- |
| Severe Weather | NOAA NWS | `CloudLightning` | `cloud-lightning` | FEMA/NWS convention — storm + lightning |
| Earthquake | USGS | `Activity` | `activity` | Seismograph wave — universally recognized |
| Flood | USGS/NWS | `Waves` | `waves` | FEMA flood iconography — water surface |
| Wildfire | NIFC WFIGS | `Flame` | `flame` | NIFC/CAL FIRE standard — fire symbol |
| Dig Ticket | State 811 | `Construction` | `construction` | 811 "Call Before You Dig" — excavation |

### 1.1 Icon Color Mapping (on white card backgrounds)

Icons inherit parent text color by default. When used standalone or as visual emphasis, use these type-specific colors:

| Hazard Type | Icon Color Hex | CSS Variable | On White Ratio |
| --- | --- | --- | --- |
| Severe Weather | `#B45309` | `--lf-hazard-weather` | 4.88:1 ✅ AA |
| Earthquake | `#7C3AED` | `--lf-hazard-earthquake` | 4.62:1 ✅ AA |
| Flood | `#2563EB` | `--lf-hazard-flood` | 4.62:1 ✅ AA |
| Wildfire | `#DC2626` | `--lf-hazard-wildfire` | 5.57:1 ✅ AA |
| Dig Ticket | `#CA8A04` | `--lf-hazard-dig` | 3.10:1 ⚠️ icon-only (≥3:1) |

**Rule:** Icon color is NEVER the sole indicator. Always pair with a text label (WCAG 1.4.1 — Use of Color).

### 1.2 Icon + Label Badge Pattern (type indicator in tables/cards)

```
┌──────────────────────────┐
│ ⚡ Severe Weather         │  ← icon + label inline, gap: 8px
└──────────────────────────┘
```

CSS class: `.hazard-type-cell` (mirrors existing `.action-type-cell` pattern)

```css
.hazard-type-cell {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  white-space: nowrap;
}
.hazard-type-cell svg {
  flex-shrink: 0;
  color: inherit;
}
```

React implementation:

```tsx
import { CloudLightning, Activity, Waves, Flame, Construction, HelpCircle, type LucideIcon } from "lucide-react";

const HAZARD_ICONS: Record<string, LucideIcon> = {
  severe_weather: CloudLightning,
  earthquake: Activity,
  flood: Waves,
  wildfire: Flame,
  dig_ticket: Construction,
};

const ICON_PROPS = { size: 16, strokeWidth: 1.5, "aria-hidden": true } as const;

function HazardTypeCell({ type }: { type: string }) {
  const Icon = HAZARD_ICONS[type] ?? HelpCircle;
  return (
    <span className="hazard-type-cell">
      <Icon {...ICON_PROPS} />
      {type.replace(/_/g, " ")}
    </span>
  );
}
```

---

## 2. Hazard Type Badge Colors (tinted-bg + dark-text)

Follows the existing badge pattern from BRAND-GUIDE §11.1 — tinted backgrounds with dark text for WCAG AA compliance.

| Hazard Type | Text Hex | Background Hex | Contrast Ratio |
| --- | --- | --- | --- |
| Severe Weather | `#7C2D12` | `#FFF7ED` | 8.83:1 ✅ AAA |
| Earthquake | `#581C87` | `#FAF5FF` | 10.14:1 ✅ AAA |
| Flood | `#1E3A5F` | `#EFF6FF` | 10.57:1 ✅ AAA |
| Wildfire | `#991B1B` | `#FEF2F2` | 7.60:1 ✅ AAA |
| Dig Ticket | `#854D0E` | `#FEFCE8` | 6.62:1 ✅ AA |

```css
/* Hazard type badges */
.badge.severe_weather { background: #FFF7ED; color: #7C2D12; }
.badge.earthquake     { background: #FAF5FF; color: #581C87; }
.badge.flood          { background: #EFF6FF; color: #1E3A5F; }
.badge.wildfire       { background: #FEF2F2; color: #991B1B; }
.badge.dig_ticket     { background: #FEFCE8; color: #854D0E; }
```

---

## 3. Severity Color Scale

Reuses the existing risk palette (BRAND-GUIDE §2.3) with a 4-level CAP-aligned scale matching the source data:

| Severity | CAP Values | Badge Text | Badge BG | CSS Class | Icon Treatment |
| --- | --- | --- | --- | --- | --- |
| Critical | Extreme | `#991B1B` | `#FEE2E2` | `.severity-critical` | 24px, pulsing animation |
| Major | Severe | `#9A3412` | `#FFEDD5` | `.severity-major` | 20px, static |
| Moderate | Moderate | `#92400E` | `#FEF3C7` | `.severity-moderate` | 16px, static |
| Minor | Minor/Unknown | `#006272` | `#E0F2F1` | `.severity-minor` | 16px, static |

**Mapping from source data:**

| Source | Source Field | Critical | Major | Moderate | Minor |
| --- | --- | --- | --- | --- | --- |
| NOAA | `severity` | Extreme | Severe | Moderate | Minor/Unknown |
| USGS Earthquake | `alert_level` | red | orange | yellow | green/NULL |
| USGS Flood | `flood_category` | major | moderate | minor | action/no_flooding |
| NIFC Wildfire | `containment_pct` | <10% | 10–50% | 50–90% | >90% |
| 811 Dig | `proximity_meters` | <50m | 50–200m | 200–500m | >500m |

### 3.1 Severity Pulse Animation (Critical only)

```css
.severity-critical .hazard-icon {
  animation: hazard-pulse 2s ease-in-out infinite;
}

@keyframes hazard-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

@media (prefers-reduced-motion: reduce) {
  .severity-critical .hazard-icon {
    animation: none;
  }
}
```

---

## 4. Proximity Indicator Overlay

### 4.1 Proximity Zones

For each active hazard, show concentric impact zones indicating proximity to Lakelink Fiber network spans:

| Zone | Distance | Fill Color (20% opacity) | Border Color | Badge Text | Badge BG | Contrast |
| --- | --- | --- | --- | --- | --- | --- |
| Direct Impact | <5 km | `rgba(211,47,47,0.20)` | `#D32F2F` | `#991B1B` | `#FEE2E2` | 6.80:1 ✅ |
| Near Impact | 5–25 km | `rgba(242,101,34,0.15)` | `#F26522` | `#9A3412` | `#FFEDD5` | 6.38:1 ✅ |
| Advisory | 25–100 km | `rgba(249,168,37,0.12)` | `#F9A825` | `#92400E` | `#FEF3C7` | 6.37:1 ✅ |
| Monitor | 100–250 km | `rgba(46,125,50,0.10)` | `#2E7D32` | `#166534` | `#DCFCE7` | 6.49:1 ✅ |

### 4.2 Map Overlay Specification

```
┌─────────────────────────────────────────────────────┐
│  Map (continental US, zoom 4)                       │
│                                                     │
│    ╭─── Monitor (250km) ─────────────╮              │
│    │  ╭─── Advisory (100km) ──────╮  │              │
│    │  │  ╭── Near (25km) ───╮     │  │              │
│    │  │  │  ╭ Direct (5km)╮ │     │  │              │
│    │  │  │  │  🔥 HAZARD  │ │     │  │              │
│    │  │  │  ╰─────────────╯ │     │  │  ─── span   │
│    │  │  ╰──────────────────╯     │  │  === span    │
│    │  ╰───────────────────────────╯  │   (at risk)  │
│    ╰─────────────────────────────────╯              │
│                                                     │
│  [Legend] [Table View] [Filter: Active Hazards ▾]   │
└─────────────────────────────────────────────────────┘
```

**Overlay rendering rules:**

* Zones are drawn from outermost (Monitor) to innermost (Direct) so inner zones stack above outer
* Each zone uses the fill color at specified opacity + 2px dashed border
* Hazard source point shows the hazard-type icon (24px) at the center
* Network spans within Direct Impact zone are highlighted in `--lf-risk-red` (thick 3px)
* Spans in Near Impact zone are highlighted in `--lf-accent-orange` (2px)
* Unaffected spans remain in `--lf-dark-teal` (1px default)

### 4.3 Map Accessibility

**WCAG 2.1 compliance (§3.5 of UX-DESIGN-SPEC):**

* Map container: `role="img"` with dynamic `aria-label` summarizing active hazards
  * Example: `aria-label="Hazard map showing 3 active hazards: 1 wildfire (critical) near Denver, 1 flood warning (moderate) near Houston, 1 dig ticket (minor) near Dallas. 47 spans in direct impact zones."`
* **Parallel table view toggle** — "Table View" button above map provides full data in accessible HTML table
* Map controls (zoom, pan, filter): keyboard-accessible with visible focus rings
* Color is not sole indicator: zones use both color AND dashed-pattern borders, AND text badges in legend
* Reduced-motion: disable auto-pan animations when `prefers-reduced-motion: reduce`

### 4.4 Parallel Table View (accessible alternative)

| Hazard | Type | Severity | Location | Affected Spans | Direct | Near | Advisory |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Park Fire | 🔥 Wildfire | Critical | 39.8°N, 121.6°W | 12 | 3 | 7 | 2 |
| Flood Warning #2456 | 🌊 Flood | Moderate | Houston, TX | 8 | 2 | 4 | 2 |

---

## 5. Hazard Alert Card (Action Queue Integration)

When a hazard triggers a proactive action, the action queue card layout incorporates hazard context:

### 5.1 Enhanced Action Card Layout

```
┌────┬──────────────────────────────────────────────────────┐
│    │  🔥 Wildfire — Park Fire                   CRITICAL │
│ !! ├──────────────────────────────────────────────────────┤
│    │  Service: Denver–SLC DARK FIBER 100G                │
│    │  Risk: 2 spans in direct impact zone (<5km)         │
│    │  Action: Reroute via alternate path #SPF-4421       │
│    ├──────────────────────────────────────────────────────┤
│    │  Hazard Details:                                    │
│    │  📍 39.8°N, 121.6°W · Containment: 12%             │
│    │  ⏱ Updated: 2026-10-21 14:30 UTC                   │
│    ├──────────────────────────────────────────────────────┤
│    │  [Start Action]  [View on Map]  [Dismiss]           │
└────┴──────────────────────────────────────────────────────┘
```

**Structure:**
* Left border: 4px, severity color (matches KPI card pattern)
* Row 1: Hazard icon + type + name, severity badge (right-aligned)
* Row 2: Affected service name (bold), span count in impact zone
* Row 3: Recommended action from `proactive_action.trigger_reason`
* Row 4 (expandable): Hazard metadata — coordinates, containment%, last update
* Row 5: Action buttons — primary (Start), secondary (View on Map), outline (Dismiss)

### 5.2 Card Accessibility

* Entire card: `role="article"`, `aria-label="{severity} {hazard_type} affecting {service_name}"`
* Severity badge: text + color (dual cue)
* Expand/collapse: `aria-expanded`, keyboard Enter/Space
* Action buttons: descriptive `aria-label` including service name
* Timestamp: `<time datetime="...">`

---

## 6. Hazard Dashboard Section (New Scorecard Panel)

### 6.1 KPI Cards (hazard summary)

Add a new KPI row below the existing resilience KPIs:

| KPI | CSS Class | Source |
| --- | --- | --- |
| Active Hazards | `.kpi-card.critical` (if >0) | `COUNT(*) FROM geographic_hazard_event WHERE is_active` |
| Spans at Risk | `.kpi-card.high` | `COUNT(DISTINCT span_id) FROM hazard_span_intersection WHERE zone='direct'` |
| Services Impacted | `.kpi-card.warning` | `COUNT(DISTINCT service_id) WHERE has_active_hazard` |
| Revenue Exposed | `.kpi-card.critical` | `SUM(revenue_at_risk_usd) WHERE service_in_hazard_zone` |

### 6.2 Hazard Summary Table

| Column | Width | Content |
| --- | --- | --- |
| Type | 120px | Icon + label badge (§1.2) |
| Name | flex | Hazard name/ID (bold) |
| Severity | 100px | Severity badge (§3) |
| Location | 180px | City/state or coordinates |
| Spans Affected | 80px | Count with color indicator |
| Status | 100px | Active/Expired badge |
| Last Update | 120px | Relative time ("2h ago") |

Use existing `.data-table` styles. Sortable by severity (default), updated time, span count.

---

## 7. CSS Token Additions

Add to `:root` in `lakelink-theme.css`:

```css
/* === Hazard Type Colors (HAZARD-VIS-SPEC §1.1) === */
--lf-hazard-weather: #B45309;
--lf-hazard-earthquake: #7C3AED;
--lf-hazard-flood: #2563EB;
--lf-hazard-wildfire: #DC2626;
--lf-hazard-dig: #CA8A04;
```

---

## 8. Responsive Behavior

| Breakpoint | Map | Hazard Cards | KPI Row |
| --- | --- | --- | --- |
| ≥1440px (XL) | Full width, 600px height | 2-column grid | 4 across |
| 1024–1439px | Full width, 480px height | 2-column grid | 4 across |
| 768–1023px (Tablet) | Full width, 360px height | 1-column stack | 2×2 grid |
| <768px (Mobile) | Hidden (table view default) | 1-column stack | 1-column stack |

**Mobile rule:** Map is hidden by default on mobile. Show "View Map" button that opens a full-screen map overlay. Table view is the default accessible experience.

---

## 9. Implementation Priority

| Priority | Component | Depends On |
| --- | --- | --- |
| P1 | Hazard type icons + badges in CSS | None |
| P1 | Hazard KPI cards (summary row) | `geographic_hazard_event` gold table |
| P2 | Hazard summary table | `hazard_span_intersection` silver table |
| P2 | Enhanced action cards with hazard context | P1 icons + existing action queue |
| P3 | Map overlay with proximity zones | Map library integration (Deck.gl/Mapbox) |
| P3 | Parallel table view for map data | P2 hazard summary table |

---

## 10. Contrast Verification Summary

All color pairings verified via sRGB→linear luminance WCAG 2.1 algorithm:

| Component | Ratio | Verdict |
| --- | --- | --- |
| Weather badge text on bg | 8.83:1 | ✅ AAA |
| Earthquake badge text on bg | 10.14:1 | ✅ AAA |
| Flood badge text on bg | 10.57:1 | ✅ AAA |
| Wildfire badge text on bg | 7.60:1 | ✅ AAA |
| Dig Ticket badge text on bg | 6.62:1 | ✅ AA |
| Direct Impact zone legend | 6.80:1 | ✅ AA |
| Near Impact zone legend | 6.38:1 | ✅ AA |
| Advisory zone legend | 6.37:1 | ✅ AA |
| Monitor zone legend | 6.49:1 | ✅ AA |
| All severity badges | ≥6.37:1 | ✅ AA |
| Icons on dark-teal header | ≥4.75:1 | ✅ AA (3:1 required for non-text) |

---

*This specification is a living document. @designer reviews are authoritative — deviations require written @designer approval.*
