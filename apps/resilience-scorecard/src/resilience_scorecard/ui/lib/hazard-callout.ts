/**
 * BUG-DW-117: visible focus callout for /topology hazard markers.
 *
 * Hazard markers are focusable (tabIndex=0, role=img) but their detail (severity, direct and
 * near impact counts) used to live only in the ancestor hover <title>, which browsers do not
 * show on keyboard focus. Sighted keyboard users now get an aria-hidden SVG callout with the
 * same facts. The aria-label stays the single accessible source (no <title> or
 * aria-describedby on the focusable element: DW-115 invariant).
 *
 * BUG-DW-119: the callout is now an HTML overlay (absolutely positioned inside
 * .topo-canvas-wrap), not SVG content. The topology SVG scales its viewBox (1200x600) to the
 * canvas width, so SVG text at 12 viewBox units rendered at ~7.4px on a 736px canvas. The
 * overlay keeps the 12 CSS px floor at every width. Marker geometry (ring, name label) still
 * scales with the map, so marker extents are multiplied by the viewBox scale; the callout's own
 * font, padding, gap and the CSS focus outline are fixed CSS px.
 *
 * Pure helpers only, so they can be evaluated with Node in tests.
 * Project: Lakelink Fiber - Provable Resilience Intelligence
 */

export interface HazardCalloutInput {
  hazard_id: string;
  hazard_type: string;
  name: string;
  severity: string;
  direct_impact_spans: number;
  near_impact_spans: number;
}

/** Designer spec (BUG-DW-117): iron 12px var(--font-primary) text, 8px padding, 1px iron border. */
export const HAZARD_CALLOUT_FONT_PX = 12;
export const HAZARD_CALLOUT_PAD = 8;
/** Generous per-glyph advance for Inter 400 at 1em, so the box never clips the text. */
export const HAZARD_CALLOUT_ADVANCE = 0.6;
/** .hazard-overlay-marker:focus-visible = 2px outline at 2px offset. */
export const HAZARD_FOCUS_RING_EXTENT = 4;
/** Clear space between the focus ring and the callout box. */
export const HAZARD_CALLOUT_GAP = 4;
/** Minimum distance from the canvas edge. */
export const HAZARD_CALLOUT_MARGIN = 4;
/** Marker geometry from topology.tsx: max ring stroke 2.5 (half = 1.25), name label baseline +30 @ 9px. */
export const HAZARD_MARKER_STROKE_HALF = 1.5;
export const HAZARD_MARKER_LABEL_BOTTOM = 33;

export function hazardTypeLabel(hazardType: string): string {
  return hazardType.replace(/_/g, " ");
}

/** '{type} hazard: {name} · {severity} · N direct / M near spans' */
export function hazardCalloutText(h: HazardCalloutInput): string {
  return (
    `${hazardTypeLabel(h.hazard_type)} hazard: ${h.name} · ${h.severity} · ` +
    `${h.direct_impact_spans} direct / ${h.near_impact_spans} near spans`
  );
}

/** Marker position (unchanged from the inline demo placement in topology.tsx). */
export function hazardMarkerPos(
  hazardId: string,
  canvasW: number,
  canvasH: number,
): { x: number; y: number } {
  const hash = hazardId.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return {
    x: 80 + (hash % (canvasW - 160)),
    y: 60 + ((hash * 7) % (canvasH - 120)),
  };
}

/** Outer proximity ring radius (unchanged). */
export function hazardRingRadius(h: Pick<HazardCalloutInput, "direct_impact_spans">): number {
  return h.direct_impact_spans > 0 ? 30 : 20;
}

export function estimateTextWidth(text: string, fontPx: number = HAZARD_CALLOUT_FONT_PX): number {
  return Array.from(text).length * HAZARD_CALLOUT_ADVANCE * fontPx;
}

/** Truncate with an ellipsis so the box (text + padding) fits within maxBoxWidth. */
export function fitCalloutText(text: string, maxBoxWidth: number): string {
  const maxChars = Math.floor(
    (maxBoxWidth - 2 * HAZARD_CALLOUT_PAD) / (HAZARD_CALLOUT_ADVANCE * HAZARD_CALLOUT_FONT_PX),
  );
  const chars = Array.from(text);
  if (chars.length <= maxChars) return text;
  return chars.slice(0, Math.max(maxChars - 1, 0)).join("") + "…";
}

export interface HazardCalloutBox {
  x: number;
  y: number;
  width: number;
  height: number;
  textX: number;
  textY: number;
  text: string;
  placement: "above" | "below";
}

/**
 * Place the callout above the marker (clear of ring + focus outline); flip below the name
 * label when there is no room above. Clamped to the canvas on both axes.
 *
 * BUG-DW-119: markerScale = CSS px per viewBox unit. cx/cy/canvasW/canvasH are in the same
 * space as the callout (CSS px inside the wrap for the HTML overlay); ringR is in viewBox units
 * and the marker extents (ring + stroke, name label) are multiplied by markerScale. The
 * default of 1 keeps the original viewBox-space behaviour.
 */
