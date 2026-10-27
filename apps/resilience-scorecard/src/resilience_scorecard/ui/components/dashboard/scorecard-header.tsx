/**
 * Lakelink Fiber — Resilience Scorecard Dashboard Header
 * Displays aggregate KPIs: avg score, risk counts, SPFs, SRLGs
 */
import { Suspense } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { InterimBadge } from "@/components/ui/interim-badge";
import { useGetResilienceSummarySuspense, useV4Kpis } from "@/lib/api";
import {
  BB_SRLG_PARTIAL_TOOLTIP,
  METRO_ACCESS,
  SRLG_DEFINITION,
  SRLG_SUBLINE,
  formatCount,
  type BbSrlgCoverage,
} from "@/lib/bb-srlg-disclosure";
import {
  formatKpiCount,
  formatMillions,
  formatScore,
  showInterimBadge,
} from "@/lib/v4-delta-format";
import selector from "@/lib/selector";

function scoreClass(score: number): string {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  if (score >= 40) return "high";
  return "critical";
}

/**
 * P36-APP-V4-BB-SRLG-DISCLOSURE (V4-KPI-COPY-SPEC §2.1/§2.2, §6.3, §6.4). Rendered only when
 * PRI_V4_KPIS=true. The v3 card below stays byte-identical for the freeze.
 */
function SrlgGroupsV4Card({ total, coverage }: { total: number; coverage: BbSrlgCoverage }) {
  const n = formatCount(total);
  const partial = coverage === "partial";
  const aria = partial
    ? `SRLG Groups: ${n}, metro and access spans only`
    : `SRLG Groups: ${n}, metro, access and backbone spans`;
  return (
    <div className="kpi-card" role="group" aria-label={aria}>
      <div className="kpi-label kpi-label-row">
        <span>SRLG Groups</span>
        <InfoTooltip label="About SRLG Groups" text={partial ? BB_SRLG_PARTIAL_TOOLTIP : SRLG_DEFINITION} />
      </div>
      <div className="kpi-value">
        {n}
        {/* §6.3: same line, joined with a non-breaking space; speech comes from the card aria-label */}
        {partial && <span className="kpi-sub">{`\u00A0${METRO_ACCESS}`}</span>}
      </div>
      <div className="kpi-caption">{SRLG_SUBLINE[coverage]}</div>
    </div>
  );
}

function ScorecardHeaderContent() {
  const { data: summary } = useGetResilienceSummarySuspense(selector());
  // V4-KPI-COPY-SPEC §1 unit consistency: Revenue at Risk is monthly, shown as /mo under the flag.
  const v4Kpis = useV4Kpis();
  // P41-APP-V4-INTERIM-BADGE (V4-KPI-COPY-SPEC §6.2/§6.4): badge driven by the API report_status
  // (never hard-coded) on Avg Score, Critical and Revenue at Risk only (not MRC Protected).
  // Flag off: every expression below falls back to the v3 freeze markup/formatting.
  const interim = showInterimBadge(v4Kpis, summary.report_status);
  const avgScore = v4Kpis ? formatScore(summary.avg_resilience_score) : summary.avg_resilience_score.toFixed(1);
  const critical = v4Kpis ? formatKpiCount(summary.critical_count) : summary.critical_count;

  return (
    <div className="kpi-row">
      <div className={`kpi-card ${scoreClass(summary.avg_resilience_score)}`}
           role="group" aria-label={`Avg Resilience Score: ${avgScore}`}>
        {interim ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>Avg Resilience Score</span>
            <InterimBadge />
          </div>
        ) : (
          <div className="kpi-label">Avg Resilience Score</div>
        )}
        <div className="kpi-value score">{avgScore}</div>
      </div>
      <div className="kpi-card critical"
           role="group" aria-label={`Critical Risk: ${critical}`}>
        {interim ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>Critical Risk</span>
            <InterimBadge />
          </div>
        ) : (
          <div className="kpi-label">Critical Risk</div>
        )}
        <div className="kpi-value">{critical}</div>
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
      {v4Kpis ? (
        <SrlgGroupsV4Card
          total={summary.total_srlg_groups}
          coverage={summary.bb_srlg_coverage === "complete" ? "complete" : "partial"}
        />
      ) : (
        <div className="kpi-card"
             role="group" aria-label={`SRLG Groups: ${summary.total_srlg_groups}`}>
          <div className="kpi-label">SRLG Groups</div>
          <div className="kpi-value">{summary.total_srlg_groups}</div>
        </div>
      )}
      <div className="kpi-card"
           role="group" aria-label={`Monitored Services: ${summary.total_services}`}>
        <div className="kpi-label">Monitored Services</div>
        <div className="kpi-value">{summary.total_services}</div>
      </div>
      {/* UX-REVENUE-DISPLAY: Core business metric (~$47.7M/year project value) */}
      {summary.total_revenue_at_risk_usd != null && (
        <div className="kpi-card critical"
             role="group" aria-label={`Revenue at Risk: $${v4Kpis ? formatMillions(summary.total_revenue_at_risk_usd) : (summary.total_revenue_at_risk_usd / 1_000_000).toFixed(1)}M${v4Kpis ? " per month" : ""}`}>
          {interim ? (
            <div className="kpi-label kpi-label-row kpi-label-row--interim">
              <span>Revenue at Risk</span>
              <InterimBadge />
            </div>
          ) : (
            <div className="kpi-label">Revenue at Risk</div>
          )}
          <div className="kpi-value">
            ${v4Kpis ? formatMillions(summary.total_revenue_at_risk_usd) : (summary.total_revenue_at_risk_usd / 1_000_000).toFixed(1)}M
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
