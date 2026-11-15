/**
 * Lakelink Fiber — InfoTooltip (V4-KPI-COPY-SPEC §1 Info control, §4 tooltip rules)
 *
 * Lucide Info 16px / 1.5px stroke inside a 24x24 button (WCAG 2.5.8 target size).
 * Tooltip (WCAG 1.4.13): opens on hover AND keyboard focus, dismisses on Esc,
 * stays open while the pointer is over the button or the tooltip, and opens
 * above the trigger so it never covers the KPI value below the label.
 * The tooltip text is always wired via aria-describedby, so screen readers get
 * the definition even while it is visually hidden.
 *
 * BUG-DW-092 (SC 1.4.13 Hoverable): two layers keep the tooltip reachable.
 * (1) CSS hover bridge: .info-tooltip::after fills the 6px gap above the
 *     trigger, so the pointer never leaves span.info-tip on the way up.
 * (2) A 150ms close delay on mouseleave, cancelled on re-enter. This covers
 *     sub-pixel gaps at 200% zoom and fast diagonal pointer paths.
 *
 * BUG-DW-180 (SC 1.4.10 Reflow): the tooltip must stay inside the viewport at
 * 320px / 200% zoom. (1) CSS caps the width at min(260px, 100vw - 32px).
 * (2) On open (and on resize while open) the centred position is computed from
 * the trigger rect and the tooltip width; if it would cross the 16px viewport
 * margin, a modifier class anchors it to the trigger's left edge
 * (.info-tooltip--align-start) or right edge (.info-tooltip--align-end).
 * (3) If neither edge anchor fits either (e.g. 260px tooltip, trigger at x=100
 * in a 320px viewport), the centred tooltip is shifted by the exact pixel
 * amount that clamps it inside the margins (--info-tooltip-shift).
 */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { Info } from "lucide-react";

/** Grace period before a hover-opened tooltip closes (BUG-DW-092). */
const HOVER_CLOSE_DELAY_MS = 150;

/** Minimum gap between the tooltip and either viewport edge (BUG-DW-180). */
export const TOOLTIP_VIEWPORT_MARGIN_PX = 16;

export type TooltipAlign = "center" | "start" | "end";

export interface TooltipPlacement {
  align: TooltipAlign;
  /** Horizontal px shift applied to the centred tooltip (align "center" only). */
  shift: number;
}

/**
 * Pure placement rule (BUG-DW-180). The default tooltip is centred on the
 * trigger. If the centred box crosses the left margin, it anchors to the
 * trigger's left edge ("start") when that fits; if it crosses the right
 * margin, it anchors to the trigger's right edge ("end") when that fits.
 * Otherwise it stays centred with a pixel shift that clamps its left edge to
 * [margin, viewportWidth - margin - tipWidth]. The CSS width cap guarantees
 * tipWidth <= viewportWidth - 2 * margin, so that range is never empty.
 */
export function computeTooltipPlacement(
  triggerLeft: number,
  triggerWidth: number,
  tipWidth: number,
  viewportWidth: number,
  margin: number = TOOLTIP_VIEWPORT_MARGIN_PX,
): TooltipPlacement {
  const minLeft = margin;
  const maxLeft = Math.max(minLeft, viewportWidth - margin - tipWidth);
  const fits = (left: number) => left >= minLeft && left <= maxLeft;
  const centredLeft = triggerLeft + triggerWidth / 2 - tipWidth / 2;
  if (fits(centredLeft)) return { align: "center", shift: 0 };
  if (centredLeft < minLeft && fits(triggerLeft)) return { align: "start", shift: 0 };
  const endLeft = triggerLeft + triggerWidth - tipWidth;
  if (centredLeft > maxLeft && fits(endLeft)) return { align: "end", shift: 0 };
  const clamped = Math.min(Math.max(centredLeft, minLeft), maxLeft);
  return { align: "center", shift: Math.round(clamped - centredLeft) };
}

const ALIGN_CLASS: Record<TooltipAlign, string> = {
  center: "info-tooltip",
  start: "info-tooltip info-tooltip--align-start",
  end: "info-tooltip info-tooltip--align-end",
};

export interface InfoTooltipProps {
  /** Accessible name of the button, e.g. "About MRC Protected" */
  label: string;
  /** Verbatim definition text */
  text: string;
}

export function InfoTooltip({ label, text }: InfoTooltipProps) {
  const tipId = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const tipRef = useRef<HTMLSpanElement | null>(null);
  const [placement, setPlacement] = useState<TooltipPlacement>({ align: "center", shift: 0 });
  const open = (hovered || focused) && !dismissed;

  // BUG-DW-180: measure before paint so the tooltip never flashes off-screen.
  // The tooltip width does not depend on the alignment (max-content, capped),
  // so one measurement of the trigger rect + tooltip width is enough.
  useLayoutEffect(() => {
    if (!open) {
      setPlacement({ align: "center", shift: 0 });
      return;
    }
    const place = () => {
      const wrap = wrapRef.current;
      const tip = tipRef.current;
      if (!wrap || !tip) return;
      const t = wrap.getBoundingClientRect();
      const w = tip.getBoundingClientRect().width;
      const vw = document.documentElement.clientWidth || window.innerWidth;
      const next = computeTooltipPlacement(t.left, t.width, w, vw);
      setPlacement((prev) =>
        prev.align === next.align && prev.shift === next.shift ? prev : next,
      );
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open, text]);

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const onPointerEnter = useCallback(() => {
    cancelClose();
    setHovered(true);
  }, [cancelClose]);

  const onPointerLeave = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      setHovered(false);
    }, HOVER_CLOSE_DELAY_MS);
  }, [cancelClose]);

  // Clear any pending close timer on unmount.
  useEffect(() => cancelClose, [cancelClose]);

  // Esc dismisses even when the tooltip was opened by hover (focus may be elsewhere).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDismissed(true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // A fresh hover/focus after dismissal re-opens it.
  useEffect(() => {
    if (!hovered && !focused) setDismissed(false);
  }, [hovered, focused]);

  return (
    <span
      ref={wrapRef}
      className="info-tip"
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
    >
      <button
        type="button"
        className="info-btn"
        aria-label={label}
        aria-describedby={tipId}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      >
        <Info size={16} strokeWidth={1.5} aria-hidden={true} />
      </button>
      <span
        ref={tipRef}
        id={tipId}
        role="tooltip"
        className={ALIGN_CLASS[placement.align]}
        style={
          placement.shift !== 0
            ? ({ "--info-tooltip-shift": `${placement.shift}px` } as CSSProperties)
            : undefined
        }
        hidden={!open}
      >
        {text}
      </span>
    </span>
  );
}
