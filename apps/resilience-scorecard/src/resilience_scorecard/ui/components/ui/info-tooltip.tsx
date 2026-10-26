/**
 * Lakelink Fiber — InfoTooltip (V4-KPI-COPY-SPEC §1 Info control, §4 tooltip rules)
 *
 * Lucide Info 16px / 1.5px stroke inside a 24x24 button (WCAG 2.5.8 target size).
 * Tooltip (WCAG 1.4.13): opens on hover AND keyboard focus, dismisses on Esc,
 * stays open while the pointer is over the button or the tooltip, and opens
 * above the trigger so it never covers the KPI value below the label.
 * The tooltip text is always wired via aria-describedby, so screen readers get
 * the definition even while it is visually hidden.
 */
import { useEffect, useId, useState } from "react";
import { Info } from "lucide-react";

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
  const open = (hovered || focused) && !dismissed;

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
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
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
