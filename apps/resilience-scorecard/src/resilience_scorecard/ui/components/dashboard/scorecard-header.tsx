/**
 * Lakelink Fiber — Resilience Scorecard Dashboard Header
 * Displays aggregate KPIs: avg score, risk counts, SPFs, SRLGs
 */
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { useGetResilienceSummarySuspense, useV4Kpis } from "@/lib/api";
import selector from "@/lib/selector";

function scoreClass(score: number): string {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  if (score >= 40) return "high";
  return "critical";
}

function ScorecardHeaderContent() {
  const { data: summary } = useGetResilienceSummarySuspense(selector());
  // V4-KPI-COPY-SPEC §1 unit consistency: Revenue at Risk is monthly, shown as /mo under the flag.
  const v4Kpis = useV4Kpis();

  return (
    <div className="kpi-row">
      <div className={`kpi-card ${scoreClass(summary.avg_resilience_score)}`}
           role="group" aria-label={`Avg Resilience Score: ${summary.avg_resilience_score.toFixed(1)}`}>
        <div className="kpi-label">Avg Resilience Score</div>
        <div className="kpi-value score">{summary.avg_resilience_score.toFixed(1)}</div>
      </div>
      <div className="kpi-card critical"
           role="group" aria-label={`Critical Risk: ${summary.critical_count}`}>
        <div className="kpi-label">Critical Risk</div>
        <div className="kpi-value">{summary.critical_count}</div>
      </div>
      <div className="kpi-card high"
           role="group" aria-label={`High Risk: ${summary.high_risk_count}`}>
        <div className="kpi-label">High Risk</div>
        <div className="kpi-value">{summary.high_risk_count}</div>
      </div>
      <div className="kpi-card warning"
           role="group" aria-label={`Medium Risk: ${summary.medium_risk_count}`}>
        <div className="kpi-label">Medium Risk</div>
        <div className="kpi-value">{summary.medium_risk_count}</div>
      </div>
      <div className="kpi-card success"
           role="group" aria-label={`Low Risk: ${summary.low_risk_count}`}>
        <div className="kpi-label">Low Risk</div>
        <div className="kpi-value">{summary.low_risk_count}</div>
      </div>
      <div className="kpi-card"
           role="group" aria-label={`Single-Point Failures: ${summary.total_single_point_failures}`}>
        <div className="kpi-label">Single-Point Failures</div>
        <div className="kpi-value">{summary.total_single_point_failures}</div>
      </div>
      <div className="kpi-card"
           role="group" aria-label={`SRLG Groups: ${summary.total_srlg_groups}`}>
        <div className="kpi-label">SRLG Groups</div>
        <div className="kpi-value">{summary.total_srlg_groups}</div>
      </div>
      <div className="kpi-card"
           role="group" aria-label={`Monitored Services: ${summary.total_services}`}>
        <div className="kpi-label">Monitored Services</div>
        <div className="kpi-value">{summary.total_services}</div>
      </div>
      {/* UX-REVENUE-DISPLAY: Core business metric (~$47.7M/year project value) */}
      {summary.total_revenue_at_risk_usd != null && (
        <div className="kpi-card critical"
             role="group" aria-label={`Revenue at Risk: $${(summary.total_revenue_at_risk_usd / 1_000_000).toFixed(1)}M${v4Kpis ? " per month" : ""}`}>
          <div className="kpi-label">Revenue at Risk</div>
          <div className="kpi-value">
            ${(summary.total_revenue_at_risk_usd / 1_000_000).toFixed(1)}M
            {v4Kpis && <span className="kpi-sub">/mo</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export function ScorecardHeader() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="kpi-row">
              <div className="kpi-card">
                <p>Failed to load summary</p>
                <button className="btn btn-outline" onClick={resetErrorBoundary}>
                  Retry
                </button>
              </div>
            </div>
          )}
        >
          <Suspense
            fallback={
              <LoadingRegion className="kpi-row" label="Loading KPI summary">
                {Array.from({ length: 9 }).map((_, i) => ( /* BUG-DW-034: match 9 KPI cards including Revenue at Risk */
                  <Skeleton key={i} className="h-24 w-full rounded-lg" />
                ))}
              </LoadingRegion>
            }
          >
            <ScorecardHeaderContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
