/**
 * Announced loading region for Suspense fallbacks (BUG-DW-078, WCAG 4.1.3 Status Messages).
 * role="status" is a polite live region, so screen readers announce the sr-only label.
 * Skeleton children stay aria-hidden; this wrapper carries the accessible text.
 * Do not put aria-label on a role-less div: ARIA 1.2 prohibits it and AT ignores it.
 */
import type { ReactNode } from "react";

type LoadingRegionProps = {
  /** Visible-to-AT text, e.g. "Loading KPI summary". An ellipsis is appended. */
  label: string;
  /** Optional layout class (e.g. "kpi-row") applied to the region itself. */
  className?: string;
  children?: ReactNode;
};

export function LoadingRegion({ label, className, children }: LoadingRegionProps) {
  return (
    <div role="status" aria-busy="true" className={className}>
      {/* sr-only is position:absolute, so it takes no grid cell when className="kpi-row" */}
      <span className="sr-only">{`${label}\u2026`}</span>
      {children}
    </div>
  );
}

export default LoadingRegion;
