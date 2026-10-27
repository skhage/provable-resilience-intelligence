/**
 * Lakelink Fiber — Backbone SRLG coverage disclosure (P36-APP-V4-BB-SRLG-DISCLOSURE)
 * V4-KPI-COPY-SPEC §2 (surfaces), §6.3 (metro/access qualifier), §6.4 (count formatting).
 *
 * All copy is verbatim from the spec. State comes only from the API field
 * ResilienceSummaryOut.bb_srlg_coverage (null when PRI_V4_KPIS is off, so every
 * caller renders the v3 freeze UI unchanged).
 */

export type BbSrlgCoverage = "complete" | "partial";

/** §2.1 SRLG Groups tooltip while partial. */
export const BB_SRLG_PARTIAL_TOOLTIP =
  "Backbone (BB-*) routes are modeled at long-haul grain. Their shared-risk groups ship in a later build, so diversity on backbone hops is not yet verified.";
/** §2.2 SRLG Groups tooltip once complete (definition only). */
export const SRLG_DEFINITION =
  "Groups of spans that share a physical risk, such as a conduit, bridge or central office.";

export const SRLG_SUBLINE: Record<BbSrlgCoverage, string> = {
  partial: "Metro/access spans only",
  complete: "Metro, access and backbone",
};

/** §2.1 topology legend line (Shared Risk Groups section). */
export const BB_LEGEND_COVERAGE_LINE = "Coverage: metro/access spans. Backbone not yet included.";
/** §2.1 BB edge aria/hover suffix. Never 'No shared risk' / '0 SRLGs'. */
export const BB_EDGE_CAVEAT = "Backbone span: shared-risk data not available";
/** §2.1 diversity badge second line. */
export const BB_UNVERIFIED = "Backbone unverified";

/** §6.3 qualifier: visual uses the slash, speech says "metro and access". */
export const METRO_ACCESS = "(metro/access)";
export const METRO_ACCESS_SPOKEN = "metro and access";
const NBSP = "\u00A0";

/** `74.2% (metro/access)` while partial; the bare value otherwise (§6.3). */
export function withMetroAccess(value: string, coverage: BbSrlgCoverage | null): string {
  return coverage === "partial" ? `${value}${NBSP}${METRO_ACCESS}` : value;
}

/** §6.4 counts: thousands separators. */
export function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Backbone is identified by SPAN id (BB-* v3, BBS-* v4 segments), never by conduit prefix:
 * CDT-BB-* conduits carry SPAN-* metro spans. The API sends backbone_span_count per conduit
 * (v3: 90 backbone-only conduits, 2 mixed).
 */
export function isBackboneSpan(spanId: string | null | undefined): boolean {
  return !!spanId && spanId.startsWith("BB");
}
type EdgeSpanCounts = { span_count: number; backbone_span_count?: number | null };
/** Any backbone span in the conduit: append the BB caveat to aria/hover text. */
export function hasBackboneSpans(c: EdgeSpanCounts): boolean {
  return (c.backbone_span_count ?? 0) > 0;
}
/** Only backbone spans: no SRLG badge at all (§2.1). */
export function isBackboneOnly(c: EdgeSpanCounts): boolean {
  return hasBackboneSpans(c) && (c.backbone_span_count ?? 0) >= c.span_count;
}

/** §2.1: only diverse services crossing backbone get the second badge line. */
export function showBackboneUnverified(
  coverage: BbSrlgCoverage | null,
  diversityStatus: string | undefined,
  crossesBackbone: boolean | null | undefined,
): boolean {
  return (
    coverage === "partial" &&
    crossesBackbone === true &&
    (diversityStatus === "fully_diverse" || diversityStatus === "partially_diverse")
  );
}
