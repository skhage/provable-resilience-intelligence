/**
 * BUG-DW-131: SVG label counter-scaling helpers.
 *
 * SVG <text> elements sized in viewBox units shrink with the canvas.
 * At narrow viewports (736-960 px) they render below the 12 px house
 * floor. These helpers compute a counter-scaled fontSize so that the
 * rendered size never drops below MIN_LABEL_CSS_PX.
 *
 * Every function is pure and has no imports — Node can evaluate this
 * module directly for testing.
 */

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

/** Minimum rendered CSS px for site and layer labels. */
export const MIN_LABEL_CSS_PX = 10;

/** Canvas scale below which the hazard name label is hidden. */
export const HAZARD_NAME_HIDE_SCALE = 0.8;

/** The viewBox width of the SiteGraph SVG. */
export const SITE_GRAPH_VB_W = 1200;

/** The viewBox height of the SiteGraph SVG. */
export const SITE_GRAPH_VB_H = 600;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/**
 * SVG viewBox-to-CSS-px scale for the default preserveAspectRatio
 * (xMidYMid meet). Returns CSS px per viewBox unit.
 */
export function svgScale(renderedW: number, renderedH: number, vbW: number = SITE_GRAPH_VB_W, vbH: number = SITE_GRAPH_VB_H): number {
  if (renderedW <= 0 || renderedH <= 0) return 1;
  return Math.min(renderedW / vbW, renderedH / vbH);
}

/**
 * Counter-scaled fontSize in viewBox units so that the rendered text
 * is at least `minCssPx` CSS pixels.
 *
 * @param basePx  — the original viewBox fontSize
 * @param scale   — CSS px per viewBox unit (from svgScale)
 * @param minCssPx — floor for the rendered size (default MIN_LABEL_CSS_PX)
 * @returns viewBox fontSize >= basePx
 */
export function scaledFontSize(basePx: number, scale: number, minCssPx: number = MIN_LABEL_CSS_PX): number {
  if (scale <= 0) return basePx;
  return Math.max(basePx, minCssPx / scale);
}

/**
 * Whether the hazard name label should be rendered.
 * Hidden at small scales because the keyboard callout, hover <title>,
 * and aria-label already carry the name.
 */
export function showHazardNameLabel(scale: number): boolean {
  return scale >= HAZARD_NAME_HIDE_SCALE;
}

/**
 * The rendered CSS px for a given viewBox fontSize at a given scale.
 * Useful for testing assertions.
 */
export function renderedPx(viewBoxFontSize: number, scale: number): number {
  return viewBoxFontSize * scale;
}

/* ------------------------------------------------------------------ */
/*  BUG-DW-132: CLLI label fitting                                     */
/* ------------------------------------------------------------------ */

/** Advance width of one monospace glyph, in em (var(--font-mono)). */
export const CLLI_CHAR_EM = 0.6;

/** Minimum clear gap between two adjacent CLLI labels, in viewBox units. */
export const CLLI_LABEL_GAP = 4;

/** Estimated rendered width of a CLLI label in viewBox units: len x 0.6 x fontSize. */
export function clliLabelWidth(len: number, fontSizeVB: number): number {
  return Math.max(0, len) * CLLI_CHAR_EM * fontSizeVB;
}

/**
 * Whether a CLLI label fits between its row neighbours: estimatedWidth <= spacing - gap.
 * The 10 px floor is never dropped; a label that does not fit is hidden instead.
 */
export function showClliLabel(len: number, fontSizeVB: number, spacingVB: number): boolean {
  return clliLabelWidth(len, fontSizeVB) <= spacingVB - CLLI_LABEL_GAP;
}

export interface ClliRowSite {
  id: string;
  /** Label centre x in viewBox units (text-anchor middle). */
  x: number;
  /** Characters in the label. */
  len: number;
}

/**
 * Ids of the CLLI labels to draw on one tier row.
 *
 * A label is a candidate when it fits at the row spacing (showClliLabel) or its site is
 * prioritised (selected, focused, on the traced path; pass them most important first).
 * Candidates are admitted greedily (priority ids in the given order, then by x) and a
 * label is skipped if it would overlap a label already admitted, so no two drawn labels
 * ever overlap. A skipped CLLI is still available in the site's <title> and aria-label.
 */
export function clliLabelIds(
  row: ReadonlyArray<ClliRowSite>,
  fontSizeVB: number,
  spacingVB: number,
  priorityIds: ReadonlyArray<string | null | undefined> = [],
): Set<string> {
  const byId = new Map(row.map((s) => [s.id, s]));
  const order: ClliRowSite[] = [];
  const seen = new Set<string>();
  for (const id of priorityIds) {
    if (!id || seen.has(id)) continue;
    const s = byId.get(id);
    if (!s) continue;
    seen.add(id);
    order.push(s);
  }
  const rest = row
    .filter((s) => !seen.has(s.id) && showClliLabel(s.len, fontSizeVB, spacingVB))
    .sort((a, b) => a.x - b.x);
  order.push(...rest);

  const admitted: ClliRowSite[] = [];
  for (const s of order) {
    const half = clliLabelWidth(s.len, fontSizeVB) / 2;
    const clashes = admitted.some((a) => {
      const minDist = half + clliLabelWidth(a.len, fontSizeVB) / 2 + CLLI_LABEL_GAP;
      return Math.abs(a.x - s.x) < minDist;
    });
    if (!clashes) admitted.push(s);
  }
  return new Set(admitted.map((s) => s.id));
}