export function hazardCalloutBox(
  cx: number,
  cy: number,
  ringR: number,
  rawText: string,
  canvasW: number,
  canvasH: number,
  markerScale: number = 1,
): HazardCalloutBox {
  const m = HAZARD_CALLOUT_MARGIN;
  const text = fitCalloutText(rawText, canvasW - 2 * m);
  const width = Math.ceil(estimateTextWidth(text) + 2 * HAZARD_CALLOUT_PAD);
  const height = HAZARD_CALLOUT_FONT_PX + 2 * HAZARD_CALLOUT_PAD;
  const clear = HAZARD_FOCUS_RING_EXTENT + HAZARD_CALLOUT_GAP;
  const s = markerScale > 0 && Number.isFinite(markerScale) ? markerScale : 1;
  const markerTop = cy - (ringR + HAZARD_MARKER_STROKE_HALF) * s;
  const markerBottom =
    cy + Math.max(ringR + HAZARD_MARKER_STROKE_HALF, HAZARD_MARKER_LABEL_BOTTOM) * s;

  const aboveY = markerTop - clear - height;
  const belowY = markerBottom + clear;
  let placement: "above" | "below";
  if (aboveY >= m) placement = "above";
  else if (belowY + height <= canvasH - m) placement = "below";
  else placement = markerTop >= canvasH - markerBottom ? "above" : "below";

  const rawY = placement === "above" ? aboveY : belowY;
  const y = Math.min(Math.max(rawY, m), Math.max(canvasH - m - height, m));
  const x = Math.min(Math.max(cx - width / 2, m), Math.max(canvasW - m - width, m));
  return {
    x,
    y,
    width,
    height,
    textX: x + HAZARD_CALLOUT_PAD,
    textY: y + height / 2,
    text,
    placement,
  };
}

/**
 * Show the callout for keyboard focus only (mouse users already get the hover tooltip).
 * Falls back to true if :focus-visible is unsupported, so keyboard users never lose it.
 */
export function isKeyboardFocus(el: { matches?: (sel: string) => boolean } | null): boolean {
  if (!el || typeof el.matches !== "function") return true;
  try {
    return el.matches(":focus-visible");
  } catch {
    return true;
  }
}

/**
 * The hazard whose callout should render: only the focused id, only with the overlay on.
 *
 * BUG-DW-119: pass activeHazardId (the data-hazard-id of document.activeElement, or null) to
 * ignore a stale focused id. Toggling the overlay off with 'h' unmounts the focused marker and
 * onBlur is not guaranteed for a removed node. Omit it (undefined) to skip the check.
 */
export function focusedHazardFor<T extends { hazard_id: string }>(
  hazards: readonly T[],
  focusedId: string | null,
  overlayOn: boolean,
  activeHazardId?: string | null,
): T | null {
  if (!overlayOn || !focusedId) return null;
  if (activeHazardId !== undefined && activeHazardId !== focusedId) return null;
  return hazards.find((h) => h.hazard_id === focusedId) ?? null;
}

/** data-hazard-id of the focused element, or null (no element, no attribute, no document). */
export function activeHazardIdOf(
  doc: { activeElement?: { getAttribute?: (name: string) => string | null } | null } | null,
): string | null {
  const el = doc?.activeElement;
  if (!el || typeof el.getAttribute !== "function") return null;
  return el.getAttribute("data-hazard-id") ?? null;
}

/** BUG-DW-119: viewBox user units -> CSS px inside the wrap (overlay positioning space). */
export interface ViewBoxMap {
  /** CSS px per viewBox unit. */
  scale: number;
  /** Wrap-relative CSS px of viewBox (0, 0). */
  ox: number;
  oy: number;
}

/**
 * Map from svg.getScreenCTM() (viewBox -> client px) and the wrap's client rect. Exact,
 * including preserveAspectRatio letterboxing. clientLeft/Top remove the wrap border so the
 * result is relative to the padding box (the containing block of an absolute child).
 */
export function viewBoxToWrap(
  ctm: { a: number; e: number; f: number },
  wrapRect: { left: number; top: number },
  clientLeft: number = 0,
  clientTop: number = 0,
): ViewBoxMap {
  return {
    scale: ctm.a,
    ox: ctm.e - wrapRect.left - clientLeft,
    oy: ctm.f - wrapRect.top - clientTop,
  };
}

/**
 * Fallback when getScreenCTM() is unavailable: the default preserveAspectRatio
 * (xMidYMid meet) for an svg box of svgW x svgH placed at (svgLeft, svgTop) in the wrap.
 */
export function meetViewBoxMap(
  svgW: number,
  svgH: number,
  vbW: number,
  vbH: number,
  svgLeft: number = 0,
  svgTop: number = 0,
): ViewBoxMap {
  const scale = Math.min(svgW / vbW, svgH / vbH);
  return {
    scale,
    ox: svgLeft + (svgW - vbW * scale) / 2,
    oy: svgTop + (svgH - vbH * scale) / 2,
  };
}

export interface HazardCalloutOverlay extends HazardCalloutBox {
  /** Rendered font size in CSS px: always HAZARD_CALLOUT_FONT_PX, whatever the canvas width. */
  fontPx: number;
}

/**
 * BUG-DW-119: callout box in wrap CSS px for the HTML overlay. The marker centre is mapped from
 * viewBox to wrap px; the box is clamped to the wrap (wrapW x wrapH = clientWidth/Height).
 */
export function hazardCalloutOverlay(
  h: HazardCalloutInput,
  map: ViewBoxMap,
  wrapW: number,
  wrapH: number,
  canvasW: number,
  canvasH: number,
): HazardCalloutOverlay {
  const pos = hazardMarkerPos(h.hazard_id, canvasW, canvasH);
  const box = hazardCalloutBox(
    map.ox + pos.x * map.scale,
    map.oy + pos.y * map.scale,
    hazardRingRadius(h),
    hazardCalloutText(h),
    wrapW,
    wrapH,
    map.scale,
  );
  return { ...box, fontPx: HAZARD_CALLOUT_FONT_PX };
}

/** Next focused id after a blur of `blurredId` (ignore stale blurs from other markers). */
export function nextFocusedHazard(current: string | null, blurredId: string): string | null {
  return current === blurredId ? null : current;
}
