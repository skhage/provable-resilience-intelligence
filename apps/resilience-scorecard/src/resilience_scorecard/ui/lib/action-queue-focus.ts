/**
 * Lakelink Fiber - Action Queue focus + result-count helpers (BUG-DW-102).
 * Pure functions, no React import, so they can be evaluated with Node in tests.
 */

export type StatusFilter = string | undefined;

export interface PageWindow {
  totalPages: number;
  page: number;
  /** 1-based index of the first visible row; 0 when the list is empty. */
  first: number;
  /** 1-based index of the last visible row; 0 when the list is empty. */
  last: number;
}

/** Clamp the requested page to the available range and return the visible window. */
export function pageWindow(total: number, page: number, pageSize: number): PageWindow {
  const size = Math.max(1, Math.floor(pageSize) || 1);
  const n = Math.max(0, Math.floor(total) || 0);
  const totalPages = Math.max(1, Math.ceil(n / size));
  const p = Math.min(Math.max(1, Math.floor(page) || 1), totalPages);
  if (n === 0) return { totalPages, page: p, first: 0, last: 0 };
  return { totalPages, page: p, first: (p - 1) * size + 1, last: Math.min(p * size, n) };
}

const FILTER_WORDS: Record<string, string> = {
  pending: "pending",
  in_progress: "in progress",
  completed: "completed",
  cancelled: "cancelled",
};

/**
 * Sentence-case result line for the persistent role=status region.
 * Examples: "42 actions · showing 1–25", "1 pending action · showing 1–1",
 * "No in progress actions".
 */
export function queueResultMessage(
  total: number,
  page: number,
  pageSize: number,
  filter: StatusFilter,
): string {
  const word = filter && Object.prototype.hasOwnProperty.call(FILTER_WORDS, filter)
    ? FILTER_WORDS[filter]
    : "";
  const w = pageWindow(total, page, pageSize);
  const n = Math.max(0, Math.floor(total) || 0);
  if (n === 0) {
    return word ? `No ${word} actions` : "No actions";
  }
  const noun = n === 1 ? "action" : "actions";
  const count = fmtCount(n);
  const label = word ? `${count} ${word} ${noun}` : `${count} ${noun}`;
  return `${label} · showing ${formatRange(w.first, w.last)}`;
}

/** BUG-DW-109 item 3: grouped en-US integer (1234 -> "1,234"). */
export function fmtCount(n: number): string {
  return Math.max(0, Math.floor(n) || 0).toLocaleString("en-US");
}

/** BUG-DW-109 item 3: "1,226–1,234" (en dash), both ends grouped. */
export function formatRange(first: number, last: number): string {
  return `${fmtCount(first)}–${fmtCount(last)}`;
}

/**
 * BUG-DW-109 item 3: visible pagination text, e.g. "Showing 1,226–1,234 of 1,234".
 * Uses the clamped pageWindow so it always matches the rendered rows and the SR line.
 */
export function paginationSummary(total: number, page: number, pageSize: number): string {
  const w = pageWindow(total, page, pageSize);
  return `Showing ${formatRange(w.first, w.last)} of ${fmtCount(total)}`;
}

/** BUG-DW-109 item 1: pagination boundary flags (aria-disabled, never native disabled). */
export function pageBoundary(page: number, totalPages: number): { atFirst: boolean; atLast: boolean } {
  return { atFirst: page <= 1, atLast: page >= totalPages };
}

/** BUG-DW-109 item 4: immutable add to the in-flight action-id set. */
export function withInFlight(set: ReadonlySet<string>, actionId: string): Set<string> {
  const next = new Set(set);
  next.add(actionId);
  return next;
}

/** BUG-DW-109 item 4: immutable remove; returns the same set when the id is absent. */
export function withoutInFlight(set: ReadonlySet<string>, actionId: string): ReadonlySet<string> {
  if (!set.has(actionId)) return set;
  const next = new Set(set);
  next.delete(actionId);
  return next;
}

export interface FocusContext {
  actionId: string;
  following: string[];
}

/**
 * BUG-DW-109 item 4: when the PATCH for `settledId` succeeds, return the focus request to
 * apply, or null. Focus moves only for the most recent user-initiated action; an earlier
 * row that finishes after the user has moved on never steals focus.
 */
export function focusRequestFor(
  settledId: string,
  latestClickId: string | null,
  contexts: ReadonlyMap<string, FocusContext>,
): FocusContext | null {
  if (latestClickId !== settledId) return null;
  return contexts.get(settledId) ?? { actionId: settledId, following: [] };
}

/** Stable key for "which view is the user looking at"; announce only when it changes. */
export function viewKey(filter: StatusFilter, page: number, pageSize: number): string {
  return `${filter ?? "all"}|${page}|${pageSize}`;
}

/**
 * After a status change, choose where keyboard focus goes:
 * (a) the same row's (new) action button if the row is still visible,
 * (b) else the first following row (in the pre-change order) that has a button,
 * (c) else null, meaning the caller focuses the table container (tabIndex=-1).
 */
export function pickFocusTarget(
  actionId: string,
  followingIds: readonly string[],
  hasButton: (id: string) => boolean,
): string | null {
  if (hasButton(actionId)) return actionId;
  for (const id of followingIds) {
    if (id !== actionId && hasButton(id)) return id;
  }
  return null;
}

/** Ids of the rows visible after `actionId` at click time (empty if not found). */
export function idsAfter(visibleIds: readonly string[], actionId: string): string[] {
  const i = visibleIds.indexOf(actionId);
  return i < 0 ? [] : visibleIds.slice(i + 1);
}
