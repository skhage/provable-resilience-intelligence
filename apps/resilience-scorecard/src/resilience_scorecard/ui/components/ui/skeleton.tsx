/**
 * Loading placeholder (shadcn-compatible API). Decorative only, so it is hidden
 * from assistive tech. Skeleton announces nothing by itself: wrap it in
 * <LoadingRegion label="..."> (components/ui/loading-region.tsx), which renders
 * role="status" with sr-only text (BUG-DW-078).
 * Styling: the single .skeleton-loading class in lakelink-theme.css (BUG-DW-079).
 * It has a white resting fill and a --lf-platinum-shade border, so it stays
 * visible on platinum when prefers-reduced-motion stops the pulse.
 */
import type { HTMLAttributes } from "react";

export function Skeleton({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={`skeleton-loading ${className}`.trim()} {...props} />;
}

export default Skeleton;
