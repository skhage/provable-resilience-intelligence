# Lakelink Fiber — Provable Resilience Intelligence
## Demo Flow Guide (Package 8: Demonstration & Handover)

**Author:** @designer · **Date:** 2026-10-20 · **Status:** BINDING  
**Task:** P4-DESIGN-DEMO-TEMPLATE · **Priority:** MEDIUM  
**Audience:** Lakelink Fiber Service Assurance leadership, Sales engineering, Network operations  
**Duration:** 12–15 minutes (expandable to 25 with Q&A and Genie exploration)

---

## 1. Demo Surface Inventory

| Asset | Type | ID / Location | Status |
| --- | --- | --- | --- |
| Provable Resilience Scorecard | AI/BI Dashboard | `01f1cc02ba3f1ad0926296f440e8f3ea` | PUBLISHED |
| Service Assurance Resilience Intelligence | Genie Agent | `01f1cc02b4c7110aaa64d6bccad5d95f` | LIVE |
| Sales Resilience Intelligence | Genie Agent | `01f1cc02b7061b9bab644383b5cd0bfa` | LIVE |
| Resilience Scorecard App | Databricks App | `apps/resilience-scorecard/` | SCAFFOLD (mock data) |
| Resilience Scoring Pipeline | SDP Pipeline | `pipeline/resilience_scoring_pipeline` | OPERATIONAL |
| Span Risk Model | ML Serving Endpoint | `copper-retirement-risk` | READY |
| 7 Metric Views | Unity Catalog | `cdm_tmforum.provable_resilience_intelligence` | LIVE |

---

## 2. Narrative Arc

**Core thesis:** "Redundancy on paper isn't resilience. Lakelink Fiber now *proves* resilience — continuously, for every enterprise service — by joining physical path topology, live network telemetry, and outside-plant hazards into a single score."

**Three-act structure:**

| Act | Duration | Theme | Primary Asset |
| --- | --- | --- | --- |
| Act 1: The Problem | 2 min | "Redundancy ≠ resilience" | Dashboard KPIs |
| Act 2: The Platform | 6 min | "Governed, scored, actionable" | Dashboard + Genie + App |
| Act 3: The Value | 4 min | "$47.7M/year base case" | Revenue at Risk + Sales Genie |

---

## 3. Scene-by-Scene Flow

### Act 1 — The Problem (2 min)

**Screen:** Dashboard → KPI strip

**Talking points:**
* "Lakelink Fiber serves 8,000+ enterprise services across a national fiber network."
* "Today, 'diversity' is a checkbox on a circuit order. We can't answer: *Is this service actually resilient right now?*"
* Point to **Avg Resilience Score** (expected ~52). "The network average is barely above 'poor.' That's not a technology gap — it's a visibility gap."
* Point to **Total Revenue at Risk** (~$69M). "This is the financial exposure we couldn't quantify before."

**Transition:** "Let me show you how we close that gap."

### Act 2 — The Platform (6 min)

#### Scene 2a: Resilience Scorecard Dashboard (2 min)

**Screen:** Dashboard → full page (charts visible)

**Walk through:**
1. **Resilience by Service Type** (bar chart) — "Every service type gets a score. MPLS and wavelength services score lowest because they share the most conduit."
2. **Revenue at Risk by Urgency × Severity** (bar chart) — "We stack-rank by financial impact, not just technical severity."
3. **SRLG Risk Summary** (heatmap) — "Shared Risk Link Groups are the hidden killer. This heatmap shows where conduit sharing creates correlated failure."
4. **Problems by Intervention Type** (pie) — "Most problems can be addressed proactively — reroute, pre-position, notify — before a cut becomes an outage."

#### Scene 2b: Genie Agent — Service Assurance (2 min)

**Screen:** Service Assurance Genie space

**Demo questions (pick 2):**
* "Which services have a resilience score below 40?"
* "Show me the top 10 services by revenue at risk."
* "How many proactive actions are pending for premium_plus customers?"
* "What are the most common SRLG types for critical-severity services?"

**Talking points:**
* "Any NOC operator can ask questions in natural language. No SQL, no dashboards to build."
* "The Genie is backed by governed metric views — same definitions everywhere."

#### Scene 2c: Resilience Scorecard App — Action Queue (2 min)

