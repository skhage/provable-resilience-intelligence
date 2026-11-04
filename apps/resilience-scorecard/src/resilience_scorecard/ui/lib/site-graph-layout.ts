/**
 * BUG-DW-133: SiteGraph drill-in layout with a per-tier site cap.
 *
 * Before this fix layoutSites put every tier-1 site on one row (y=120) at max(60, 1100/n)
 * spacing and every tier-2 site on one row (y=380) at max(50, 1100/n). Live regions carry
 * 104-171 T1 and 61-76 T2 sites, so x ran out to ~10,250 viewBox units: only 19 T1 and
 * 23 T2 sites fell inside the 1200-unit viewBox. The rest were clipped yet still focusable
 * (WCAG 2.4.3 / 2.4.7), and the svg name announced totals nobody could see (1.3.1).
 *
 * Chosen fix (designer option 2): each tier row draws at most as many sites as fit at the
 * minimum spacing (T1 18, T2 22). Pinned sites (selected, on the traced path, endpoints of
 * the selected conduit) are drawn first, then the most connected sites (conduit_count desc,
 * site_id asc as the tie-break). Sites that are not drawn are not rendered at all, so they
 * are out of the tab order. The page shows "Showing N of M backbone sites" plus a
 * "Show all sites" list that reaches every site in the region.
 *
 * Pure module: no imports, so Node --experimental-strip-types can load it in tests.
 */

export const SITE_CANVAS_W = 1200;
export const SITE_ROW_MARGIN = 50;
export const SITE_ROW_Y_T1 = 120;
export const SITE_ROW_Y_T2 = 380;
export const SITE_MIN_SPACING_T1 = 60;
export const SITE_MIN_SPACING_T2 = 50;
export const SITE_RADIUS_T1 = 20;
export const SITE_RADIUS_T2 = 14;

export type SiteTier = "tier_1" | "tier_2";

export interface LayoutSite {
  site_id: string;
  tier: string | null;
  conduit_count: number;
}

export interface TierCount {
  shown: number;
  total: number;
}

export interface SiteCap<S extends LayoutSite> {
  /** Sites drawn on the map, in their original (API) order. */
  visible: S[];
  /** Tiered sites that are not drawn. */
  hidden: S[];
  t1: TierCount;
  t2: TierCount;
  /** Pinned sites that still did not fit (only when pins exceed a row's capacity). */
  pinnedNotShown: number;
}

/** Usable row width in viewBox units (1100). */
export function rowWidth(canvasW: number = SITE_CANVAS_W): number {
  return canvasW - 2 * SITE_ROW_MARGIN;
}

/** Max sites one tier row can draw at its minimum spacing: T1 18, T2 22 at 1200 wide. */
export function tierCapacity(tier: SiteTier, canvasW: number = SITE_CANVAS_W): number {
  const minSpacing = tier === "tier_1" ? SITE_MIN_SPACING_T1 : SITE_MIN_SPACING_T2;
  return Math.max(1, Math.floor(rowWidth(canvasW) / minSpacing));
}

function rankTier<S extends LayoutSite>(
  tierSites: S[],
  pinned: ReadonlySet<string>,
  cap: number,
): { keep: Set<string>; pinnedNotShown: number } {
  const ranked = [...tierSites].sort((a, b) => {
    const pa = pinned.has(a.site_id) ? 1 : 0;
    const pb = pinned.has(b.site_id) ? 1 : 0;
    if (pa !== pb) return pb - pa;
    const ca = a.conduit_count ?? 0;
    const cb = b.conduit_count ?? 0;
    if (ca !== cb) return cb - ca;
    return a.site_id < b.site_id ? -1 : a.site_id > b.site_id ? 1 : 0;
  });
  const keep = new Set(ranked.slice(0, cap).map((s) => s.site_id));
  let pinnedNotShown = 0;
  for (const s of tierSites) if (pinned.has(s.site_id) && !keep.has(s.site_id)) pinnedNotShown += 1;
  return { keep, pinnedNotShown };
}

/**
 * Pick the sites to draw. Sites whose tier is neither tier_1 nor tier_2 were never placed
 * by the old layout either; they are excluded from both visible and hidden.
 */
