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
  return `${n.toLocaleString("en-US")} ${subjectVerb}. Coverage: ${coverage}. Region: ${region || ALL_REGIONS_LABEL}.`;
}
