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
