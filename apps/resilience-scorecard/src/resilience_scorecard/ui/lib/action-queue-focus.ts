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
  const count = n.toLocaleString("en-US");
  const label = word ? `${count} ${word} ${noun}` : `${count} ${noun}`;
  return `${label} · showing ${w.first}–${w.last}`;
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
