/**
 * Lakelink Fiber - header data-source badge (BUG-DW-161, WCAG 4.1.3 Status Messages).
 * Pure functions, no React import, so they can be evaluated with Node in tests.
 *
 * The badge has four states. It says "Mock Data" only when /api/health explicitly
 * reports mock. While the health check is pending it shows a neutral "Checking data
 * source", and when the check fails it shows "Data source unavailable". Neither of
 * those claims the numbers are fake.
 */

export type DataSourceState = "loading" | "live" | "mock" | "unavailable";

export const DATA_SOURCE_LOADING_LABEL = "Checking data source";
export const DATA_SOURCE_UNAVAILABLE_LABEL = "Data source unavailable";
export const DATA_SOURCE_MOCK_LABEL = "Mock Data";

/** Map the /api/health data_source field to a badge state. Anything unexpected is unavailable. */
export function dataSourceFromHealth(value: unknown): DataSourceState {
  if (value === "live") return "live";
  if (value === "mock") return "mock";
  return "unavailable";
}

/** CSS modifier class for .data-source-badge. Each state has its own class. */
export function dataSourceBadgeClass(state: DataSourceState): string {
  return `data-source-badge ${state}`;
}

/** Live label per route (unchanged from the previous inline ternary). */
export function liveDataSourceLabel(pathname: string): string {
  switch (pathname) {
    case "/actions":
      return "Lakebase State";
    case "/hazards":
      return "Live Crosswalk";
    case "/topology":
      return "Live Topology";
    case "/conduits":
      return "Live v4 Coverage";
    default:
      return "Live Data";
  }
}

/** Visible badge text for a state (route-specific when live). Not announced; see below. */
export function dataSourceBadgeLabel(state: DataSourceState, pathname: string): string {
  switch (state) {
    case "live":
      return liveDataSourceLabel(pathname);
    case "mock":
      return DATA_SOURCE_MOCK_LABEL;
    case "unavailable":
      return DATA_SOURCE_UNAVAILABLE_LABEL;
    default:
      return DATA_SOURCE_LOADING_LABEL;
  }
}

/**
 * BUG-DW-182 (WCAG 4.1.3): text for the sr-only role=status live region next to the badge.
 * It depends on the state only, never on the route, so a client-side navigation does not
 * change it and does not trigger an announcement that competes with the BUG-DW-160 focus
 * move to #main-content. "loading" is empty, so the region is mounted empty and speaks
 * only when the health check settles (loading -> live | mock | unavailable).
 */
export function dataSourceAnnouncement(state: DataSourceState): string {
  switch (state) {
    case "live":
      return "Data source: Live Data";
    case "mock":
      return `Data source: ${DATA_SOURCE_MOCK_LABEL}`;
    case "unavailable":
      return "Data source: unavailable";
    default:
      return "";
  }
}
