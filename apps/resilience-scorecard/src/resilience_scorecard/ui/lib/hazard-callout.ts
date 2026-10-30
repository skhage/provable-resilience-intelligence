/**
 * BUG-DW-117: visible focus callout for /topology hazard markers.
 *
 * Hazard markers are focusable (tabIndex=0, role=img) but their detail (severity, direct and
 * near impact counts) used to live only in the ancestor hover <title>, which browsers do not
 * show on keyboard focus. Sighted keyboard users now get an aria-hidden SVG callout with the
 * same facts. The aria-label stays the single accessible source (no <title> or
 * aria-describedby on the focusable element: DW-115 invariant).
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

/** Designer spec (BUG-DW-117): iron 12px Inter text, 8px padding, 1px iron border. */
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
 */
export function hazardCalloutBox(
  cx: number,
  cy: number,
  ringR: number,
  rawText: string,
  canvasW: number,
  canvasH: number,
): HazardCalloutBox {
  const m = HAZARD_CALLOUT_MARGIN;
  const text = fitCalloutText(rawText, canvasW - 2 * m);
  const width = Math.ceil(estimateTextWidth(text) + 2 * HAZARD_CALLOUT_PAD);
  const height = HAZARD_CALLOUT_FONT_PX + 2 * HAZARD_CALLOUT_PAD;
  const clear = HAZARD_FOCUS_RING_EXTENT + HAZARD_CALLOUT_GAP;
  const markerTop = cy - (ringR + HAZARD_MARKER_STROKE_HALF);
  const markerBottom = cy + Math.max(ringR + HAZARD_MARKER_STROKE_HALF, HAZARD_MARKER_LABEL_BOTTOM);

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

/** The hazard whose callout should render: only the focused id, only with the overlay on. */
export function focusedHazardFor<T extends { hazard_id: string }>(
  hazards: readonly T[],
  focusedId: string | null,
  overlayOn: boolean,
): T | null {
  if (!overlayOn || !focusedId) return null;
  return hazards.find((h) => h.hazard_id === focusedId) ?? null;
}

/** Next focused id after a blur of `blurredId` (ignore stale blurs from other markers). */
export function nextFocusedHazard(current: string | null, blurredId: string): string | null {
  return current === blurredId ? null : current;
}
