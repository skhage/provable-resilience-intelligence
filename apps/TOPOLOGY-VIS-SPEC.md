# Lakelink Fiber — Network Topology Visualization UX Specification
## Provable Resilience Intelligence · Phase 12

**Author:** @designer · **Date:** 2026-10-22 · **Status:** BINDING  
**Task:** P12-DESIGN-TOPOLOGY-SPEC · **Priority:** MEDIUM  
**Extends:** BRAND-GUIDE.md §2.5, §7 · UX-DESIGN-SPEC.md §3.5 · HAZARD-VIS-SPEC.md §4  
**Data Model:** geographic_site (2,969) → physical_resource_conduit (1,969) → physical_resource_span (10,092) → shared_risk_group (12,235) → service_path (54,572 hops across 8,000 services)  
**Assessment Ref:** P12-TOPOLOGY-GRAPH-ASSESSMENT — @data-analyst recommended deferring tmf_resource.topology_graph integration to Release C. This spec designs against the **existing physical path model** exclusively.

> All findings in this document are **binding** per project charter.  
> @app-developer MUST implement these requirements. Deviations require written @designer approval.

---

## 0. Scope & Rationale

The Resilience Scorecard currently presents service-level scores, hazard exposure tables, and an action queue — all in tabular or KPI-card form. What it lacks is a **spatial/structural view** of the physical network that lets operators answer:

* "Where does this service's path physically run?"
* "Which conduits share risk (SRLGs)?"
* "Does this service have true path diversity, or do working and protect paths share a bridge?"
* "Which spans near this wildfire are carrying the most critical services?"

This spec defines a **Network Topology Graph View** — a new route/tab in the resilience-scorecard app — that renders the physical layer as an interactive node-link diagram overlaid with hazard zones.

**Data source:** The existing PRI physical path model (geographic_site → conduit → span → SRLG → service_path). NOT the tmf_resource.topology_graph/connection_point tables (see P12-TOPOLOGY-GRAPH-ASSESSMENT: abstraction mismatch, direction homogeneity, no FK bridge to spans).

---

## 1. Graph Layout Approach

### 1.1 Layout Selection: Hierarchical Layered (Sugiyama-style)

**Decision: Hierarchical over force-directed.**

Rationale:
* Physical network topology is inherently layered: CO/DC sites are backbone nodes, conduits are inter-site edges, spans are the fiber strands within conduits, and services traverse specific hop sequences.
* Force-directed layouts produce unpredictable positions on each render, making it hard for operators to build spatial memory of their network.
* Hierarchical layout preserves geographic region grouping (West → Central → East → Southeast) and tier ordering (tier_1 backbone → tier_2 regional → tier_3 access).

