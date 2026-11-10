/**
 * Lakelink Fiber — Provable Resilience Intelligence
 * Root Layout: shared header, nav, skip-nav, lang, and main content area.
 * Extracted from index.tsx + actions.tsx to eliminate duplication (UX-REM-LAYOUT-ROOT).
 */
import { useState, useEffect, useRef } from "react";
import { Link, Outlet, createRootRoute, useRouterState } from "@tanstack/react-router";
import {
  focusMainContent,
  navEscapeShouldRestoreFocus,
  navLinkClickShouldFocusMain,
  shouldFocusMainOnRouteChange,
} from "@/lib/root-focus";
import {
  dataSourceBadgeClass,
  dataSourceBadgeLabel,
  dataSourceFromHealth,
  type DataSourceState,
} from "@/lib/data-source-badge";
import "@/styles/lakelink-theme.css";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const [navOpen, setNavOpen] = useState(false);
  const routerState = useRouterState();
  const pathname = routerState.location.pathname;
  // BUG-DW-160: refs for focus return on Escape and focus move on route change
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const prevPathRef = useRef<string | null>(null);

  // Fetch data source from health endpoint.
  // BUG-DW-161: "loading" renders a neutral "Checking data source" badge, and a failed
  // check renders "Data source unavailable". "Mock Data" only when health says mock.
  const [dataSource, setDataSource] = useState<DataSourceState>("loading");
  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => {
        if (!r.ok) throw new Error(`health ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (!cancelled) setDataSource(dataSourceFromHealth(d?.data_source));
      })
      .catch(() => {
        if (!cancelled) setDataSource("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = "en";
  }, []);

  // BUG-DW-028: WCAG 2.4.2 — descriptive page title per route
  useEffect(() => {
    const titles: Record<string, string> = {
      "/": "Resilience Scorecard | Lakelink Fiber",
      "/actions": "Action Queue | Lakelink Fiber",
      "/hazards": "Hazard Exposure | Lakelink Fiber",
      "/topology": "Network Topology | Lakelink Fiber",
      "/conduits": "Conduit Coverage | Lakelink Fiber",
    };
    document.title =
      titles[routerState.location.pathname] ??
      "Provable Resilience Intelligence | Lakelink Fiber";
  }, [routerState.location.pathname]);

  // BUG-DW-160: WCAG 2.4.3 — after a client-side route change, move focus to #main-content.
  // Skipped on first render (prev is null) and when only the query string changes.
  useEffect(() => {
    const prev = prevPathRef.current;
    prevPathRef.current = pathname;
    if (!shouldFocusMainOnRouteChange(prev, pathname)) return;
    const frame = requestAnimationFrame(() => focusMainContent(document));
    return () => cancelAnimationFrame(frame);
  }, [pathname]);

  // BUG-DW-029: WCAG 2.1.1 — Escape key closes hamburger nav
  // BUG-DW-160: WCAG 2.4.3 — return focus to the hamburger if it was in the nav or on it
  useEffect(() => {
    if (!navOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        const restore = navEscapeShouldRestoreFocus(
          document.activeElement,
          navRef.current,
          hamburgerRef.current,
        );
        setNavOpen(false);
        if (restore) hamburgerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [navOpen]);

  // BUG-DW-160: closing the nav hides the clicked link. A different route moves focus via
  // the pathname effect; the current route does not, so focus #main-content here.
  const onNavLinkClick = (to: string) => {
    const focusMain = navOpen && navLinkClickShouldFocusMain(to, pathname);
    setNavOpen(false);
    if (focusMain) requestAnimationFrame(() => focusMainContent(document));
  };

  return (
    <>
      {/* Skip-nav link (UX-REM-A11Y-LANDMARKS §6, WCAG 2.4.1) */}
      <a href="#main-content" className="skip-nav">Skip to main content</a>

      {/* App Header (UX-DESIGN-SPEC §2.2, §4.2, UX-REM-RESPONSIVE) */}
      <header className="app-header" role="banner">
        <h1>
          <span className="brand-accent">Lakelink Fiber</span> &mdash; Provable
          Resilience Intelligence
        </h1>
        <button
          ref={hamburgerRef}
          className="nav-hamburger"
          onClick={() => setNavOpen((o) => !o)}
          aria-expanded={navOpen}
          aria-controls="main-nav"
          aria-label={navOpen ? "Close navigation menu" : "Open navigation menu"}
        >
          {navOpen ? "\u2715" : "\u2630"}
        </button>
        <nav
          id="main-nav"
          ref={navRef}
          className={`nav-tabs${navOpen ? " open" : ""}`}
          role="navigation"
          aria-label="Main navigation"
        >
          <Link
            to="/"
            activeOptions={{ exact: true }}
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => onNavLinkClick("/")}
          >
            Scorecard
          </Link>
          <Link
            to="/actions"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => onNavLinkClick("/actions")}
          >
            Action Queue
          </Link>
          <Link
            to="/hazards"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => onNavLinkClick("/hazards")}
          >
            Hazard Exposure
          </Link>
          <Link
            to="/topology"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => onNavLinkClick("/topology")}
          >
            Network Topology
          </Link>
          <Link
            to="/conduits"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => onNavLinkClick("/conduits")}
          >
            Conduit Coverage
          </Link>
        </nav>
        <div className="ml-auto">
          <span className={dataSourceBadgeClass(dataSource)} role="status">
            <span className="dot" aria-hidden="true" />
            {dataSourceBadgeLabel(dataSource, pathname)}
          </span>
        </div>
      </header>

      {/* Page Content (UX-DESIGN-SPEC §4.2) */}
      {/* BUG-DW-149 (WCAG 2.4.1): tabIndex -1 so the skip link moves focus in Safari/WebKit */}
      <main id="main-content" className="page-content" role="main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}
