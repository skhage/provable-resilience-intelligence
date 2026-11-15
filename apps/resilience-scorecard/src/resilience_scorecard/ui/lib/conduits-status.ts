/**
 * BUG-DW-095 (BINDING @designer S39). Lakelink Fiber - Provable Resilience Intelligence.
 *
 * Copy for the persistent /conduits filter status region (.filter-result-count, role=status,
 * aria-atomic). The region lives outside Suspense, so it must never keep the previous filter's
 * count while a new query is loading or after the list fails (WCAG 4.1.3 / 3.3.1).
 *
 * Self-contained (no "@/" imports) so Node can evaluate it directly in tests.
 */

/** Shown in the region filter as the empty option and used in the status string. */
export const ALL_REGIONS_LABEL = "All regions";

/** Announced as soon as a filter changes or Retry is pressed, before the new data arrives. */
export const CONDUITS_LOADING_MSG = "Loading conduits\u2026";

/** Announced when the conduit list query fails and the error fallback is shown. */
export const CONDUITS_FAILED_MSG = "Conduits failed to load.";

/**
 * "12 conduits match. Coverage: Real segmented. Region: All regions."
 * BUG-DW-128: subject-verb agreement, so 1 reads "1 conduit matches." and 0/N read "N conduits match."
 */
export function conduitResultMessage(n: number, coverageLabel: string, region?: string | null): string {
  const subjectVerb = n === 1 ? "conduit matches" : "conduits match";
  const coverage = coverageLabel.replace(" (default)", "");
  return `${fmtCount(n)} ${subjectVerb}. Coverage: ${coverage}. Region: ${region || ALL_REGIONS_LABEL}.`;
}

/**
 * BUG-DW-179 (BINDING @designer S131): one locale for every number on /conduits, so a de-DE or
 * fr-FR browser never mixes "1.914" with "1,914". Counts are thousands-grouped integers.
 */
export function fmtCount(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * BUG-DW-179: kilometre values always show exactly one decimal, so whole values keep their decimal
 * (372 -> "372.0") and stay aligned with "1,791.2" in the right-aligned td.num columns.
 */
export function fmtKm(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

/** BUG-DW-179 (c): subject-verb agreement (BUG-DW-128 rule) and grouping, no "conduit(s)". */
export function noCoordsMessage(n: number): string {
  return n === 1
    ? "1 conduit has no site coordinates and is listed in the table only."
    : `${fmtCount(n)} conduits have no site coordinates and are listed in the table only.`;
}
