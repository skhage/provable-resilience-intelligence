/**
 * Lakelink Fiber — diversity badge copy (BUG-DW-099, @designer S43 binding).
 *
 * One label map shared by the /topology desktop banner, the legend and the
 * mobile tree badge. diversity_status is derived from traced path structure
 * (BUG-QA-080 classify_diversity), so it can legitimately differ from the
 * scored-snapshot grade on the Service Table. Each view names its basis.
 *
 * Pure module: no imports, so Node can evaluate it in tests.
 */

export type DiversityStatus = "fully_diverse" | "partially_diverse" | "single_path" | "unknown";

/** Sentence-case labels. "unknown" now means no working hops were traced. */
export const DIVERSITY_LABELS: Record<DiversityStatus, string> = {
  fully_diverse: "Fully diverse",
  partially_diverse: "Partially diverse",
  single_path: "Single path",
  unknown: "No path data",
};

/** Short labels for the mobile tree badge. */
export const DIVERSITY_SHORT_LABELS: Record<DiversityStatus, string> = {
  fully_diverse: "Diverse",
  partially_diverse: "Partial",
  single_path: "Single",
  unknown: "No data",
};

/** Legend / badge order. */
export const DIVERSITY_STATUS_ORDER: DiversityStatus[] = [
  "fully_diverse",
  "partially_diverse",
  "single_path",
  "unknown",
];

/** Caption shown under the banner badge (only when the badge is shown). */
export const DIVERSITY_BASIS_CAPTION = "From traced working and protect hops.";

function normalize(status: string | null | undefined): DiversityStatus {
  return status && Object.prototype.hasOwnProperty.call(DIVERSITY_LABELS, status)
    ? (status as DiversityStatus)
    : "unknown";
}

/** Full label; null, undefined and unrecognised statuses map to "No path data". */
export function diversityLabel(status: string | null | undefined): string {
  return DIVERSITY_LABELS[normalize(status)];
}

/** Short mobile label; unrecognised statuses map to "No data". */
export function diversityShortLabel(status: string | null | undefined): string {
  return DIVERSITY_SHORT_LABELS[normalize(status)];
}

/** " · N shared conduits" (singular for 1). Empty when count is 0/absent. `fmt` formats N. */
export function sharedConduitStat(
  count: number | null | undefined,
  fmt: (n: number) => string = (n) => n.toLocaleString("en-US"),
): string {
  if (!count || count <= 0) return "";
  return ` \u00B7 ${fmt(count)} shared ${count === 1 ? "conduit" : "conduits"}`;
}

/**
 * Full sentence naming the scored-snapshot basis. Kept for non-table contexts
 * (tooltips, exports). BUG-DW-107: the Service Table pill no longer uses it as
 * an aria-label/title, because naming a generic span is not reliably announced.
 */
export function snapshotGradeLabel(grade: string | null | undefined): string {
  return `Path diversity grade (scored snapshot): ${grade ?? "not rated"}`;
}

/** BUG-DW-107: visible Service Table column header (sentence case) + qualifier line. */
export const PATH_DIV_HEADER = "Path div.";
export const PATH_DIV_HEADER_QUALIFIER = "(snapshot)";

/**
 * BUG-DW-107: sr-only text rendered inside the pill, before the visible letter,
 * so each cell reads "Scored snapshot grade C". Missing grade: the pill has no
 * visible letter, so the spoken text carries "not rated" on its own.
 */
export function snapshotGradeSrText(grade: string | null | undefined): string {
  return grade ? "Scored snapshot grade " : "Scored snapshot grade: not rated";
}
