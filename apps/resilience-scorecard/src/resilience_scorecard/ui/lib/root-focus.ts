/**
 * Lakelink Fiber - root layout focus helpers (BUG-DW-160, WCAG 2.4.3 Focus Order).
 * Pure functions, no React import, so they can be evaluated with Node in tests.
 */

/** Id of the <main> landmark. It has tabIndex=-1 (BUG-DW-149), so it can take focus. */
export const MAIN_CONTENT_ID = "main-content";

interface ContainsNode {
  contains(other: unknown): boolean;
}

/**
 * Escape closes the hamburger nav. Focus goes back to the hamburger button only when it
 * was inside the nav or on the button itself. Focus anywhere else is left alone.
 */
export function navEscapeShouldRestoreFocus(
  active: unknown,
  nav: ContainsNode | null | undefined,
  hamburger: unknown,
): boolean {
  if (!active) return false;
  if (hamburger && active === hamburger) return true;
  return !!nav && nav.contains(active);
}

/**
 * Move focus to <main> after a client-side route change. Not on the first render
 * (prev === null), and not when only the query string changed (same pathname).
 */
export function shouldFocusMainOnRouteChange(prev: string | null, next: string): boolean {
  return prev !== null && prev !== next;
}

/**
 * A nav link for the page you are already on does not change the pathname. Closing the
 * nav would then hide the focused link and drop focus to <body>, so focus <main> instead.
 */
export function navLinkClickShouldFocusMain(to: string, pathname: string): boolean {
  return to === pathname;
}

interface FocusDoc {
  getElementById(id: string): { focus(): void } | null;
}

/** Focus the <main> landmark. Returns false when it is not in the document. */
export function focusMainContent(doc: FocusDoc): boolean {
  const el = doc.getElementById(MAIN_CONTENT_ID);
  if (!el) return false;
  el.focus();
  return true;
}
