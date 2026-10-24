/**
 * Loading placeholder (shadcn-compatible API). Decorative only: hidden from
 * assistive tech; the surrounding Suspense region announces loading state.
 * Animation is disabled under prefers-reduced-motion (see styles/scaffold.css).
 */
import type { HTMLAttributes } from "react";

export function Skeleton({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={`skeleton ${className}`.trim()} {...props} />;
}

export default Skeleton;
