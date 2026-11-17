/**
 * Lakelink Fiber - RetryBoundary focus decisions (BUG-DW-178, BUG-QA-171; WCAG 2.4.3, 3.2.1).
 * Pure functions, no React import, so the behaviour can be exercised with Node in tests.
 *
 * The pending flag is a React ref ({ current: boolean }). It is set only by a user Retry
 * click and consumed exactly once: by the next Retry button that mounts (repeat failure)
 * or by the success probe (content resolved). A resetKeys reset clears it.
 *
 * BUG-QA-171 late-resolve guard: if the user has moved focus somewhere outside the boundary
 * while the retried content was still loading, focus is left where the user put it.
 */

export type PendingFlag = { current: boolean };
export type Focusable = { focus(): void };
export type FocusContainer = Focusable & { contains(other: unknown): boolean };
export type ActiveDoc = { activeElement: unknown; body: unknown };

/** User pressed Retry: the next mount (button or resolved content) may take focus. */
export function markRetryPending(flag: PendingFlag): void {
  flag.current = true;
}

/** react-error-boundary onReset. A resetKeys change ("keys") is not a user Retry. */
export function handleBoundaryReset(flag: PendingFlag, reason: string | undefined): void {
  if (reason === "keys") flag.current = false;
}

/**
 * True when focus is on a real element outside the boundary container, i.e. the user moved
 * on while the retry was in flight. Focus on <body> (the old Retry button unmounted), on the
 * container, or inside it is not "moved away".
 */
export function userMovedFocusAway(
  doc: ActiveDoc | null | undefined,
  container: FocusContainer | null | undefined,
): boolean {
  const active = doc?.activeElement;
  if (!active || active === doc?.body) return false;
  if (!container) return true;
  return active !== container && !container.contains(active);
}

/** Success probe effect: schedule a focus frame only after a user Retry. */
export function shouldScheduleRetryFocus(flag: PendingFlag): boolean {
  return flag.current;
}

function consume(
  flag: PendingFlag,
  target: Focusable | null | undefined,
  container: FocusContainer | null | undefined,
  doc: ActiveDoc | null | undefined,
): boolean {
  if (!flag.current) return false;
  flag.current = false;
  if (!target || userMovedFocusAway(doc, container)) return false;
  target.focus();
  return true;
}

/** Repeat failure: the new Retry button takes focus (once) after a user Retry. */
export function focusRetryButtonIfPending(
  flag: PendingFlag,
  button: Focusable | null | undefined,
  container: FocusContainer | null | undefined,
  doc: ActiveDoc | null | undefined,
): boolean {
  return consume(flag, button, container, doc);
}

/** Success: the boundary container takes focus (once, in the scheduled frame) after a user Retry. */
export function focusContainerAfterRetry(
  flag: PendingFlag,
  container: FocusContainer | null | undefined,
  doc: ActiveDoc | null | undefined,
): boolean {
  return consume(flag, container, container, doc);
}
