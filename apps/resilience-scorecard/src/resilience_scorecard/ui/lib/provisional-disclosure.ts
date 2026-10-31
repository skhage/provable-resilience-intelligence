/**
 * Lakelink Fiber — PROVISIONAL disclosure (P68-APP-PROVISIONAL-BADGE, V4-KPI-COPY-SPEC §7)
 *
 * Contingency copy for the DEC-41 partial cutover. Ships only when PRI_V4_KPIS=true AND
 * the backend reports cutover_mode=PARTIAL with per-object KEPT_V3_PROVISIONAL status.
 * PROVISIONAL replaces INTERIM on any surface whose source object is still v3 (§7.1).
 *
 * Copy and placement are from §7.2-§7.4. Badge tokens reuse the §6.2 .interim-badge CSS
 * class; the variants differ by text only (§7.3, WCAG 1.4.1).
 */

// §7.3 badge copy (verbatim)
export const PROVISIONAL_LABEL = "Provisional";
export const PROVISIONAL_ARIA =
  "Provisional figure, v3 hazard model, update pending";
export const PROVISIONAL_TOOLTIP =
  "Hazard exposure, risk bands and resilience scores still use the v3 hazard model. " +
  "Network topology and conduits already show the v4 build. " +
  "These figures will be updated after the v4 hazard re-derive passes QA.";
export const PROVISIONAL_INFO_LABEL = "About provisional figures";

// §7.4 page note (verbatim)
export const PROVISIONAL_PAGE_NOTE =
  "Provisional: hazard exposure on this page uses the v3 hazard model. " +
  "Topology and conduits use the v4 build.";

// §7.2 topology legend line
export const PROVISIONAL_HAZARD_LEGEND =
  "Hazard overlay: provisional (v3 hazard model)";

// Badge variant type shared with InterimBadge
export type BadgeVariant = "interim" | "provisional";

// §7.2 surface-to-source-object mapping
const SURFACE_SOURCES: Record<string, string[]> = {
  scorecard_header: ["resilience_score_snapshot"],
  service_table: ["resilience_score_snapshot"],
  hazards_page: ["hazard_span_proximity", "hazard_span_intersection"],
  actions_page: ["proactive_action", "hazard_span_proximity", "hazard_span_intersection"],
  topology_hazard_legend: ["hazard_span_proximity", "hazard_span_intersection"],
};

/** True when at least one source object for this surface is KEPT_V3_PROVISIONAL. */
export function isProvisional(
  surface: string,
  provisionalObjects: string[],
): boolean {
  const sources = SURFACE_SOURCES[surface];
  if (!sources || provisionalObjects.length === 0) return false;
  return sources.some((s) => provisionalObjects.includes(s));
}

/**
 * §7.1: decide which badge variant to show. PROVISIONAL overrides INTERIM.
 * Returns null when no badge should be shown.
 */
export function badgeVariant(
  v4Kpis: boolean,
  reportStatus: unknown,
  provisionalObjects: string[],
  surface: string,
): BadgeVariant | null {
  if (!v4Kpis) return null;
  // §7.1: v3-sourced figure → PROVISIONAL, never INTERIM
  if (isProvisional(surface, provisionalObjects)) return "provisional";
  // §6.2: v4 candidate figure → INTERIM while status is not FINAL
  if (reportStatus === "INTERIM") return "interim";
  return null;
}

/** True when the /hazards or /actions page note should render (§7.4). */
export function showProvisionalPageNote(
  v4Kpis: boolean,
  provisionalObjects: string[],
  surface: "hazards_page" | "actions_page",
): boolean {
  return v4Kpis && isProvisional(surface, provisionalObjects);
}

/** True when the topology hazard legend line should render (§7.2). */
export function showProvisionalHazardLegend(
  v4Kpis: boolean,
  provisionalObjects: string[],
): boolean {
  return v4Kpis && isProvisional("topology_hazard_legend", provisionalObjects);
}
