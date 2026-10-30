# V4 KPI Copy and UI Spec (BINDING)

Owner: @designer. Task: P35-DESIGN-V4-KPI-COPY-SPEC (2026-10-25). App: `apps/resilience-scorecard`.
Sources: DEC-PRI-REV-PROTECTED-DEFINITION, DEC-PRI-BB-SRLG-DISCLOSURE, DEC-PRI-FREEZE-V4-SCOPE (incl. B12 amendment), P29-DA-REV-PROTECTED-DEDUP, P34-DA-BB-SRLG-BLIND-IMPACT, P35-DE-V4-CONDUIT-COVERAGE-CLASS.

## 0. Gating (applies to every item below)

* The demo stays on PRI-DEMO-FREEZE-v3. **No item in this spec ships to the demo UI before the @pm v4 cutover** (target no earlier than 2026-10-28).
* Build all changes behind one config flag, `PRI_V4_KPIS` (app.yaml env var, default `false`). With the flag off, the UI must render exactly as it does today.
* Pre-cutover, the backbone disclosure is a speaker note only (DEC-PRI-BB-SRLG-DISCLOSURE). Do not add BB copy to the v3 UI.
* Company name in all copy is **Lakelink Fiber**. Never use the customer's real name.

## 1. MRC Protected (replaces every "Revenue Protected" / "Revenue at risk avoided")

**Definition (verbatim, use in the tooltip and README):** Monthly recurring charge of distinct services with at least one completed proactive action. Each service is counted once.

**Source:** `mv_mrc_protected_v4_candidate` (renamed by @data-analyst at cutover, P30-DA-GENIE-MRC-PROTECTED-CUTOVER). Reference value: $72,767,771 over 4,625 services (57.8% of $125.81M total MRC).

