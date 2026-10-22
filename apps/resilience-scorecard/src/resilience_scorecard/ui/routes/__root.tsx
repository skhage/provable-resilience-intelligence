/**
 * Lakelink Fiber — Provable Resilience Intelligence
 * Root Layout: shared header, nav, skip-nav, lang, and main content area.
 * Extracted from index.tsx + actions.tsx to eliminate duplication (UX-REM-LAYOUT-ROOT).
 */
import { useState, useEffect } from "react";
import { Link, Outlet, createRootRoute, useRouterState } from "@tanstack/react-router";
import "@/styles/lakelink-theme.css";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const [navOpen, setNavOpen] = useState(false);
  const routerState = useRouterState();
  const isActions = routerState.location.pathname === "/actions";
  const isHazards = routerState.location.pathname === "/hazards";
  const isTopology = routerState.location.pathname === "/topology";

  // Fetch data source from health endpoint
  const [dataSource, setDataSource] = useState<string>("loading");
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setDataSource(d.data_source ?? "mock"))
      .catch(() => setDataSource("mock"));
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
    };
    document.title =
      titles[routerState.location.pathname] ??
      "Provable Resilience Intelligence | Lakelink Fiber";
  }, [routerState.location.pathname]);

  // BUG-DW-029: WCAG 2.1.1 — Escape key closes hamburger nav
  useEffect(() => {
    if (!navOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [navOpen]);

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
          className={`nav-tabs${navOpen ? " open" : ""}`}
          role="navigation"
          aria-label="Main navigation"
        >
          <Link
            to="/"
            activeOptions={{ exact: true }}
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => setNavOpen(false)}
          >
            Scorecard
          </Link>
          <Link
            to="/actions"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => setNavOpen(false)}
          >
            Action Queue
          </Link>
          <Link
            to="/hazards"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => setNavOpen(false)}
          >
            Hazard Exposure
          </Link>
          <Link
            to="/topology"
            activeProps={{ className: "active", "aria-current": "page" as const }}
            onClick={() => setNavOpen(false)}
          >
            Network Topology
          </Link>
        </nav>
        <div className="ml-auto">
          <span className={`data-source-badge ${dataSource === "live" ? "live" : "mock"}`} role="status">
            <span className="dot" aria-hidden="true" />
            {dataSource === "live"
              ? (isActions ? "Lakebase State" : isHazards ? "Live Crosswalk" : isTopology ? "Live Topology" : "Live Data")
              : "Mock Data"}
          </span>
        </div>
      </header>

      {/* Page Content (UX-DESIGN-SPEC §4.2) */}
      <main id="main-content" className="page-content" role="main">
        <Outlet />
      </main>
    </>
  );
}
