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

## 7. PROVISIONAL disclosure for the DEC-41 partial cutover (P68-DESIGN-PROVISIONAL-HSI-COPY, 2026-10-31)

Source decision: `DEC-PRI-V4-073-SECOND-MISS-PARTIAL-CUTOVER` (decisions id 41, option b). Runbook: `ops/v4_cutover_runbook.py` `partial_cutover=True`, `PARTIAL_KEEP_V3 = (hazard_span_intersection, span_risk_predictions, resilience_score_snapshot)` (commit a1b4053). This section is **contingency copy**. It ships only if DEC-41 becomes `decided`. If the CEO approves the BUG-QA-073 writes (DEC-41 `superseded`), §7 is never rendered and §6 applies unchanged.

### 7.1 Gating (never hard-coded)

* Render PROVISIONAL only when `PRI_V4_KPIS=true` **and** the API reports `cutover_mode = PARTIAL` for the surface's source object (from the demo freeze manifest row status `KEPT_V3_PROVISIONAL`, per P68-DP-PARTIAL-CUTOVER-MANIFEST-SPEC). Return the status per object, not as one global flag, so v4.1 can clear each surface on its own.
* With the flag off, or with the manifest reporting no `KEPT_V3_PROVISIONAL` rows, the UI matches the current build exactly.
* **PROVISIONAL and INTERIM never appear on the same element.** A v3-sourced figure is not a v4 candidate. On any card whose source is a kept-v3 object, PROVISIONAL replaces INTERIM. INTERIM stays only on surfaces that actually read a v4 INTERIM object. In partial mode that is none of the §6.2 cards.

### 7.2 Where it appears

| Surface | Source object (partial mode) | Treatment |
| --- | --- | --- |
| Scorecard header: Avg Resilience Score, Critical Risk, High Risk, Revenue at Risk | `resilience_score_snapshot` (v3) | PROVISIONAL badge in the label row (same slot as §6.2) |
| Service table: score and risk-band columns | `resilience_score_snapshot` (v3) | One badge in the table caption, not per row or per header cell |
| `/hazards` page (exposure counts, impacted services) | HSI-derived (`hazard_span_proximity`, v3 lineage) | Page note (§7.4) under the page title |
| `/actions` page | `proactive_action` (v3; v4 moves to v4.1) + HSI-derived nearest hazard | Page note (§7.4) |
| `/topology` hazard overlay legend | HSI-derived | One legend line: `Hazard overlay: provisional (v3 hazard model)` |
| `/topology` map, conduits, SRLG, path trace; `/conduits` | v4 promoted | **No badge.** These are the v4 build. Do not imply they are provisional. |
| MRC Protected card | `mv_mrc_protected` (WAITS_UPSTREAM in partial mode) | Keep the existing hide-on-null rule (P36). Do not show a PROVISIONAL card. |

If @pm adds `hazard_span_proximity` or `proactive_action` to `PARTIAL_KEEP_V3` (the open @devops S65 question), the table above already covers them. If they are instead deferred as missing, `/hazards` and `/actions` show their existing empty or error state, not a PROVISIONAL note.

### 7.3 Badge (reuse the INTERIM component)

| Element | Spec |
| --- | --- |
| Component | Generalise `InterimBadge` into a status badge with `variant: "interim" \| "provisional"`. Same CSS class, so tokens cannot drift. |
| Visible text | `Provisional` (12px, 600 weight, CSS uppercase) |
| Style | Identical to §6.2: platinum #E8E8E8 fill, iron #4D4D4D text (6.90:1 PASS), 1px iron border, 4px radius, 3px brand-orange #F26522 decorative left accent. The variants differ by **text only** (SC 1.4.1). No new colour. |
| aria-label | `Provisional figure, v3 hazard model, update pending` |
| Info tooltip (InfoTooltip, `label="About provisional figures"`) | `Hazard exposure, risk bands and resilience scores still use the v3 hazard model. Network topology and conduits already show the v4 build. These figures will be updated after the v4 hazard re-derive passes QA.` |
| Forced colours | Inherits the `.interim-badge` Canvas/CanvasText block. |
| Removal | Driven by the per-object manifest status. When v4.1 promotes an object, its badge disappears with no code change. |

### 7.4 Page note (`/hazards`, `/actions`)

* Text: `Provisional: hazard exposure on this page uses the v3 hazard model. Topology and conduits use the v4 build.`
* Markup: `<p role="note">` directly under the h1. It is static, so **not** a live region. Solid iron #4D4D4D on white (8.45:1). 14px minimum. It wraps at 320px (SC 1.4.10). Put the bold word `Provisional:` first so it does not depend on colour or the badge.
* No dismiss control. It is part of the page's meaning while the condition holds.

### 7.5 Genie disclosure (owner @data-analyst; Genie space name per BRAND-GUIDE `{Audience} Resilience Intelligence`)

* General instruction, verbatim: `When an answer uses resilience scores, risk bands, critical or high risk counts, revenue at risk, or hazard exposure, end with: "Note: these figures are provisional. They use the v3 hazard model while the v4 hazard update completes. Topology, conduit and shared-risk figures are from the v4 build." Do not add the note to answers that use only topology, conduit, span or shared-risk data.`
* Banned in Genie answers and sample questions: `worse`, `declined`, `dropped`, `deteriorated`, `regression` about scores (same as §6.1), and any v4 score delta (`61.5 → 56.8`, `1,087 critical`, `$54.4M/mo`). Those are v4 HSI figures and are **not live** in partial mode.
* Sample question to add: `Which figures are provisional right now?` Expected answer: the scores, risk bands and hazard exposure are provisional (v3 hazard model), and topology and conduits are v4.
* Company name is Lakelink Fiber only.

### 7.6 Numbers and presenter frame in partial mode

* Displayed values are the live v3 figures (checked 2026-10-31 on `resilience_score_snapshot` v24): Avg score **61.5** (raw 61.549), Critical **848**, High **2,932**, Revenue at Risk **$48.4M/mo**. Do **not** show the §6.1 v4 figures (56.8, 1,087, $54.4M/mo) or any v3→v4 score delta.
* **Erratum to §6.1/§6.4:** the raw v3 average is 61.549, so it rounds half up to **61.5**, not 61.6. 61.6 came from rounding twice (61.549 → 61.55 → 61.6). When §6 ships (full cutover), use `61.5 → 56.8`, delta `−4.7` (recheck against the raw v4 value at that time).
* Presenter frame (speaker note): `Topology, conduits and shared-risk groups are on the new v4 build today. The hazard model update lands next. Until then the scores are labelled provisional.` The §6.1 "same network, more honest measurement" frame is held back until HSI v4 ships.
* The `(metro/access)` qualifier (§6.3) still follows `bb_srlg_coverage` and does not depend on §7.

### 7.7 Acceptance checks (@designer verifies)

1. Flag off, or no `KEPT_V3_PROVISIONAL` rows: there is no PROVISIONAL text anywhere, and the UI is identical to the current build.
2. Partial mode: PROVISIONAL shows on exactly the §7.2 surfaces. No element shows both INTERIM and PROVISIONAL. `/conduits` and the topology map have no badge.
3. The aria-label, tooltip and page note match §7.3/§7.4 byte for byte. Tooltip behaviour follows §4 (hover, focus, Esc).
4. The header shows 61.5, 848, 2,932 and $48.4M/mo from the API, with no hard-coded numbers.
5. `grep -riE "lumen"` over `ui/` returns 0, and so does a search for `\bworse\b|declined|deteriorat` in the new copy.
6. At 320px the badge wraps under the label (`.kpi-label-row--interim` wrap rule) and the page note wraps without truncating.
