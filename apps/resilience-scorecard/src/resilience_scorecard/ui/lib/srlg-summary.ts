/**
 * P108-APP-SRLG-OVERLAY-LIMIT-TRUNCATION (designer ruling S91, option a).
 *
 * The /topology map and conduit panel used the region SRLG list (/api/topology/srlgs), whose
 * per-span LIMIT 500 silently cut every region. Badges, the critical ring, '+N' and the conduit
 * aria-labels now come from the complete per-(conduit, srlg_type) aggregate
 * (/api/topology/srlg-summary). The panel heading uses the true count M, and its list loads lazily
 * per conduit. A short list is always disclosed as 'Showing N of M', never presented as the total.
 *
 * Pure module with no imports, so Node can load it directly in tests. Lakelink Fiber.
 */

/** One row of /api/topology/srlg-summary. */
export interface SrlgConduitTypeRow {
  conduit_id: string;
  srlg_type: string;
  srlg_count: number;
  member_span_count?: number;
  max_severity: string | null;
}

/** Everything the map needs for one conduit. */
export interface ConduitSrlgSummary {
  conduitId: string;
  /** Distinct SRLGs on the conduit (M). */
  srlgCount: number;
  /** Worst member severity across all its SRLGs. */
  maxSeverity: string | null;
  /** Distinct SRLG types, worst severity first, then by name. */
  types: string[];
  /** types[0]: drives the edge colour and the badge code (same rule as the old first row). */
  primaryType: string | null;
}

const SEVERITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

export function severityRank(s: string | null | undefined): number {
  return s ? SEVERITY_RANK[s.toLowerCase()] ?? 0 : 0;
}

export function buildSrlgSummary(rows: readonly SrlgConduitTypeRow[] | null | undefined): Map<string, ConduitSrlgSummary> {
  const grouped = new Map<string, SrlgConduitTypeRow[]>();
  for (const r of rows ?? []) {
    if (!r || !r.conduit_id || !r.srlg_type || !(Number(r.srlg_count) > 0)) continue;
    const list = grouped.get(r.conduit_id) ?? [];
    list.push(r);
    grouped.set(r.conduit_id, list);
  }
  const out = new Map<string, ConduitSrlgSummary>();
  grouped.forEach((list, conduitId) => {
    const byType = new Map<string, { count: number; sev: string | null }>();
    for (const r of list) {
      const prev = byType.get(r.srlg_type);
      const sev = r.max_severity ? r.max_severity.toLowerCase() : null;
      if (!prev) byType.set(r.srlg_type, { count: Number(r.srlg_count), sev });
      else {
        prev.count += Number(r.srlg_count);
        if (severityRank(sev) > severityRank(prev.sev)) prev.sev = sev;
      }
    }
    const types = Array.from(byType.keys()).sort((a, b) => {
      const d = severityRank(byType.get(b)!.sev) - severityRank(byType.get(a)!.sev);
      return d !== 0 ? d : a < b ? -1 : a > b ? 1 : 0;
    });
    let srlgCount = 0;
    let maxSeverity: string | null = null;
    byType.forEach((v) => {
      srlgCount += v.count;
      if (severityRank(v.sev) > severityRank(maxSeverity)) maxSeverity = v.sev;
    });
    out.set(conduitId, { conduitId, srlgCount, maxSeverity, types, primaryType: types[0] ?? null });
  });
  return out;
}

/** Rows shown before 'Show all M' (same disclosure pattern as the DW-133 site cap). */
export const PANEL_SRLG_INITIAL = 25;

function fmt(n: number): string {
  return Math.max(0, Math.round(n)).toLocaleString("en-US");
}

export function srlgPanelHeading(total: number): string {
  return `Shared Risk Groups (${fmt(total)})`;
}

/** Visible 12px iron note. null when every SRLG is shown. */
export function srlgShowingNote(shown: number, total: number): string | null {
  if (!(total > 0) || shown >= total) return null;
  return `Showing ${fmt(shown)} of ${fmt(total)} shared risk groups`;
}

export function srlgShowAllLabel(total: number): string {
  return `Show all ${fmt(total)}`;
}

export const SRLG_SHOW_FEWER_LABEL = "Show fewer";

export const SRLG_LIST_LOADING_MSG = "Loading shared risk groups\u2026";

/** Rows to render: the first PANEL_SRLG_INITIAL until expanded. */
export function visibleSrlgRows<T>(list: readonly T[], expanded: boolean): T[] {
  return expanded ? list.slice() : list.slice(0, PANEL_SRLG_INITIAL);
}

/** 'Show all' only when there is more loaded data to reveal. */
export function canShowAllSrlgs(loaded: number, expanded: boolean): boolean {
  return !expanded && loaded > PANEL_SRLG_INITIAL;
}

export function conduitSrlgsUrl(conduitId: string, region: string): string {
  return `/api/topology/conduits/${encodeURIComponent(conduitId)}/srlgs?region=${encodeURIComponent(region)}`;
}

export function srlgSummaryUrl(region: string): string {
  return `/api/topology/srlg-summary?region=${encodeURIComponent(region)}`;
}

export type PanelSrlgListMode = "loading" | "list" | "unavailable";

/**
 * Panel list body. A live but empty response while the summary says M>0 is a mismatch.
 * It is treated as unavailable, never shown as an empty or zero section.
 */
export function panelSrlgListMode(state: string | null, loaded: number): PanelSrlgListMode {
  if (state === null) return "loading";
  if (state === "live" && loaded > 0) return "list";
  return "unavailable";
}