**Screen:** App → `/actions` route

**Demo flow:**
1. Show **Action Queue KPI cards** (Critical Pending, Total Pending, In Progress, Completed)
2. Filter by **"pending"** status
3. Click **"Start"** on a critical reroute action → status changes to in_progress
4. Click **"Complete"** → status moves to completed
5. Switch to **"All"** filter → show state persistence

**Talking points:**
* "Actions are triggered by risk thresholds — the system recommends reroute, dispatch, or notify."
* "State persists in Lakebase — close the browser, come back, your queue is exactly where you left it."
* "Every action is auditable — who acted, when, what was the outcome."

### Act 3 — The Value (4 min)

#### Scene 3a: Revenue at Risk Deep Dive (2 min)

**Screen:** Dashboard → Revenue at Risk chart + KPI

**Talking points:**
* "$69M at risk is the *current* exposure. Every proactive intervention reduces it."
* "Premium_plus customers with SLA commitments are prioritized automatically."
* "This isn't a one-time report — the score refreshes every 15 minutes from live telemetry."

#### Scene 3b: Genie Agent — Sales (2 min)

**Screen:** Sales Genie space

**Demo questions (pick 2):**
* "Which premium_plus customers have revenue at risk above $1M?"
* "Show me diversity coverage percentage by customer tier."
* "What's the average resilience score for our top 20 customers by revenue?"

**Talking points:**
* "Sales can now answer RFP questions with *data*: 'Your service has a resilience score of 87, with A-rated path diversity and zero SRLGs.'"
* "That's not a promise — it's a proof point, updated continuously."
* "Base-case value: $47.7M/year in reduced churn, faster sales cycles, and avoided SLA penalties."

---

## 4. Visual Polish Checklist (Demo Readiness)

### 4.1 Demo-Blocking Issues (MUST FIX before demo)

| # | Issue | Severity | Task Code | Owner |
| --- | --- | --- | --- | --- |
| 1 | ~~`--lf-lumen-orange` CSS variable violates branding mandate~~ **RESOLVED** — renamed to `--lf-accent-orange` (BUG-QA-013 / UX-REM-BRAND-ORANGE) | ~~HIGH~~ | UX-REM-BRAND-ORANGE | @app-developer |
| 2 | Sortable table header not keyboard-accessible (Enter/Space) | MEDIUM | UX-REM-A11Y-KEYBOARD-SORT | @app-developer |
| 3 | Filter buttons missing `aria-pressed` toggle state | MEDIUM | UX-REM-A11Y-FILTER-PRESSED | @app-developer |
| 4 | No skip-navigation link for keyboard users | LOW | UX-REM-A11Y-SKIP-NAV | @app-developer |

### 4.2 Nice-to-Have (polish, not blocking)

| # | Issue | Severity | Task Code | Owner |
| --- | --- | --- | --- | --- |
| 5 | Emoji icons instead of Lucide React (inconsistent cross-OS) | LOW | UX-REM-ICONS | @app-developer |
| 6 | Inline styles should be CSS classes | LOW | UX-REM-CSS-HYGIENE | @app-developer |
| 7 | Pagination missing on service table (25-row default) | MEDIUM | UX-REM-TABLE-UX | @app-developer |
| 8 | Duplicated header/nav (not DRY, risk of drift) | MEDIUM | UX-REM-LAYOUT-ROOT | @app-developer |
| 9 | `aria-busy` missing on Suspense loading containers | MEDIUM | UX-REM-A11Y-ARIA-BUSY | @app-developer |
| 10 | Genie space descriptions empty (CEO semantic mandate) | LOW | BRAND-GENIE-DESCRIPTIONS | @data-analyst |

### 4.3 Verified ✅ (implemented correctly)

