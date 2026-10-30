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
  hopsShown: HopsShown | null = null,
): string {
  if (workingHops + protectHops === 0) return noTracedPathMsg(serviceId);
  const protect = protectHops > 0 ? hopCount(protectHops, "protect") : "no protect path";
  const base = `${serviceId} traced: ${diversityLabel}, ${hopCount(workingHops, "working")}, ${protect}.`;
  // BUG-DW-118 item 4: the hops-shown sentence is appended once, only when some hops are undrawn
  const shown = hopsShownSpoken(hopsShown);
  return shown ? `${base} ${shown}.` : base;
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
  /** BUG-DW-118: drawn/total hop counts for the current map; null = no map scope */
  hopsShown?: HopsShown | null;
}): string {
  if (opts.busy) return RETRYING_LABEL;
  if (opts.retryFeedback) return opts.retryFeedback;
  const nonLive = traceBannerMessage(opts.mode, opts.serviceId);
  if (nonLive) return nonLive;
  if (opts.mode === "live") {
    return traceLiveSummary(
      opts.serviceId,
      opts.diversityLabel,
      opts.workingHops,
      opts.protectHops,
      opts.hopsShown ?? null,
    );
  }
  return "";
}

// ---------------------------------------------------------------------------
// BUG-DW-118: "{drawn} of {total} hops shown on this map" disclosure
// ---------------------------------------------------------------------------
// The site map draws only tier 1/2 conduits for the selected region. Hops on conduits with a
// tier 3 (access/hut) endpoint, or with no conduit, are counted in the banner but never drawn.

export interface HopsShown {
  drawn: number;
  total: number;
}

/** Tooltip text (V4-KPI-COPY-SPEC section 1 Info pattern). */
export const HOPS_SHOWN_TOOLTIP =
  "Some hops run through access and hut sites (tier 3), which this map does not draw. The hop count includes them.";

/** Same output as formatCount in bb-srlg-disclosure.ts (kept local: this module has no imports). */
function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Count trace hops the site map actually draws: the hop's conduit is in the rendered
 * (region-scoped, coverage-filtered) conduit list and, when siteIds is given, both conduit
 * endpoints have a node on the map (SiteGraph skips edges without positions).
 */
export function countHopsShown(
  hops: ReadonlyArray<{ conduit_id: string | null }>,
  conduits: ReadonlyArray<{ conduit_id: string; site_a_id?: string; site_z_id?: string }>,
  siteIds?: ReadonlySet<string> | null,
): HopsShown {
  const drawable = new Set<string>();
  for (const c of conduits) {
    if (siteIds && (!c.site_a_id || !c.site_z_id || !siteIds.has(c.site_a_id) || !siteIds.has(c.site_z_id))) {
      continue;
    }
    drawable.add(c.conduit_id);
  }
  let drawn = 0;
  for (const h of hops) if (h.conduit_id && drawable.has(h.conduit_id)) drawn += 1;
  return { drawn, total: hops.length };
}

/** True only when some hops are not drawn (item 5: omit the line when drawn == total). */
export function showHopsShown(hs: HopsShown | null | undefined): hs is HopsShown {
  return !!hs && hs.total > 0 && hs.drawn < hs.total;
}

/** Visible line: "4 of 6 hops shown on this map", or null when nothing is hidden. */
export function hopsShownLine(hs: HopsShown | null | undefined): string | null {
  if (!showHopsShown(hs)) return null;
  return `${fmt(hs.drawn)} of ${fmt(hs.total)} hops shown on this map`;
}

/** Spoken form (Info button aria-label + live announcement), no trailing period. */
export function hopsShownSpoken(hs: HopsShown | null | undefined): string | null {
  const line = hopsShownLine(hs);
  return line ? `${line}, others pass through tier 3 sites` : null;
}
