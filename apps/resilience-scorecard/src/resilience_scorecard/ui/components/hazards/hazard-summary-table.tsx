/**
 * Lakelink Fiber — Hazard Summary Table
 * HAZARD-VIS-SPEC §6.2: Sortable hazard table with pagination
 *
 * Columns: Type, Name, Severity, Location, Spans Affected, Status, Last Update
 * Default sort by severity. Uses hazard type badges (§2) and severity badges (§3).
 * Follows ServiceTable pattern with Suspense + ErrorBoundary.
 */
import { Suspense, useState, useMemo, useCallback } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Link } from "@tanstack/react-router";
import { Skeleton } from "@/components/ui/skeleton";
import { useListHazardsSuspense } from "@/lib/api";
import { HazardTypeCell } from "./hazard-type-cell";

type SortField = "severity" | "spans_affected" | "last_update";
type SortDir = "asc" | "desc";

const SEVERITY_ORDER: Record<string, number> = {
  critical: 1,
  high: 2,
  medium: 3,
  low: 4,
};

const PAGE_SIZES = [10, 25, 50] as const;

function relativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function HazardTableContent() {
  const [sortField, setSortField] = useState<SortField>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(25);

  const { data: hazards } = useListHazardsSuspense();

  const toggleSort = useCallback(
    (field: SortField) => {
      if (field === sortField) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDir("asc");
      }
      setPage(1);
    },
    [sortField],
  );

  const sorted = useMemo(() => {
    const items = [...hazards];
    const dir = sortDir === "asc" ? 1 : -1;
    items.sort((a, b) => {
      switch (sortField) {
        case "severity":
          return ((SEVERITY_ORDER[a.severity] ?? 5) - (SEVERITY_ORDER[b.severity] ?? 5)) * dir;
        case "spans_affected":
          return (a.spans_affected - b.spans_affected) * dir;
        case "last_update":
          return (new Date(a.last_update).getTime() - new Date(b.last_update).getTime()) * dir;
        default:
          return 0;
      }
    });
    return items;
  }, [hazards, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginated = sorted.slice((safePage - 1) * pageSize, safePage * pageSize);

  const sortIndicator = (field: SortField) =>
    sortField === field ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : "";

  const sortProps = (field: SortField) => ({
    onClick: () => toggleSort(field),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleSort(field);
      }
    },
    tabIndex: 0,
    "aria-sort":
      sortField === field
        ? sortDir === "asc"
          ? ("ascending" as const)
          : ("descending" as const)
        : undefined,
    role: "columnheader" as const,
  });

  if (hazards.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <p>No active hazards detected</p>
          <p className="empty-hint">The Lakelink Fiber network has no active hazard events.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="data-table">
      <table aria-label="Active hazard summary">
        <thead>
          <tr>
            <th style={{ width: 120 }}>Type</th>
            <th>Name</th>
            <th style={{ width: 100 }} {...sortProps("severity")}>
              Severity{sortIndicator("severity")}
            </th>
            <th style={{ width: 180 }}>Location</th>
            <th style={{ width: 80 }} {...sortProps("spans_affected")}>
              Spans{sortIndicator("spans_affected")}
            </th>
            <th style={{ width: 100 }}>Status</th>
            <th style={{ width: 120 }} {...sortProps("last_update")}>
              Updated{sortIndicator("last_update")}
            </th>
          </tr>
        </thead>
        <tbody>
          {paginated.map((h) => (
            <tr key={h.hazard_id}>
              <td>
                <span className={`badge ${h.hazard_type}`}>
                  <HazardTypeCell type={h.hazard_type} />
                </span>
              </td>
              <td className="text-medium">
                <Link
                  to="/topology"
                  search={{ hazard: h.hazard_id }}
                  className="cross-view-table-link"
                  aria-label={`View ${h.name} on topology map`}
                >
                  {h.name}
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="cross-view-icon">
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                    <path d="M21 14v5a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h5" />
                  </svg>
                </Link>
              </td>
              <td>
                <span className={`badge severity-${h.severity}`}>{h.severity}</span>
              </td>
              <td className="mono text-sm">{h.location}</td>
              <td>
                <span
                  className={h.spans_affected > 5 ? "text-medium" : ""}
                  style={h.spans_affected > 5 ? { color: "var(--lf-risk-red)" } : undefined}
                >
                  {h.spans_affected}
                </span>
              </td>
              <td>
                <span className={`badge ${h.is_active ? "critical" : "completed"}`}>
                  {h.is_active ? "Active" : "Expired"}
                </span>
              </td>
              <td className="text-sm">
                <time dateTime={String(h.last_update)}>
                  {relativeTime(String(h.last_update))}
                </time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <nav className="pagination-bar" aria-label="Hazard table pagination">
        <span>
          Showing {(safePage - 1) * pageSize + 1}\u2013
          {Math.min(safePage * pageSize, sorted.length)} of {sorted.length}
        </span>
        <div className="page-controls">
          <label>
            Rows:
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              aria-label="Rows per page"
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={safePage <= 1}
            aria-label="Previous page"
          >
            \u2039 Prev
          </button>
          <span>
            Page {safePage} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={safePage >= totalPages}
            aria-label="Next page"
          >
            Next \u203A
          </button>
        </div>
      </nav>
    </div>
  );
}

export function HazardSummaryTable() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="data-table error-fallback">
              <p>Failed to load hazard data</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div aria-busy="true" aria-label="Loading hazard table">
                <Skeleton className="h-96 w-full rounded-lg" />
              </div>
            }
          >
            <HazardTableContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
