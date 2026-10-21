/**
 * Lakelink Fiber — Hazard KPI Row
 * HAZARD-VIS-SPEC §6.1: 4 KPI cards below existing resilience KPIs
 *
 * Cards: Active Hazards, Spans at Risk, Services Impacted, Revenue Exposed
 * Conditional render: only shown if hazard data is available.
 * Pattern: mirrors ScorecardHeader with Suspense + ErrorBoundary.
 */
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { useGetHazardSummarySuspense } from "@/lib/api";

function HazardKpiContent() {
  const { data: summary } = useGetHazardSummarySuspense();

  // Conditional render: if no active hazards, don't show the row
  if (summary.active_hazards === 0) {
    return null;
  }

  return (
    <div className="kpi-row">
      <div
        className={`kpi-card ${summary.active_hazards > 0 ? "critical" : ""}`}
        role="group"
        aria-label={`Active Hazards: ${summary.active_hazards.toLocaleString()}`}
      >
        <div className="kpi-label">Active Hazards</div>
        <div className="kpi-value">{summary.active_hazards.toLocaleString()}</div>
      </div>

      <div
        className="kpi-card high"
        role="group"
        aria-label={`Spans at Risk: ${summary.spans_at_risk.toLocaleString()}`}
      >
        <div className="kpi-label">Spans at Risk</div>
        <div className="kpi-value">{summary.spans_at_risk.toLocaleString()}</div>
      </div>

      <div
        className="kpi-card warning"
        role="group"
        aria-label={`Services Impacted: ${summary.services_impacted.toLocaleString()}`}
      >
        <div className="kpi-label">Services Impacted</div>
        <div className="kpi-value">{summary.services_impacted.toLocaleString()}</div>
      </div>

      <div
        className="kpi-card critical"
        role="group"
        aria-label={`Revenue Exposed: $${(summary.revenue_exposed_usd / 1_000_000).toFixed(1)}M`}
      >
        <div className="kpi-label">Revenue Exposed</div>
        <div className="kpi-value">
          ${(summary.revenue_exposed_usd / 1_000_000).toFixed(1)}M
        </div>
      </div>
    </div>
  );
}

export function HazardKpiRow() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="kpi-row">
              <div className="kpi-card">
                <p>Failed to load hazard summary</p>
                <button className="btn btn-outline" onClick={resetErrorBoundary}>
                  Retry
                </button>
              </div>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div className="kpi-row" aria-busy="true" aria-label="Loading hazard summary">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-lg" />
                ))}
              </div>
            }
          >
            <HazardKpiContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
