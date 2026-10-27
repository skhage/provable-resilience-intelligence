/**
 * Lakelink Fiber — topology live-data state (BUG-DW-098)
 *
 * The backend (BUG-QA-080 / BUG-QA-086) reports data provenance on topology
 * endpoints via the X-PRI-Data-Source header ('live' | 'unavailable'):
 *   - path-trace and srlgs: 200 + [] + header 'unavailable' when the live query fails
 *   - diversity: 503 + header 'unavailable' on failure, 404 only when the service
 *     genuinely does not exist (query succeeded with zero rows)
 *
 * An outage must never render as a finding (no badge, no hop stats, no silent
 * empty SRLG overlay). These pure helpers keep that logic testable without a DOM.
 */

export type DataState = "live" | "unavailable" | "not_found";

export const DATA_SOURCE_HEADER = "X-PRI-Data-Source";

/** Neutral outage copy (iron on white). Not a risk signal: never orange/red. */
export const PATH_UNAVAILABLE_MSG = "Path data is temporarily unavailable.";
export const RETRY_LABEL = "Retry";

export function serviceNotFoundMsg(serviceId: string): string {
  return `Service ${serviceId} not found.`;
}

export function srlgUnavailableMsg(region: string): string {
  return `SRLG data unavailable for ${region}.`;
}

/**
 * Classify a fetch result. The header 'unavailable' or any 5xx wins; 404 is
 * not_found; any other 2xx is live (a missing header on 2xx is treated as live
 * so older backends keep the v3 render). Any other status is unavailable.
 */
export function classifyResponse(status: number, dataSource: string | null | undefined): DataState {
  if ((dataSource ?? "").toLowerCase() === "unavailable" || status >= 500) return "unavailable";
  if (status === 404) return "not_found";
  if (status >= 200 && status < 300) return "live";
  return "unavailable";
}

export interface StatefulResult<T> {
  state: DataState;
  data: T | null;
}

/** fetch + classify. Network errors and bad JSON are 'unavailable'. Data is null unless live. */
export async function fetchWithState<T>(url: string): Promise<StatefulResult<T>> {
  try {
    const r = await fetch(url);
    const state = classifyResponse(r.status, r.headers.get(DATA_SOURCE_HEADER));
    if (state !== "live") return { state, data: null };
    return { state, data: (await r.json()) as T };
  } catch {
    return { state: "unavailable", data: null };
  }
}

export type TraceBannerMode = "pending" | "live" | "unavailable" | "not_found";

/**
 * Combined mode for the path banner and mobile tree summary.
 * - either fetch still pending -> 'pending' (render nothing new)
 * - diversity 404 -> 'not_found' (a successful live query proved the service is absent)
 * - path or diversity unavailable -> 'unavailable' (no badge, no hop stats)
 * - otherwise 'live' (v3 render unchanged)
 */
export function traceBannerMode(path: DataState | null, diversity: DataState | null): TraceBannerMode {
  if (path === null || diversity === null) return "pending";
  if (diversity === "not_found" || path === "not_found") return "not_found";
  if (path === "unavailable" || diversity === "unavailable") return "unavailable";
  return "live";
}

/** Message for a non-live banner mode, or null when the live/pending render applies. */
export function traceBannerMessage(mode: TraceBannerMode, serviceId: string): string | null {
  if (mode === "unavailable") return PATH_UNAVAILABLE_MSG;
  if (mode === "not_found") return serviceNotFoundMsg(serviceId);
  return null;
}

/** Whether the legend should show the SRLG-unavailable line (overlay on + region + outage). */
export function showSrlgUnavailable(srlgOn: boolean, region: string | null, state: DataState | null): boolean {
  return srlgOn && !!region && state === "unavailable";
}
