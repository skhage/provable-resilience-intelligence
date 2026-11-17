/**
 * Lakelink Fiber — Hazard KPI Row
 * HAZARD-VIS-SPEC §6.1: 4 KPI cards below existing resilience KPIs
 *
 * Cards: Active Hazards, Spans at Risk, Services Impacted, Revenue Exposed
 * Conditional render: only shown if hazard data is available.
 * Pattern: mirrors ScorecardHeader with Suspense + ErrorBoundary.
 */
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { RetryBoundary } from "@/components/ui/retry-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { useGetHazardSummarySuspense } from "@/lib/api";
// BUG-DW-192: §6.4 counts pinned to en-US (no browser-locale drift; aria-label == visible).
import { formatCount } from "@/lib/bb-srlg-disclosure";

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
        aria-label={`Active Hazards: ${formatCount(summary.active_hazards)}`}
      >
        <div className="kpi-label">Active Hazards</div>
        <div className="kpi-value">{formatCount(summary.active_hazards)}</div>
      </div>

      <div
        className="kpi-card high"
        role="group"
        aria-label={`Spans at Risk: ${formatCount(summary.spans_at_risk)}`}
      >
        <div className="kpi-label">Spans at Risk</div>
        <div className="kpi-value">{formatCount(summary.spans_at_risk)}</div>
      </div>

      <div
        className="kpi-card warning"
        role="group"
        aria-label={`Services Impacted: ${formatCount(summary.services_impacted)}`}
      >
        <div className="kpi-label">Services Impacted</div>
        <div className="kpi-value">{formatCount(summary.services_impacted)}</div>
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
        <RetryBoundary
          onReset={reset}
          fallback={(retryButton) => (
            <div className="kpi-row" role="alert">
              <div className="kpi-card">
                <p>Failed to load hazard summary</p>
                {retryButton}
              </div>
            </div>
          )}
          loading={
            <LoadingRegion className="kpi-row" label="Loading hazard summary">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))}
            </LoadingRegion>
          }
        >
          <HazardKpiContent />
        </RetryBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
