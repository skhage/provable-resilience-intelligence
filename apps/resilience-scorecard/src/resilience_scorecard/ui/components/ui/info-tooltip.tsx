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
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Info } from "lucide-react";

/** Grace period before a hover-opened tooltip closes (BUG-DW-092). */
const HOVER_CLOSE_DELAY_MS = 150;

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
  const open = (hovered || focused) && !dismissed;

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
      <span id={tipId} role="tooltip" className="info-tooltip" hidden={!open}>
        {text}
      </span>
    </span>
  );
}