| Item | Finding |
| --- | --- |
| ARIA landmarks | `role="banner"`, `role="navigation"`, `role="main"` on both routes |
| Score gauge a11y | `role="meter"`, `aria-valuenow/min/max`, `aria-label` |
| KPI card a11y | `role="group"`, `aria-label="{metric}: {value}"` |
| Focus indicators | Global `:focus-visible` on all interactive elements (2px solid teal, 2px offset) |
| Responsive layout | 4 breakpoints (XL/desktop/tablet/mobile), hamburger nav, table scroll |
| Touch targets | 44×44px minimum on mobile (btn, rating-pill) |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` suppresses all animations |
| Brand tokens | --lf-dark-teal #006272, --lf-platinum #E8E8E8, --lf-iron #4D4D4D |
| Accent orange | `--lf-lumen-orange` renamed to `--lf-accent-orange` per branding mandate (BUG-QA-013) |
| Typography | Inter + JetBrains Mono font stacks, correct weight/size/line-height |
| Spacing scale | xs=4px through xxl=48px, consistent usage |
| Elevation | card/dropdown/modal shadow system |
| Error boundaries | ErrorBoundary + Retry button on every data component |
| Skeleton loading | Pulse animation on platinum gradient |
| Data source badge | Mock vs Live indicator with colored dot |
| Action button a11y | `aria-label="Start/Complete action for {service}"` |
| Hamburger nav a11y | `aria-expanded`, `aria-controls`, `aria-label` (open/close) |

---

## 5. Pre-Demo Checklist

- [ ] Verify dashboard loads with live data (metric views returning rows)
- [ ] Test both Genie spaces with the scripted questions above
- [ ] Confirm app runs locally or on Databricks Apps (mock data OK for demo)
- [ ] Browser zoom: test at 100%, 150%, 200% — no layout breaks
- [ ] Dark mode: not supported — ensure OS is in light mode
- [ ] Tab through the app with keyboard only — confirm all interactions reachable
- [ ] Open DevTools console — confirm zero JS errors
- [ ] Verify no "Lumen" text appears anywhere in the UI or DevTools
- [ ] Test on Chrome, Firefox, Safari (Lucide icons render correctly in all three)
- [ ] Prepare backup: if Genie is slow, have a screenshot of a good response

---

## 6. Demo Environment Setup

```
1. Open Dashboard: Lakelink Fiber — Provable Resilience Scorecard
2. Open Genie (tab): Service Assurance Resilience Intelligence
3. Open Genie (tab): Sales Resilience Intelligence  
4. Open App (tab): localhost:8000 or Databricks Apps URL
5. Arrange: Dashboard left, Genie/App ready to switch
```

**Browser:** Chrome (recommended). Font: Inter will load from Google Fonts.  
**Resolution:** 1920×1080 minimum. 2560×1440 preferred.  
**Connection:** Wired or strong WiFi — Genie responses take 2–5s.

---

## 7. Contingency Playbook

| Scenario | Fallback |
| --- | --- |
| Dashboard doesn't load | Open metric view queries directly in SQL editor |
| Genie returns unexpected answer | Pivot to "Great question — let me show you in the dashboard" |
| App backend timeout | Use Mock Data badge to explain: "In production, this connects to Lakebase" |
| Network issue | Pre-downloaded screenshots of all key screens (save to `/resources/demo-screenshots/`) |

---

## 8. Known Data Patterns — Demo Awareness

| Table | Pattern | Explanation | Impact on Demo |
| --- | --- | --- | --- |
| `resource_alarm` | 7.99% NULL `span_id` (159,753 rows) | All POWER_FAIL alarms have NULL `span_id` — these are site-level (CO power failure) events, not span-level. Expected and correct. | If someone asks "why are some alarms missing span IDs?" — explain POWER_FAIL is a facility alarm. Join via `site_id IN (site_a_id, site_z_id)` for span impact. |
| `resource_alarm` | 100% `site_id` FK validity | All 2M alarms have valid `site_id` → `geographic_site`. 300 distinct sites with POWER_FAIL. | No orphan risk on site dimension. |
| `resource_alarm` | Transport alarms: 100% `span_id` | OSNR_DEGRADE, BER_HIGH, LOS, AMP_FAIL, FIBER_CUT always have `span_id`. | Direct span join always works for transport alarms. |

> **Resilience scoring note:** The gold-layer scoring pipeline joins POWER_FAIL alarms transitively via `site_id IN (physical_resource_span.site_a_id, physical_resource_span.site_z_id)` to propagate CO-level risk to all spans terminating at that site.

---

*This demo flow guide is a @designer deliverable for P4-DESIGN-DEMO-TEMPLATE. Reviewed 2026-10-20.*
*Section 8 added by @data-engineer (P19-DE-ALARM-NULL-DOC), 2026-10-23.*
