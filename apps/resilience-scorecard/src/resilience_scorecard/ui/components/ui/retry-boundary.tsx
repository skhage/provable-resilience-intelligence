/**
 * BUG-DW-178 (WCAG 2.4.3 Focus Order, 3.2.1 Predictable): shared Suspense + error boundary
 * with Retry focus management. Replaces the bare `onClick={resetErrorBoundary}` Retry buttons that
 * dropped keyboard/screen-reader focus to <body> when the fallback unmounted.
 *
 * Behaviour:
 *  - The boundary output is wrapped in <div tabIndex={-1} className="retry-focus-target">.
 *  - Pressing Retry sets retryPendingRef = true, then resets the boundary.
 *  - If it errors again while pending, the NEW Retry button takes focus on mount.
 *  - If children render successfully while pending, the container takes focus (requestAnimationFrame),
 *    so the next Tab reaches the first control inside it.
 *  - Focus is never moved on the first error, on initial load, or on a resetKeys-driven reset
 *    (e.g. a /conduits filter change): only after a user-initiated Retry.
 *  - No new live regions: callers keep their existing role (alert or none per BUG-DW-128/170).
 *
 * Generalises the BUG-DW-105 /topology path-trace fix. Lakelink Fiber tokens only.
 */
import { Suspense, useEffect, useRef, type MutableRefObject, type ReactNode, type RefObject } from "react";
import { ErrorBoundary } from "react-error-boundary";

type RetryBoundaryProps = {
  /** Usually the QueryErrorResetBoundary `reset`, plus any caller side effect (e.g. announceLoading). */
  onReset?: () => void;
  /** Changing keys resets the boundary without moving focus (BUG-DW-095). */
  resetKeys?: unknown[];
  onError?: () => void;
  /** Suspense fallback (LoadingRegion + skeletons). */
  loading: ReactNode;
  /** Renders the error fallback. Place `retryButton` where the old Retry button was. */
  fallback: (retryButton: ReactNode) => ReactNode;
  children: ReactNode;
};

export function RetryBoundary({ onReset, resetKeys, onError, loading, fallback, children }: RetryBoundaryProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const retryPendingRef = useRef(false);

  return (
    <div ref={containerRef} tabIndex={-1} className="retry-focus-target">
      <ErrorBoundary
        resetKeys={resetKeys}
        onError={onError ? () => onError() : undefined}
        onReset={(details) => {
          // A resetKeys change is not a user Retry: never steal focus for it.
          if (details.reason === "keys") retryPendingRef.current = false;
          onReset?.();
        }}
        fallbackRender={({ resetErrorBoundary }) =>
          fallback(<RetryButton retryPendingRef={retryPendingRef} onRetry={resetErrorBoundary} />)
        }
      >
        <Suspense fallback={loading}>
          <RetryFocusProbe retryPendingRef={retryPendingRef} containerRef={containerRef} />
          {children}
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}

/** Retry button: focuses itself on mount only when it replaces a fallback after a user Retry. */
function RetryButton({
  retryPendingRef,
  onRetry,
}: {
  retryPendingRef: MutableRefObject<boolean>;
  onRetry: () => void;
}) {
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (retryPendingRef.current) {
      retryPendingRef.current = false;
      buttonRef.current?.focus();
    }
  }, [retryPendingRef]);

  return (
    <button
      ref={buttonRef}
      type="button"
      className="btn btn-outline"
      onClick={() => {
        retryPendingRef.current = true;
        onRetry();
      }}
    >
      Retry
    </button>
  );
}

/**
 * Mounts inside Suspense, so its effect runs only once the content has resolved without error.
 * The flag is cleared inside the frame callback so a StrictMode double-effect still focuses once.
 */
function RetryFocusProbe({
  retryPendingRef,
  containerRef,
}: {
  retryPendingRef: MutableRefObject<boolean>;
  containerRef: RefObject<HTMLDivElement>;
}) {
  useEffect(() => {
    if (!retryPendingRef.current) return;
    const frame = requestAnimationFrame(() => {
      retryPendingRef.current = false;
      containerRef.current?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [retryPendingRef, containerRef]);
  return null;
}