export function capSites<S extends LayoutSite>(
  sites: ReadonlyArray<S>,
  pinnedIds: ReadonlySet<string> = new Set(),
  canvasW: number = SITE_CANVAS_W,
): SiteCap<S> {
  const t1 = sites.filter((s) => s.tier === "tier_1");
  const t2 = sites.filter((s) => s.tier === "tier_2");
  const r1 = rankTier(t1, pinnedIds, tierCapacity("tier_1", canvasW));
  const r2 = rankTier(t2, pinnedIds, tierCapacity("tier_2", canvasW));
  const visible: S[] = [];
  const hidden: S[] = [];
  for (const s of sites) {
    if (s.tier === "tier_1") (r1.keep.has(s.site_id) ? visible : hidden).push(s);
    else if (s.tier === "tier_2") (r2.keep.has(s.site_id) ? visible : hidden).push(s);
  }
  return {
    visible,
    hidden,
    t1: { shown: r1.keep.size, total: t1.length },
    t2: { shown: r2.keep.size, total: t2.length },
    pinnedNotShown: r1.pinnedNotShown + r2.pinnedNotShown,
  };
}

/**
 * Positions for the drawn sites. Each row is spread evenly over the 1100-unit row width;
 * because a row never holds more than tierCapacity sites, spacing never drops below the
 * tier minimum and every centre x lies in [50 + s/2, 1150 - s/2], well inside [r, 1200 - r].
 */
export function layoutVisibleSites(
  visible: ReadonlyArray<LayoutSite>,
  canvasW: number = SITE_CANVAS_W,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const place = (row: LayoutSite[], minSpacing: number, y: number) => {
    const spacing = Math.max(minSpacing, rowWidth(canvasW) / Math.max(row.length, 1));
    row.forEach((s, i) => {
      positions.set(s.site_id, { x: SITE_ROW_MARGIN + i * spacing + spacing / 2, y });
    });
  };
  place(visible.filter((s) => s.tier === "tier_1"), SITE_MIN_SPACING_T1, SITE_ROW_Y_T1);
  place(visible.filter((s) => s.tier === "tier_2"), SITE_MIN_SPACING_T2, SITE_ROW_Y_T2);
  return positions;
}

/** Spacing actually used by a tier row (BUG-DW-132 needs this for CLLI label fitting). */
export function rowSpacing(
  shown: number,
  tier: SiteTier,
  canvasW: number = SITE_CANVAS_W,
): number {
  const minSpacing = tier === "tier_1" ? SITE_MIN_SPACING_T1 : SITE_MIN_SPACING_T2;
  return Math.max(minSpacing, rowWidth(canvasW) / Math.max(shown, 1));
}

export function hasHiddenSites(cap: SiteCap<LayoutSite> | null | undefined): boolean {
  return !!cap && cap.hidden.length > 0;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/**
 * Visible note (12px iron): "Showing 18 of 171 backbone sites and 22 of 76 regional sites,
 * most connected first." Only tiers with hidden sites are listed; null when nothing is hidden.
 */
export function siteCapNote(cap: SiteCap<LayoutSite> | null | undefined): string | null {
  if (!hasHiddenSites(cap)) return null;
  const c = cap as SiteCap<LayoutSite>;
  const parts: string[] = [];
  if (c.t1.shown < c.t1.total) {
    parts.push(`${fmt(c.t1.shown)} of ${fmt(c.t1.total)} backbone ${plural(c.t1.total, "site", "sites")}`);
  }
  if (c.t2.shown < c.t2.total) {
    parts.push(`${fmt(c.t2.shown)} of ${fmt(c.t2.total)} regional ${plural(c.t2.total, "site", "sites")}`);
  }
  return `Showing ${parts.join(" and ")}, most connected first.`;
}

export const SITE_LIST_HIDE_LABEL = "Hide site list";

/** Disclosure button label: "Show all 247 sites". */
export function siteListShowLabel(cap: SiteCap<LayoutSite>): string {
  const total = cap.t1.total + cap.t2.total;
  return `Show all ${fmt(total)} ${plural(total, "site", "sites")}`;
}

export const SITE_LIST_NOT_DRAWN = "Not drawn on map";

/**
 * svg role=img name. Unchanged wording when nothing is hidden; otherwise it states what is
 * actually drawn, so the announced totals match what a sighted user can see (1.3.1).
 */
export function siteGraphAriaLabel(
  regionName: string,
  cap: SiteCap<LayoutSite>,
  totalSites: number,
  drawnConduits: number,
  totalConduits: number,
): string {
  if (!hasHiddenSites(cap)) {
    return `${regionName} topology: ${totalSites} sites (${cap.t1.total} backbone, ${cap.t2.total} regional), ${totalConduits} conduits`;
  }
  const shown = cap.t1.shown + cap.t2.shown;
  return (
    `${regionName} topology: showing ${shown} of ${totalSites} sites ` +
    `(${cap.t1.shown} of ${cap.t1.total} backbone, ${cap.t2.shown} of ${cap.t2.total} regional), ` +
    `${drawnConduits} of ${totalConduits} conduits drawn. Use Show all sites for the full list.`
  );
}
