/**
 * Lakelink Fiber — Hazard Crosswalk KPI Row
 * P10-APP-HAZARD-XWALK-VIEW: 4 KPI cards for hazard×span exposure summary
 *
 * Cards: Total Intersections, Network Exposure, Direct Impact Spans, Hazard Types
 * Pattern: mirrors HazardKpiRow with Suspense + ErrorBoundary.
 */
import { Suspense } from "react";
import { QueryErrorResetBoundary, useSuspenseQuery } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";

interface CrosswalkSummary {
  total_intersections: number;
  distinct_spans_exposed: number;
  total_spans: number;
  exposure_pct: number;
  hazard_types: number;
  direct_impact_count: number;
  near_field_count: number;
  buffer_zone_count: number;
}

function useCrosswalkSummary() {
  return useSuspenseQuery<CrosswalkSummary>({
    queryKey: ["hazardCrosswalkSummary"],
    queryFn: async () => {
      const r = await fetch("/api/hazards/crosswalk/summary");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 60_000,
  });
}

function CrosswalkKpiContent() {
  const { data: summary } = useCrosswalkSummary();

  return (
    <div className="kpi-row">
      <div
        className="kpi-card"
        role="group"
        aria-label={`Total Intersections: ${summary.total_intersections.toLocaleString()}`}
      >
        <div className="kpi-label">Total Intersections</div>
        <div className="kpi-value">{summary.total_intersections.toLocaleString()}</div>
      </div>

      <div
        className={`kpi-card ${summary.exposure_pct > 90 ? "critical" : summary.exposure_pct > 70 ? "high" : ""}`}
        role="group"
        aria-label={`Network Exposure: ${summary.exposure_pct}%`}
      >
        <div className="kpi-label">Network Exposure</div>
        <div className="kpi-value">
          {summary.exposure_pct}%
          <span className="kpi-sub">
            {" "}{summary.distinct_spans_exposed.toLocaleString()} / {summary.total_spans.toLocaleString()} spans
          </span>
        </div>
      </div>

      <div
        className="kpi-card high"
        role="group"
        aria-label={`Direct Impact: ${summary.direct_impact_count.toLocaleString()} intersections`}
      >
        <div className="kpi-label">Direct Impact (&lt;1km)</div>
        <div className="kpi-value">{summary.direct_impact_count.toLocaleString()}</div>
      </div>

      <div
        className="kpi-card"
        role="group"
        aria-label={`Hazard Types: ${summary.hazard_types}`}
      >
        <div className="kpi-label">Hazard Types</div>
        <div className="kpi-value">{summary.hazard_types}</div>
      </div>
    </div>
  );
}

export function HazardCrosswalkKpis() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="kpi-row">
              <div className="kpi-card">
                <p>Failed to load crosswalk summary</p>
                <button className="btn btn-outline" onClick={resetErrorBoundary}>
                  Retry
                </button>
              </div>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div className="kpi-row" aria-busy="true" aria-label="Loading crosswalk summary">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 w-full rounded-lg" />
                ))}
              </div>
            }
          >
            <CrosswalkKpiContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
