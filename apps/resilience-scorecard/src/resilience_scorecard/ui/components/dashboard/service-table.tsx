/**
 * Lakelink Fiber — Service Resilience Table
 * Sortable table showing per-service resilience scores with inline gauges.
 */
import { Suspense, useState } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Link } from "@tanstack/react-router";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { useBbSrlgCoverage, useListResilienceScoresSuspense } from "@/lib/api";
import { METRO_ACCESS, METRO_ACCESS_SPOKEN } from "@/lib/bb-srlg-disclosure";
import { snapshotGradeLabel } from "@/lib/diversity-copy";
import selector from "@/lib/selector";

function gaugeClass(score: number): string {
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 55) return "fair";
  if (score >= 40) return "poor";
  return "failing";
}

function ScoreGauge({ score, label }: { score: number; label?: string }) {
  return (
    <span className="score-gauge"
          role="meter"
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label ? `${label}: ${score.toFixed(1)} out of 100` : `${score.toFixed(1)} out of 100`}>
      <span className="score-value">{score.toFixed(1)}</span>
      <span className="gauge-bar" aria-hidden="true">
        <span
          className={`gauge-fill ${gaugeClass(score)}`}
          style={{ width: `${score}%` }}
        />
      </span>
    </span>
  );
}

const PAGE_SIZES = [10, 25, 50, 100] as const;

function ServiceTableContent() {
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(25);
  // P41-APP-V4-INTERIM-BADGE §6.3: null when PRI_V4_KPIS is off, so the v3 header is unchanged.
  const bbCoverage = useBbSrlgCoverage();
  const { data: scores } = useListResilienceScoresSuspense({
    params: { sort_by: "resilience_score", sort_dir: sortDir },
    ...selector(),
  });

  const toggleSort = () => setSortDir((d) => (d === "asc" ? "desc" : "asc"));
  const totalPages = Math.max(1, Math.ceil(scores.length / pageSize));
  const safeCurrentPage = Math.min(page, totalPages);
  const paginatedScores = scores.slice(
    (safeCurrentPage - 1) * pageSize,
    safeCurrentPage * pageSize,
  );

  if (scores.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <div className="empty-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg></div>
          <p>No services found</p>
          <p className="empty-hint">Service data has not been loaded yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="data-table">
      <table aria-label="Service resilience scores">
        <thead>
          <tr>
            <th>Service</th>
            <th>Customer</th>
            <th onClick={toggleSort}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleSort();
                  }
                }}
                tabIndex={0}
                aria-sort={sortDir === "asc" ? "ascending" : "descending"}
                role="columnheader">
              Resilience {sortDir === "asc" ? "▲" : "▼"}
            </th>
            <th>Physical</th>
            <th>Network</th>
            <th>Environ.</th>
            <th>Path Div.</th>
            <th>SPFs</th>
            <th>
              SRLGs
              {bbCoverage === "partial" && (
                <>
                  <span aria-hidden="true">{`\u00A0${METRO_ACCESS}`}</span>
                  <span className="sr-only">{` ${METRO_ACCESS_SPOKEN}`}</span>
                </>
              )}
            </th>
          </tr>
        </thead>
        <tbody>
          {paginatedScores.map((s) => (
            <tr key={s.service_id}>
              <td className="text-medium">
                <Link
                  to="/topology"
                  search={{ service: s.service_id }}
                  className="cross-view-table-link"
                  aria-label={`View ${s.service_name} on topology map`}
                >
                  {s.service_name}
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="cross-view-icon">
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                    <path d="M21 14v5a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h5" />
                  </svg>
                </Link>
              </td>
              <td>{s.customer_name}</td>
              <td>
                <ScoreGauge score={s.resilience_score} label="Resilience score" />
              </td>
              <td>
                <ScoreGauge score={s.physical_redundancy_score} label="Physical redundancy" />
              </td>
              <td>
                <ScoreGauge score={s.network_health_score} label="Network health" />
              </td>
              <td>
                <ScoreGauge score={s.environmental_risk_score} label="Environmental risk" />
              </td>
              <td>
                <span
                  className={`rating-pill ${s.path_diversity_rating}`}
                  // BUG-DW-099: name the basis (scored snapshot) so it is not read as the /topology derived badge
                  aria-label={snapshotGradeLabel(s.path_diversity_rating)}
                  title={snapshotGradeLabel(s.path_diversity_rating)}
                >
                  {s.path_diversity_rating}
                </span>
              </td>
              <td>{s.single_point_failures}</td>
              <td>{s.srlg_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination controls (UX-REM-TABLE-UX) */}
      <nav className="pagination-bar" aria-label="Service table pagination">
        <span>
          Showing {(safeCurrentPage - 1) * pageSize + 1}–
          {Math.min(safeCurrentPage * pageSize, scores.length)} of {scores.length}
        </span>
        <div className="page-controls">
          <label>
            Rows:
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              aria-label="Rows per page"
            >
              {PAGE_SIZES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={safeCurrentPage <= 1}
            aria-label="Previous page"
          >
            ‹ Prev
          </button>
          <span>Page {safeCurrentPage} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={safeCurrentPage >= totalPages}
            aria-label="Next page"
          >
            Next ›
          </button>
        </div>
      </nav>
    </div>
  );
}

export function ServiceTable() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="data-table error-fallback">
              <p>Failed to load service scores</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <LoadingRegion label="Loading service table">
                <Skeleton className="h-96 w-full rounded-lg" />
              </LoadingRegion>
            }
          >
            <ServiceTableContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
