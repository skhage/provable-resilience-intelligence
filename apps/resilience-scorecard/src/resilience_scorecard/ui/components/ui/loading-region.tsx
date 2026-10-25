/**
 * Announced loading region for Suspense fallbacks (BUG-DW-078, BUG-DW-084, WCAG 4.1.3 Status Messages).
 * role="status" is a polite live region, so screen readers announce the sr-only label.
 * Skeleton children stay aria-hidden; this wrapper carries the accessible text.
 * Do not put aria-label on a role-less div: ARIA 1.2 prohibits it and AT ignores it.
 *
 * BUG-DW-084: no aria-busy here. A Suspense fallback unmounts instead of clearing busy, so
 * aria-busy="true" would suppress the announcement forever. The region also mounts EMPTY and
 * the label is injected after ANNOUNCE_DELAY_MS, because a live region that appears with its
 * content already present is often not announced (same root cause as BUG-DW-074).
 * If aria-busy is wanted, put it on the persistent parent card/section, never on this region.
 */
import { useEffect, useState, type ReactNode } from "react";

/** Delay before injecting the label so AT registers the empty live region first. */
const ANNOUNCE_DELAY_MS = 100;

type LoadingRegionProps = {
  /** Visible-to-AT text, e.g. "Loading KPI summary". An ellipsis is appended. */
  label: string;
  /** Optional layout class (e.g. "kpi-row") applied to the region itself. */
  className?: string;
  children?: ReactNode;
};

export function LoadingRegion({ label, className, children }: LoadingRegionProps) {
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    // Start empty, then set text on a later tick so the change is announced once per fallback.
    setAnnouncement("");
    const timer = setTimeout(() => setAnnouncement(`${label}\u2026`), ANNOUNCE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [label]);

  return (
    <div role="status" aria-live="polite" aria-atomic="true" className={className}>
      {/* sr-only is position:absolute, so it takes no grid cell when className="kpi-row" */}
      <span className="sr-only">{announcement}</span>
      {children}
    </div>
  );
}

export default LoadingRegion;
