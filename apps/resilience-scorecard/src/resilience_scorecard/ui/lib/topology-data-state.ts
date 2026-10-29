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

// BUG-DW-106 item 4: 'auth_expired' = 401/403. A Retry cannot fix it, so it gets its own copy.
export type DataState = "live" | "unavailable" | "not_found" | "auth_expired";

export const DATA_SOURCE_HEADER = "X-PRI-Data-Source";

/** Neutral outage copy (iron on white). Not a risk signal: never orange/red. */
export const PATH_UNAVAILABLE_MSG = "Path data is temporarily unavailable.";
export const RETRY_LABEL = "Retry";
/** BUG-DW-106 item 4: 401/403 copy. Neutral iron, no Retry (reloading re-authenticates). */
export const SESSION_EXPIRED_MSG = "Your session may have expired. Reload the page.";

export function serviceNotFoundMsg(serviceId: string): string {
  return `Service ${serviceId} not found.`;
}

export function srlgUnavailableMsg(region: string): string {
  return `SRLG data unavailable for ${region}.`;
}

/**
 * Classify a fetch result. 401/403 is auth_expired (BUG-DW-106). Otherwise the
 * header 'unavailable' or any 5xx wins; 404 is not_found; any other 2xx is live
 * (a missing header on 2xx is treated as live so older backends keep the v3
 * render). Any other status is unavailable.
 */
export function classifyResponse(status: number, dataSource: string | null | undefined): DataState {
  if (status === 401 || status === 403) return "auth_expired";
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

export type TraceBannerMode = "pending" | "live" | "unavailable" | "not_found" | "auth_expired";

/**
 * Combined mode for the path banner and mobile tree summary.
 * - either fetch still pending -> 'pending' (render nothing new)
 * - either fetch 401/403 -> 'auth_expired' (BUG-DW-106: no other result can be trusted)
 * - diversity 404 -> 'not_found' (a successful live query proved the service is absent)
 * - path or diversity unavailable -> 'unavailable' (no badge, no hop stats)
 * - otherwise 'live' (v3 render unchanged)
 */
export function traceBannerMode(path: DataState | null, diversity: DataState | null): TraceBannerMode {
  if (path === null || diversity === null) return "pending";
  if (path === "auth_expired" || diversity === "auth_expired") return "auth_expired";
  if (diversity === "not_found" || path === "not_found") return "not_found";
  if (path === "unavailable" || diversity === "unavailable") return "unavailable";
  return "live";
}

/** Message for a non-live banner mode, or null when the live/pending render applies. */
export function traceBannerMessage(mode: TraceBannerMode, serviceId: string): string | null {
  if (mode === "unavailable") return PATH_UNAVAILABLE_MSG;
  if (mode === "not_found") return serviceNotFoundMsg(serviceId);
  if (mode === "auth_expired") return SESSION_EXPIRED_MSG;
  return null;
}

/**
 * BUG-DW-106: Retry is offered only for a transient outage. not_found and
 * auth_expired cannot be fixed by retrying. Shared by the banner and mobile summary.
 */
export function showTraceRetry(mode: TraceBannerMode): boolean {
  return mode === "unavailable";
}

/** Whether the legend should show the SRLG-unavailable line (overlay on + region + outage). */
export function showSrlgUnavailable(srlgOn: boolean, region: string | null, state: DataState | null): boolean {
  return srlgOn && !!region && (state === "unavailable" || state === "auth_expired");
}

// ---------------------------------------------------------------------------
// BUG-DW-105: Retry state labels and feedback copy
// ---------------------------------------------------------------------------

/** Retry button label while a request is in flight. */
export const RETRYING_LABEL = "Retrying\u2026";

/**
 * Feedback message after a repeat Retry failure, with the local time.
 * tabular-nums is applied in CSS so the clock digits don't reflow.
 */
export function stillUnavailableMsg(now: Date): string {
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  // BUG-DW-111 item 5: keep the subject so the repeat-failure line stands on its own
  return `Path data is still unavailable. Last checked ${hh}:${mm}.`;
}

// ---------------------------------------------------------------------------
// BUG-DW-111: live trace announcement + 0-hop live banner copy
// ---------------------------------------------------------------------------

/** Banner/status copy when the live query succeeded but returned no path hops. */
export function noTracedPathMsg(serviceId: string): string {
  return `No traced path for ${serviceId}.`;
}

function hopCount(n: number, kind: string): string {
  return `${n.toLocaleString("en-US")} ${kind} hop${n === 1 ? "" : "s"}`;
}

/**
 * Concise summary written to the persistent sr-only status region in live mode
 * (WCAG 4.1.3). The static basis caption is deliberately NOT included.
 * 0 hops in total -> the "No traced path" copy.
 */
export function traceLiveSummary(
  serviceId: string,
  diversityLabel: string,
  workingHops: number,
  protectHops: number,
): string {
  if (workingHops + protectHops === 0) return noTracedPathMsg(serviceId);
  const protect = protectHops > 0 ? hopCount(protectHops, "protect") : "no protect path";
  return `${serviceId} traced: ${diversityLabel}, ${hopCount(workingHops, "working")}, ${protect}.`;
}

/**
 * Single source of text for the persistent trace status region.
 * Priority: Retrying… > repeat-failure feedback > non-live message > live summary.
 * Pending -> "" (region stays mounted and empty).
 */
export function traceStatusText(opts: {
  mode: TraceBannerMode;
  serviceId: string;
  busy: boolean;
  retryFeedback: string | null;
  diversityLabel: string;
  workingHops: number;
  protectHops: number;
}): string {
  if (opts.busy) return RETRYING_LABEL;
  if (opts.retryFeedback) return opts.retryFeedback;
  const nonLive = traceBannerMessage(opts.mode, opts.serviceId);
  if (nonLive) return nonLive;
  if (opts.mode === "live") {
    return traceLiveSummary(opts.serviceId, opts.diversityLabel, opts.workingHops, opts.protectHops);
  }
  return "";
}
