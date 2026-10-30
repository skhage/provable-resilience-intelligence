/**
 * P36-APP-V4-CONDUIT-COVERAGE-FILTER (V4-KPI-COPY-SPEC §3, BINDING @designer).
 * Lakelink Fiber - Provable Resilience Intelligence.
 *
 * Pure helpers for the /topology "Conduits" coverage filter chips. Only used when PRI_V4_KPIS
 * is on: the v4 topology API then sends span_coverage_class per conduit. With the flag off the
 * field is null, the chip group is not rendered, and every conduit is shown (v3 freeze UI).
 *
 * Self-contained (no "@/" imports) so Node can evaluate it directly in tests.
 */

export type CoverageChip = "segmented" | "backbone" | "inventory";
export type CoverageSelection = Record<CoverageChip, boolean>;

/** Display order of the chips. */
export const COVERAGE_CHIPS: readonly CoverageChip[] = ["segmented", "backbone", "inventory"];

export const COVERAGE_CHIP_LABELS: Record<CoverageChip, string> = {
  segmented: "Segmented",
  backbone: "Backbone only",
  inventory: "Inventory only",
};

/** Group label for the chip set (spec §3). */
export const COVERAGE_GROUP_LABEL = "Conduits";

/** Default = conduits with span geometry (Segmented + Backbone only), per DEC-PRI-FREEZE-V4-SCOPE (B12). */
export const DEFAULT_COVERAGE_SELECTION: CoverageSelection = Object.freeze({
  segmented: true,
  backbone: true,
  inventory: false,
}) as CoverageSelection;

/** Hover + aria text for inventory-only edges (spec §3). */
export const INVENTORY_ONLY_TEXT = "Inventory only: no span geometry";

/** Dotted iron stroke for inventory-only edges (spec §3). */
export const INVENTORY_ONLY_DASH = "2,4";

const CLASS_TO_CHIP: Record<string, CoverageChip> = {
  REAL_SEGMENTED: "segmented",
  BB_SEGMENTED: "backbone", // DE B2 (conduit_v4 v29): CDT-BBR-* routes carrying BBS-* segments
  BB_ONLY: "backbone", // superseded P35 value, kept so it never falls out of the filter
  INVENTORY_ONLY: "inventory",
};

/** Chip for a span_coverage_class. Unknown / null classes return null (never filtered out). */
export function chipForClass(cls: string | null | undefined): CoverageChip | null {
  if (typeof cls !== "string") return null;
  return Object.prototype.hasOwnProperty.call(CLASS_TO_CHIP, cls) ? CLASS_TO_CHIP[cls] : null;
}

export function isInventoryOnly(c: { span_coverage_class?: string | null }): boolean {
  return chipForClass(c.span_coverage_class) === "inventory";
}

/** True when the API sent a coverage class on at least one row (i.e. the v4 topology source). */
export function hasCoverageClasses(conduits: ReadonlyArray<{ span_coverage_class?: string | null }>): boolean {
  return conduits.some((c) => chipForClass(c.span_coverage_class) !== null);
}

/** Per-chip counts over the conduits the API returned for the region (never hard-coded). */
export function countByChip(
  conduits: ReadonlyArray<{ span_coverage_class?: string | null }>,
): Record<CoverageChip, number> {
  const out: Record<CoverageChip, number> = { segmented: 0, backbone: 0, inventory: 0 };
  for (const c of conduits) {
    const chip = chipForClass(c.span_coverage_class);
    if (chip) out[chip] += 1;
  }
  return out;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US"); // §6.4 thousands separator
}

/** Visible chip text, e.g. "Inventory only (1,824)". */
export function chipLabel(chip: CoverageChip, count: number): string {
  return `${COVERAGE_CHIP_LABELS[chip]} (${fmt(count)})`;
}

/**
 * Visibility rule. A conduit is shown when its chip is selected, when its class is unknown,
 * or when it is pinned (on the traced service path or currently selected): the filter must never
 * hide a hop of the path the user asked to trace.
 */
export function isConduitVisible(
  c: { conduit_id: string; span_coverage_class?: string | null },
  selection: CoverageSelection,
  pinnedIds?: ReadonlySet<string> | null,
): boolean {
  if (pinnedIds && pinnedIds.has(c.conduit_id)) return true;
  const chip = chipForClass(c.span_coverage_class);
  return chip === null ? true : selection[chip] === true;
}

export function filterConduits<T extends { conduit_id: string; span_coverage_class?: string | null }>(
  conduits: ReadonlyArray<T>,
  selection: CoverageSelection,
  pinnedIds?: ReadonlySet<string> | null,
): T[] {
  return conduits.filter((c) => isConduitVisible(c, selection, pinnedIds));
}

export function toggleChip(selection: CoverageSelection, chip: CoverageChip): CoverageSelection {
  return { ...selection, [chip]: !selection[chip] };
}

/** Persistent sr-only status text, e.g. "Showing 32 of 160 conduits." */
export function coverageFilterStatus(visible: number, total: number): string {
  const noun = total === 1 ? "conduit" : "conduits";
  return `Showing ${fmt(visible)} of ${fmt(total)} ${noun}.`;
}