| Element | Spec |
| --- | --- |
| Placement | Action Queue page, `ActionSummaryCards` row, 5th card, directly after **Completed**. It is an outcome of completed actions, so it belongs next to them. Do not add it to the scorecard header. |
| Card class | `kpi-card success` (green left border #2E7D32; the border is decoration, not information). |
| Label | `MRC Protected` (CSS uppercases it). |
| Value | `$72.8M` + `<span class="kpi-sub">/mo</span>`. Format: `$` + millions to 1 dp + `M`. Under $1M use `$###K`. |
| Sub-line | `4,625 services · 57.8% of MRC` (12px, solid iron #4D4D4D). Thousands separators required. |
| Info control | Lucide `Info` 16px, 1.5px stroke, inside a 24x24px button, `aria-label="About MRC Protected"`, `aria-describedby` pointing at the tooltip. |
| aria-label (card) | `MRC Protected: $72.8 million per month across 4,625 services with at least one completed action` |
| Null / error | If the measure is null or the query fails, do **not** render the card. Never show `$0`. |

**Banned strings (anywhere in UI, aria, tooltips, Genie suggestions, README):** `Revenue Protected`, `Revenue at risk avoided`, `Revenue saved`, `Revenue Protected USD`. Never compute the value by summing per action (that is the $76.45M fan-out bug).

**Unit consistency (same flag):** the scorecard header **Revenue at Risk** card is also monthly. Append `<span class="kpi-sub">/mo</span>` to its value and add `per month` to its aria-label. Both money KPIs must show the same unit.

## 2. Backbone SRLG coverage disclosure

Fact base: shared-risk (SRLG) derivation covers the metro/access span layer (`SPAN-*`). Backbone (`BB-*`, 92 spans / 31 routes) has no SRLG rows until BUG-DP-069 ships. 7,531/8,000 services cross BB hops, and 1,222/2,395 sold-diverse services put working and protect on the same BB route.

The UI state depends on one backend field, `bb_srlg_coverage: "complete" | "partial"` (in the scorecard summary). It is `partial` until @qa passes the BUG-DP-069 gate (QA-B gates).

### 2.1 When `bb_srlg_coverage = partial`

| Surface | Required copy / behavior |
| --- | --- |
| Scorecard header, **SRLG Groups** card | Sub-line: `Metro/access spans only`. Add an Info button (spec as in §1) with tooltip: `Backbone (BB-*) routes are modeled at long-haul grain. Their shared-risk groups ship in a later build, so diversity on backbone hops is not yet verified.` aria-label: `SRLG Groups: {n}, metro and access spans only` |
| Topology legend, **Shared Risk Groups** section | Last line, 12px solid iron #4D4D4D: `Coverage: metro/access spans. Backbone not yet included.` |
| Topology, BB-* edges | No SRLG badge. Edge aria-label and hover text end with `Backbone span: shared-risk data not available`. **Never** say `No shared risk` or `0 SRLGs` for a BB span. |
| Diversity badge (service panel) | If the service crosses BB hops (`crosses_backbone = true` in `ServiceDiversityOut`) and its status is `fully_diverse` or `partially_diverse`, append a second line in the badge: `Backbone unverified`. Include it in the badge aria-label. Leave the color unchanged; this is text, not a new color. |
| Diversity percentages | Any diversity % in UI copy must be labelled `(metro/access)`. Do not present a network-wide diversity %. |

### 2.2 When `bb_srlg_coverage = complete`

* SRLG Groups sub-line: `Metro, access and backbone`. Remove the tooltip caveat (keep the Info button with the definition: `Groups of spans that share a physical risk, such as a conduit, bridge or central office.`).
* Remove the legend coverage line, the BB edge caveat and the `Backbone unverified` line. BB edges get SRLG badges like any other edge.

## 3. Conduit coverage class (B12, same flag)

Source: `physical_resource_conduit_v4_candidate.span_coverage_class` (REAL_SEGMENTED 55 / BB_ONLY 90 / INVENTORY_ONLY 1,824).

* Topology adds a filter chip group labelled `Conduits`. Options: `Segmented (55)`, `Backbone only (90)`, `Inventory only (1,824)`. The default selection is Segmented + Backbone only (conduits with span geometry), per the DEC-PRI-FREEZE-V4-SCOPE amendment. Counts come from the API, not hard-coded.
* Chips use `role="checkbox"` + `aria-checked`, the same pattern as the overlay toggles. Selected = dark teal #006272 fill with white text (7.02:1). Unselected = white with a teal border and teal text.
* Inventory-only conduits, when shown, render with a dotted iron stroke (`2,4`) and the hover/aria text `Inventory only: no span geometry`. Add the matching legend item.

## 4. Accessibility requirements (WCAG 2.1 AA)

| Pair | Ratio | Result |
| --- | --- | --- |
| Iron #4D4D4D sub-line / disclosure text on white | 8.45:1 | PASS (use solid iron, not the 80% alpha label color, for disclosure text) |
| Dark teal #006272 value on white | 7.02:1 | PASS |
| White on dark teal chip | 7.02:1 | PASS |
| Existing `.kpi-label` rgba(77,77,77,0.8) on white (approx. #717171) | about 4.8:1 | PASS, but do not reuse it for caveat text |

* Tooltips (SC 1.4.13): open on hover **and** keyboard focus, dismiss on Esc, stay open while hovered, and never cover the KPI value.
* The Info button must be reachable by Tab. Focus ring is 2px solid dark teal #006272 with offset 2px, the existing `.btn:focus-visible` token on white surfaces (7.02:1).
* Caveats are text. Never rely on an asterisk, color, or icon alone (SC 1.4.1).
* Reflow (SC 1.4.10): at 320px the 5-card action row wraps (the existing `auto-fit minmax(200px,1fr)` grid is fine). The sub-line must wrap, not truncate.

## 5. Acceptance checks (@designer verifies)

1. With `PRI_V4_KPIS=false`, the UI is pixel-identical to the v3 freeze.
2. `grep -riE "revenue (protected|at risk avoided|saved)"` over `ui/` and `backend/` returns 0 hits.
3. The MRC Protected card shows $72.8M/mo, 4,625 services, 57.8%; the aria-label matches §1.
4. With `bb_srlg_coverage=partial`, all four §2.1 surfaces show the caveat. Switching to `complete` removes it.
5. Topology defaults to 145 conduits (55+90). Chip counts come from the API.
6. The tooltip passes keyboard + Esc + hover tests. Contrast is as in §4.

## 6. v3 to v4 delta: presenter copy and INTERIM badge (P40-DESIGN-V4-DELTA-PRESENTER-COPY, 2026-10-26)

Source: `kpi_delta_attribution_v4_candidate` (report_status = INTERIM, interim-1). Decision record: DEC-PRI-V4-DELTA-PRESENTER-COPY. The same gating as §0 applies. Before cutover this section is a speaker note only.

### 6.1 Narrative frame (binding wording)

* Headline: **Same network, more honest measurement.**
* Rule: the score went down because measurement got better, not because the network got worse. Never say `worse`, `declined`, `dropped`, `deteriorated` or `regression` about the v4 score. Use `recalibrated`, `now accounts for`, `newly visible`.
* Three beats:
  1. **What changed.** Hazard proximity is now measured along each span's full route instead of only at its midpoint. Lakelink Fiber now sees about 1.23M hazard-to-service links, up from about 613K.
  2. **What moved.** Average resilience score went from 61.6 to 56.8. 239 more services are now critical (1,087 total), and MRC at risk went from $48.4M/mo to $54.4M/mo. No service left the critical tier. The change only adds visibility.
  3. **Why it matters.** These exposures were real in v3 and simply not visible. Finding them before a cut is the product's job.
* Diversity: `74.2% (metro/access), unchanged in this interim build. Backbone shared-risk scoring has not landed yet.`
* MRC Protected ($72.8M/mo, 4,625 services) is a **new definition** (each service counted once). Do not present it as a delta against any earlier Revenue Protected figure. That figure is banned (§1) and could not be compared anyway because it was a fan-out.

### 6.2 INTERIM badge (UI, behind PRI_V4_KPIS, shown only while report_status = INTERIM)

| Element | Spec |
| --- | --- |
| Where | The Avg Score, Critical and Revenue at Risk cards on the scorecard header, plus any v3-to-v4 delta view. Not on MRC Protected, which has no v3 counterpart. |
| Visible text | `Interim` (12px, 600 weight, CSS uppercase) |
| Style | Platinum #E8E8E8 fill, iron #4D4D4D text (6.9:1 PASS), 1px iron border, 4px radius, plus a 3px lumen-orange #F26522 left accent that is decorative only. **Never** use orange text on white (3.15:1 FAIL) or iron on orange (2.68:1 FAIL). |
| Tooltip (Info pattern from §1) | `Preliminary v4 figures. Only the hazard-distance fix is included so far. Backbone segmentation and shared-risk updates are still being scored, so these numbers will change.` |
| aria-label | `Interim figure, v4 candidate, subject to change` |
| Removal | Driven by the API (`report_status`). When it is FINAL the badge is gone, with no code change. Never hard-code it. |

### 6.3 `(metro/access)` qualifier

* Attach it to every diversity % and SRLG count while `bb_srlg_coverage = partial`. Place it on the same line right after the number, joined with a non-breaking space: `74.2%\u00A0(metro/access)`.
* aria and speech: say `metro and access`, never the slash form.
* When the field is `complete`, remove it (see §2.2).

### 6.4 Number formatting

| KPI | Display | Delta |
| --- | --- | --- |
| Avg score | 1 dp: `61.6 → 56.8` | `−4.8` (U+2212 minus sign) |
| Critical services | thousands separator: `848 → 1,087` | `+239` |
| MRC at risk | `$48.4M/mo → $54.4M/mo` | `+$6.0M/mo` |
| Diversity | `74.2% (metro/access)` | `no change` (words, not `0.0`) |

* Round half up from the raw values, and check that display arithmetic reconciles (61.6 − 56.8 = 4.8, 54.4 − 48.4 = 6.0). Never show 2 dp (61.55) in the UI.
* Arrows: use `→` with an aria-label of `to`, for example `Average score 61.6 to 56.8, interim`.
* Delta color: neutral iron #4D4D4D for every direction. No red/green for direction, because a lower score is not a failure here and color alone cannot carry meaning (1.4.1).

### 6.5 Prepared Q&A (presenter)

* *Did resilience get worse?* No. The network is identical. The measurement now sees hazard exposure along the full route, so risk that was always there is now on the board.
* *Will the numbers move again?* Yes. The final v4 adds backbone segmentation and the shared-risk re-derive. We publish final numbers only after QA gates. Backstage only, do not put on slides: the sensitivity range for critical services is 789 to 1,680.
* *Why trust a lower number?* Because each driver is attributed. 100% of this interim delta traces to one documented fix (the hazard-span rebuild).