**Layout engine:** [D3-dag](https://github.com/erikbrinkman/d3-dag) or [ELK.js](https://github.com/kieler/elkjs) (Sugiyama/layered algorithm). Both are tree-shaking friendly and SSR-safe.

### 1.2 Node Hierarchy

| Layer | Entity | Node Shape | Size (px) | Icon |
| --- | --- | --- | --- | --- |
| L0 — Region | Lakelink Fiber region | Rounded rect | 160×48 | `Globe` (Lucide) |
| L1 — Backbone Site | tier_1 CO/DC (424 COs, 415 DCs) | Circle | 40 diam | `Building2` (Lucide) |
| L2 — Regional Site | tier_2 CO/DC | Circle | 28 diam | `Building` (Lucide) |
| L3 — Access Site | tier_3 hut / customer_premise (2,130) | Diamond | 20 diam | `Radio` (Lucide) |

**Node colors:** Fill `--lf-white`, stroke `--lf-dark-teal` (default). Active-selection highlight: stroke `--lf-accent-orange` (3px). Inactive/disabled: stroke `--lf-platinum`.

### 1.3 Edge Representation

| Edge Type | Entity | Stroke Style | Width | Color |
| --- | --- | --- | --- | --- |
| Conduit | physical_resource_conduit | Solid | 3px | `--lf-dark-teal` |
| Span (working path) | span via service_path (path_type=working) | Solid | 2px | Score-based (§2) |
| Span (protect path) | span via service_path (path_type=protect) | Dashed (8,4) | 2px | Score-based (§2) |
| SRLG link | shared_risk_group membership | Dotted (2,4) | 1px | `--lf-risk-red` at 40% opacity |

**Edge bundling:** When multiple spans share a conduit, bundle them into a single conduit edge with a strand-count badge. Click to expand into individual span edges.

### 1.4 Interaction Model

| Gesture | Desktop | Tablet | Mobile |
| --- | --- | --- | --- |
| Pan | Click-drag on canvas | Two-finger drag | Two-finger drag |
| Zoom | Scroll wheel / +/− buttons | Pinch | Pinch |
| Select node | Click | Tap | Tap |
| Select edge | Click | Tap | N/A (detail panel) |
| Multi-select | Shift+click | N/A | N/A |
| Context menu | Right-click | Long-press | N/A |
| Reset view | "Fit" button | "Fit" button | "Fit" button |

---

## 2. Diversity Status Color Coding

### 2.1 Service Path Diversity Classification

Every service has a diversity status based on its working and protect paths. The dataset shows 5,605 single-path (70%) and 2,395 dual-path (30%) services.

| Status | Description | Span Edge Color | Badge Text | Badge BG | Contrast |
| --- | --- | --- | --- | --- | --- |
| Fully Diverse | Working + protect paths share NO conduit, SRLG, or site | `#16A34A` | `#166534` | `#DCFCE7` | 6.49:1 ✅ |
| Partially Diverse | Working + protect exist but share ≥1 SRLG or conduit | `#D97706` | `#92400E` | `#FEF3C7` | 6.37:1 ✅ |
| Single Path | No protect path — service has only working path | `#DC2626` | `#991B1B` | `#FEE2E2` | 6.80:1 ✅ |
| Unknown | Path data incomplete or service unmapped | `#9CA3AF` | `#4B5563` | `#F3F4F6` | 7.48:1 ✅ |

CSS variables (extend lakelink-theme.css):

```css
/* Diversity status (TOPOLOGY-VIS-SPEC §2.1) */
--lf-diversity-full: #16A34A;
--lf-diversity-partial: #D97706;
--lf-diversity-single: #DC2626;
--lf-diversity-unknown: #9CA3AF;
```

### 2.2 Path Diversity Grading (BRAND-GUIDE §2.5)

The existing A–F grading system from BRAND-GUIDE §2.5 applies to node-level rollups (sites, conduits). The per-span coloring above applies to edges.

| Grade | Meaning | Node Border Color |
| --- | --- | --- |
| A | Fully diverse — no shared conduit, SRLG, or site risk | `#16A34A` (3px solid) |
| B | Diverse with minor shared infrastructure | `#65A30D` (3px solid) |
| C | Partial diversity — some shared risk | `#D97706` (3px solid) |
| D | Poor diversity — significant shared risk | `#EA580C` (3px solid) |
| F | No diversity — single path or critical SRLG overlap | `#DC2626` (3px solid) |

### 2.3 Color-Blindness Safety

Color is NEVER the sole means of conveying diversity status (WCAG 1.4.1):

* **Edges:** Solid (working) vs dashed (protect) line style distinguishes path type regardless of color.
* **Badges:** Text label always accompanies the color ("Fully Diverse", "Single Path", etc.).
* **Nodes:** Grade letter (A–F) rendered inside the node circle in addition to border color.
* **Patterns:** Optional: stripe pattern overlay on edges for deuteranopia/protanopia simulation mode (toggle in accessibility panel).

---

## 3. SRLG Visualization

### 3.1 Shared Risk Group Indicators

SRLGs are the core insight — showing where supposedly independent paths share physical risk.

| SRLG Type | Count | Icon (Lucide) | Color |
| --- | --- | --- | --- |
| Shared Conduit | 9,998 | `Cable` | `--lf-iron` |
| Bridge | 1,115 | `BridgeIcon` (custom SVG) | `--lf-risk-amber` |
| Rail Crossing | 565 | `TrainFront` | `--lf-risk-amber` |
| Power Feed | 286 | `Zap` | `--lf-accent-orange` |
| Tunnel | 252 | `Cylinder` | `--lf-iron` |
| Central Office | 19 | `Building2` | `--lf-risk-red` |

### 3.2 SRLG Highlight Mode

When an operator clicks an SRLG badge or selects "Show SRLGs" toggle:

1. All spans in the selected SRLG are highlighted with a **pulsing glow** (4px `box-shadow` in the SRLG severity color).
2. Non-member spans fade to 20% opacity.
3. An SRLG detail card appears in the side panel: type, severity, member span count, affected services, geographic coordinates.
4. If SRLG severity is `critical`: red pulse animation (reuses HAZARD-VIS-SPEC §3.1 `hazard-pulse` keyframes). Respects `prefers-reduced-motion`.

```css
.srlg-highlight {
  filter: drop-shadow(0 0 4px var(--srlg-color));
  animation: srlg-pulse 2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .srlg-highlight { animation: none; }
}

@keyframes srlg-pulse {
  0%, 100% { filter: drop-shadow(0 0 4px var(--srlg-color)); }
  50% { filter: drop-shadow(0 0 8px var(--srlg-color)); }
}
```

---

## 4. Hazard Overlay Integration

### 4.1 Reuse HAZARD-VIS-SPEC §4 Proximity Zones

Hazard overlays from HAZARD-VIS-SPEC §4 apply directly to the topology graph. When "Hazard Overlay" toggle is active:

* **Direct Impact (<5km):** Affected spans rendered in `--lf-risk-red` (3px, overrides diversity color). Affected nodes get a red glow ring.
* **Near Impact (5–25km):** Spans rendered in `--lf-accent-orange` (2px).
* **Advisory (25–100km):** Subtle amber tint on canvas region.
* **Monitor (100–250km):** Dashed boundary only (no span coloring).

### 4.2 Hazard Marker Nodes

Active hazards appear as special overlay nodes positioned by their lat/lon:

| Element | Shape | Size | Styling |
| --- | --- | --- | --- |
| Hazard marker | Hexagon | 32px | Fill: hazard-type color at 20% opacity, stroke: hazard-type color at 100% |
| Hazard icon | Lucide icon per HAZARD-VIS-SPEC §1 | 16px | Centered in hexagon |
| Proximity ring | Dashed circle | Scaled to proximity zone | Stroke: zone color (HAZARD-VIS-SPEC §4.1) |

### 4.3 Hazard + Diversity Compound View

When both overlays are active, hazard coloring takes precedence over diversity coloring on affected spans (safety-critical information wins). A secondary indicator (small colored dot at span midpoint) preserves the diversity status information.

**Priority stack:** Hazard Impact > SRLG Highlight > Diversity Status > Default Teal.

---

## 5. Detail Panels

### 5.1 Node Detail Panel (Side Drawer)

Triggered by: Click/tap on a site node. Slides in from the right, 400px wide (desktop), full-width sheet (mobile).

```
┌────────────────────────────────────────┐
│ ✕  CO-DEN-001 · Denver Central Office  │  ← H3, close button
│─────────────────────────────────────────│
│ Site Type: Central Office    Tier: 1   │
│ CLLI: DNVRCO01    Region: West         │
│ Status: ● Active                       │
│─────────────────────────────────────────│
│ DIVERSITY GRADE          ┌────────┐    │
│                          │   B    │    │  ← circular grade badge
│                          └────────┘    │
│─────────────────────────────────────────│
│ Connected Conduits (12)                │
│ ┌─ CNT-DEN-001 → CO-BLD-003  [B] ──┐  │
│ │  Underground · 47.2km · 6 spans   │  │
│ └───────────────────────────────────┘  │
│ ┌─ CNT-DEN-002 → DC-DEN-001  [A] ──┐  │
│ │  Underground · 12.1km · 3 spans   │  │
│ └───────────────────────────────────┘  │
│─────────────────────────────────────────│
│ Active SRLGs (3)                       │
│  🌉 Bridge SRLG-B-001 (HIGH)          │
│  🔌 Power Feed SRLG-P-012 (MEDIUM)    │
│─────────────────────────────────────────│
│ Services Through This Site (142)       │
│  [View in Service Table →]             │
└────────────────────────────────────────┘
```

### 5.2 Edge Detail Panel

Triggered by: Click on a conduit or span edge.

```
┌─────────────────────────────────────────┐
│ ✕  CNT-DEN-001 · Denver–Boulder Conduit │
│──────────────────────────────────────────│
│ Type: Underground   Owner: Lakelink     │
│ Corridor: US-36    Length: 47.2km       │
│ Install: 2018      Active: ● Yes        │
│──────────────────────────────────────────│
│ Spans (6)                               │
│  SPN-001  SMF-28e  12ct  8.2km  [A]     │
│  SPN-002  SMF-28e  24ct  7.1km  [C]     │
│  ...                                    │
│──────────────────────────────────────────│
│ Shared Risk Groups (2)                  │
│  🌉 Bridge SRLG-B-001 (HIGH) — 3 spans │
│  🚇 Tunnel SRLG-T-044 (MEDIUM)         │
│──────────────────────────────────────────│
│ Hazard Exposure                         │
│  🔥 Wildfire WF-2026-001 · Direct (3km) │
│  🌊 Flood FL-2026-044 · Advisory (62km) │
└─────────────────────────────────────────┘
```

### 5.3 Panel Accessibility

* Panel uses `role="dialog"` with `aria-label="Site detail: {site_name}"`
* Focus traps inside panel when open (WCAG 2.1 — Modals)
* Escape key closes panel and returns focus to the triggering node/edge
* All content in panel is keyboard-navigable (Tab order: close button → content → links)
* Panel announced via `aria-live="polite"` region update

---

## 6. Responsive Behavior

### 6.1 Breakpoint Strategy

| Breakpoint | View Mode | Graph | Detail Panel |
| --- | --- | --- | --- |
| ≥1440px (Desktop XL) | Full interactive graph | SVG canvas, pan/zoom enabled | Side drawer (400px) |
| 1024–1439px (Desktop) | Full graph, compact nodes | SVG canvas, reduced node labels | Side drawer (360px) |
| 768–1023px (Tablet) | Simplified graph | Top 50 sites only, aggregate edges | Bottom sheet (50vh) |
| <768px (Mobile) | List view fallback | No graph — structured list/tree | Full-screen modal |

### 6.2 Mobile List View (< 768px)

Mobile replaces the graph with an accessible, searchable tree view:

```
┌──────────────────────────────────────┐
│ 🔍 Search sites, conduits, spans...  │
│──────────────────────────────────────│
│ ▾ West Region                        │
│   ▾ CO-DEN-001 Denver CO [B]         │
│     ├─ CNT-DEN-001 → Boulder [B]     │
│     │  ├─ SPN-001 SMF-28e 8.2km [A]  │
│     │  └─ SPN-002 SMF-28e 7.1km [C]  │
│     └─ CNT-DEN-002 → DC-DEN [A]      │
│   ▸ CO-BLD-003 Boulder CO [A]        │
│ ▸ Central Region                     │
│ ▸ East Region                        │
│ ▸ Southeast Region                   │
└──────────────────────────────────────┘
```

* Each row is a `<li>` in a `role="tree"` with `role="treeitem"` children
* Expand/collapse via Enter/Space, arrow key navigation (WCAG 1.3.1, 2.1.1)
* Grade badges use tinted-bg pattern from §2.1
* Tap row to open detail panel (full-screen modal on mobile)

### 6.3 Tablet Simplification (768–1023px)

* Only render tier_1 and tier_2 sites (\~839 nodes instead of 2,969)
* Aggregate tier_3 access sites as a count badge on their parent conduit
* Edge bundling always on (no expand-to-spans)
* Touch targets ≥ 44×44px for all interactive elements

---

## 7. Graph Controls Toolbar

### 7.1 Toolbar Layout

```
┌──────────────────────────────────────────────────────────────┐
│ [Fit] [+] [−] │ 🔲 Diversity │ 🔲 SRLGs │ 🔲 Hazards │ ⚙  │
└──────────────────────────────────────────────────────────────┘
```

Sticky below the header (position: sticky, top: 56px). Background: `--lf-white` with `--shadow-card`.

| Control | Type | Keyboard | ARIA |
| --- | --- | --- | --- |
| Fit to View | Button | F | `aria-label="Fit graph to viewport"` |
| Zoom In | Button | + or = | `aria-label="Zoom in"` |
| Zoom Out | Button | − | `aria-label="Zoom out"` |
| Diversity Overlay | Toggle | D | `role="switch"`, `aria-checked` |
| SRLG Overlay | Toggle | S | `role="switch"`, `aria-checked` |
| Hazard Overlay | Toggle | H | `role="switch"`, `aria-checked` |
| Settings | Menu Button | — | `aria-haspopup="menu"` |

### 7.2 Settings Menu

* **Node labels:** Show/Hide (default: Show for tier_1/tier_2, Hide for tier_3)
* **Edge labels:** Show/Hide
* **Layout density:** Compact / Normal / Spacious
* **Color-blind mode:** On/Off (adds patterns to edges)
* **Animation:** On/Off (overrides `prefers-reduced-motion`)

---

## 8. Graph Legend

Persistent, collapsible legend panel in bottom-left corner of the graph canvas.

```
┌─ Legend ──────────────────────────┐
│                                   │
│ NODES                             │
│  ○  Backbone Site (tier_1)        │
│  ○  Regional Site (tier_2)        │
│  ◇  Access Site (tier_3)          │
│  ⬡  Active Hazard                 │
│                                   │
│ EDGES                             │
│  ── Working Path                  │
│  ┄┄ Protect Path                  │
│  ·· SRLG Link                     │
│                                   │
│ DIVERSITY                         │
│  ● Fully Diverse                  │
│  ● Partially Diverse              │
│  ● Single Path                    │
│  ● Unknown                        │
│                                   │
│ SRLG TYPES                        │
│  ⚡ Bridge   🚂 Rail Crossing     │
│  📦 Shared Conduit  ⚡ Power Feed │
│  🚇 Tunnel  🏢 Central Office    │
│                                   │
│ [Collapse ▴]                      │
└───────────────────────────────────┘
```

* `role="region"` with `aria-label="Graph legend"`
* Collapsed state: single-row icon strip
* Responsive: moves to top of graph on tablet, inline above tree on mobile

---

## 9. Navigation Integration

### 9.1 New Route: `/topology`

Add a fourth tab in `__root.tsx` navigation:

```tsx
<Link
  to="/topology"
  activeProps={{ className: "active", "aria-current": "page" as const }}
  onClick={() => setNavOpen(false)}
>
  Network Topology
</Link>
```

Page title: `"Network Topology | Lakelink Fiber"`

### 9.2 Cross-View Navigation

| From | Action | Navigates To |
| --- | --- | --- |
| Service Table → Topology | "View path" link per service row | `/topology?service={service_id}` — highlights the service's working + protect paths |
| Topology → Service Table | Panel link "View in Service Table" | `/?service={service_id}` — scrolls to and highlights the row |
| Hazard Exposure → Topology | "View on topology" link per hazard | `/topology?hazard={hazard_id}` — centers on hazard with overlay active |
| Topology → Action Queue | Panel link "Open action" per SRLG action | `/actions?action={action_id}` |

---

## 10. Performance Considerations

### 10.1 Rendering Budget

The full graph (2,969 sites, 1,969 conduits, 10,092 spans) would produce \~15,000 SVG elements — within browser limits but sluggish on mid-range devices.

**Strategy: Progressive disclosure with WebGL fallback.**

| Node Count | Renderer | Technique |
| --- | --- | --- |
| <500 | SVG (D3) | Full DOM — interactive, accessible |
| 500–5,000 | Canvas (D3 + HTML overlay) | Canvas for edges, HTML for interactive nodes |
| >5,000 | WebGL (Deck.gl) | GPU-rendered, tooltip overlay on hover |

Default view: Region-level aggregation (4 regions + backbone sites \~50 nodes). Drill into a region to see its sites and conduits.

### 10.2 Data Loading

* **Initial load:** Fetch site summary + conduit count per region (tiny payload, <5KB)
* **Region drill-in:** Lazy-load sites and conduits for selected region
* **Service path trace:** On-demand query for a specific service_id (fetch working + protect path hops)
* **SRLG overlay:** Lazy-load SRLG memberships for visible spans only

All fetches use the existing `/api/` pattern from catalog_sql.py with Statement Execution API.

---

## 11. Accessibility Summary (WCAG 2.1 AA)

| Requirement | Implementation |
| --- | --- |
| 1.1.1 Non-text Content | Graph has `role="img"` with dynamic `aria-label` summarizing topology ("Network topology: 424 COs, 1,969 conduits, 5,605 single-path services") |
| 1.3.1 Info & Relationships | Mobile tree view uses semantic `role="tree"` / `role="treeitem"` hierarchy |
| 1.4.1 Use of Color | Diversity status uses color + pattern (dash) + text label + letter grade |
| 1.4.3 Contrast | All badge pairings ≥ 4.5:1 (verified in §2.1, §3.1) |
| 1.4.11 Non-text Contrast | Node borders and edge strokes ≥ 3:1 against canvas background |
| 2.1.1 Keyboard | All graph controls keyboard-accessible. Escape closes panels. Arrow keys navigate tree. |
| 2.4.1 Skip Navigation | Graph canvas has skip link to detail panel / toolbar |
| 2.4.2 Page Title | "Network Topology \| Lakelink Fiber" |
| 2.4.7 Focus Visible | 2px solid `--lf-dark-teal` focus ring on all interactive elements |
| 2.5.8 Target Size | All toolbar buttons and toggle switches ≥ 44×44px touch target |
| 4.1.2 Name, Role, Value | Toggles use `role="switch"`, nodes are focusable with `aria-label` |

**Parallel table view:** The mobile list/tree view (§6.2) serves as the accessible alternative to the visual graph, satisfying WCAG 1.1.1 for complex visualizations.

---

## 12. Brand Compliance Checklist

- [x] Company name: "Lakelink Fiber" throughout (never "Lumen")
- [x] Primary color: `--lf-dark-teal` (#006272) for graph chrome, toolbar, headers
- [x] Body text: `--lf-iron` (#4D4D4D) in all panels and labels
- [x] Accent: `--lf-accent-orange` (#F26522) only for large text, icons, selected-node highlight
- [x] Background: `--lf-platinum` (#E8E8E8) for canvas background
- [x] Risk palette: Reuses BRAND-GUIDE §2.3 severity scale
- [x] Diversity palette: Extends BRAND-GUIDE §2.5 path diversity ratings
- [x] Typography: Inter for all labels, JetBrains Mono for IDs/codes
- [x] Icons: Lucide React, 1.5px stroke
- [x] Elevation: `--shadow-card` for panels, `--shadow-dropdown` for menus
- [x] Spacing: 4px base unit scale
- [x] Border radius: `--radius-md` (8px) on panels and cards

---

## 13. Implementation Phases

| Phase | Deliverable | Dependencies | Priority |
| --- | --- | --- | --- |
| 13a | `/topology` route + toolbar + legend + region-level aggregation | None (uses existing gold tables) | HIGH |
| 13b | Drill-in to site-level nodes + conduit edges | 13a | HIGH |
| 13c | Service path trace (highlight working + protect) | 13b + API endpoint | MEDIUM |
| 13d | SRLG overlay with highlight mode | 13b + API endpoint | MEDIUM |
| 13e | Hazard overlay integration (reuse HAZARD-VIS-SPEC zones) | 13b + HAZARD-VIS-SPEC | MEDIUM |
| 13f | Mobile tree view fallback | 13a | MEDIUM |
| 13g | WebGL renderer for >5K node views | 13b | LOW |

---

## 14. Review Criteria

@designer will evaluate the implementation against:

1. **Layout fidelity:** Hierarchical structure, no random node positions
2. **Color accuracy:** All tokens match BRAND-GUIDE hex values
3. **Contrast compliance:** All text and non-text elements meet stated ratios
4. **Keyboard accessibility:** Full graph navigation without mouse
5. **Responsive transitions:** Clean breakpoint behavior, no layout shift
6. **Mobile fallback:** Tree view renders correctly, all data accessible
7. **Performance:** Initial render <2s on desktop, <3s on tablet
8. **Brand compliance:** Zero "Lumen" references, correct Lakelink Fiber branding

---

*End of specification. Questions or deviation requests → @designer via Lakebase.*