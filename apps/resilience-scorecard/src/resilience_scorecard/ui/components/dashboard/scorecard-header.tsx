/**
 * Lakelink Fiber — Resilience Scorecard Dashboard Header
 * Displays aggregate KPIs: avg score, risk counts, SPFs, SRLGs
 */
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { RetryBoundary } from "@/components/ui/retry-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { InterimBadge } from "@/components/ui/interim-badge";
import { useGetResilienceSummarySuspense, useCutoverManifest, useV4Kpis } from "@/lib/api";
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
} from "@/lib/v4-delta-format";
import { badgeVariant, type BadgeVariant } from "@/lib/provisional-disclosure";
import selector from "@/lib/selector";
// P363 (V4-KPI-COPY-SPEC §8.1/§8.2): governed risk levels shared with the service table gauge.
// Cuts come from the API (summary.risk_level_cuts, read from risk_band_vocabulary); border
// colour is supplementary and the label/caption is the text signal in both flag states.
import {
  scoreBand,
  scoreBandKpiClass,
  avgBandCaption,
  riskLevelCaption,
  riskCardAria,
  RISK_LEVEL_LABEL,
} from "@/lib/score-band";

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
        {/* §6.3: same line, joined with a non-breaking space. BUG-DW-097/129: role=group aria-label
            names the card but does NOT hide its children, so the visual slash qualifier is
            aria-hidden; the spoken "metro and access" comes only from the card aria-label (no sr-only
            span, which would make it spoken twice). .kpi-sub--disclosure = solid iron (v4-only). */}
        {partial && <span className="kpi-sub kpi-sub--disclosure" aria-hidden="true">{`\u00A0${METRO_ACCESS}`}</span>}
      </div>
      <div className="kpi-caption">{SRLG_SUBLINE[coverage]}</div>
    </div>
  );
}

function ScorecardHeaderContent() {
  const { data: summary } = useGetResilienceSummarySuspense(selector());
  // V4-KPI-COPY-SPEC §1 unit consistency: Revenue at Risk is monthly, shown as /mo under the flag.
  const v4Kpis = useV4Kpis();
  // P41/P68 (V4-KPI-COPY-SPEC §6.2/§7): badge driven by API report_status + cutover manifest.
  // §7.1: PROVISIONAL replaces INTERIM on surfaces whose source object is KEPT_V3_PROVISIONAL.
  // Flag off: every expression below falls back to the v3 freeze markup/formatting.
  const manifest = useCutoverManifest();
  const provisionalObjects = manifest?.provisional_objects ?? [];
  const headerVariant: BadgeVariant | null = badgeVariant(
    v4Kpis, summary.report_status, provisionalObjects, "scorecard_header",
  );
  const avgScore = v4Kpis ? formatScore(summary.avg_resilience_score) : summary.avg_resilience_score.toFixed(1);
  const cuts = summary.risk_level_cuts;
  const avgBand = scoreBand(summary.avg_resilience_score, cuts);
  const avgCaption = avgBandCaption(summary.avg_resilience_score, cuts);
  const critical = v4Kpis ? formatKpiCount(summary.critical_count) : summary.critical_count;
  // BUG-DW-123 (§7.7 #4): At Risk uses the same thousands formatting as Critical under the flag.
  const atRisk = v4Kpis ? formatKpiCount(summary.at_risk_count) : summary.at_risk_count;
  // BUG-DW-126: Moderate follows the same pattern so the count row never mixes formats.
  const moderate = v4Kpis ? formatKpiCount(summary.moderate_count) : summary.moderate_count;
  // BUG-DW-127: the remaining count cards use the same flag-gated formatter (value + aria-label).
  // SRLG Groups under the flag is formatted inside SrlgGroupsV4Card; its v3 branch is flag-off only.
  const healthy = v4Kpis ? formatKpiCount(summary.healthy_count) : summary.healthy_count;
  const singlePointFailures = v4Kpis ? formatKpiCount(summary.total_single_point_failures) : summary.total_single_point_failures;
  const monitoredServices = v4Kpis ? formatKpiCount(summary.total_services) : summary.total_services;
  // BUG-DW-190: backend/models.py allows None; treat undefined the same way.
  const revenueAtRisk = summary.total_revenue_at_risk_usd ?? null;

  return (
    <div className="kpi-row">
      <div className={`kpi-card ${scoreBandKpiClass(summary.avg_resilience_score, cuts)}`}
           role="group" aria-label={`Avg Resilience Score: ${avgScore}, ${avgCaption.toLowerCase()}`}
           data-band={avgBand.key}>
        {headerVariant ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>Avg Resilience Score</span>
            <InterimBadge variant={headerVariant} />
          </div>
        ) : (
          <div className="kpi-label">Avg Resilience Score</div>
        )}
        <div className="kpi-value score">{avgScore}</div>
        {/* P363 §8.2 (WCAG 1.4.1): '<Label> band' as text, solid iron 8.45:1, both flag states. */}
        <div className="kpi-caption">{avgCaption}</div>
      </div>
      <div className="kpi-card critical"
           role="group" aria-label={riskCardAria("critical", critical, cuts)}>
        {headerVariant ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>{RISK_LEVEL_LABEL.critical}</span>
            <InterimBadge variant={headerVariant} />
          </div>
        ) : (
          <div className="kpi-label">{RISK_LEVEL_LABEL.critical}</div>
        )}
        <div className="kpi-value">{critical}</div>
        <div className="kpi-caption">{riskLevelCaption("critical", cuts)}</div>
      </div>
      <div className="kpi-card high"
           role="group" aria-label={riskCardAria("at_risk", atRisk, cuts)}>
        {/* §7.2 / §8.1: At Risk (the second risk card) also gets the PROVISIONAL badge in partial cutover */}
        {headerVariant === "provisional" ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>{RISK_LEVEL_LABEL.at_risk}</span>
            <InterimBadge variant="provisional" />
          </div>
        ) : (
          <div className="kpi-label">{RISK_LEVEL_LABEL.at_risk}</div>
        )}
        <div className="kpi-value">{atRisk}</div>
        <div className="kpi-caption">{riskLevelCaption("at_risk", cuts)}</div>
      </div>
      <div className="kpi-card warning"
           role="group" aria-label={riskCardAria("moderate", moderate, cuts)}>
        <div className="kpi-label">{RISK_LEVEL_LABEL.moderate}</div>
        <div className="kpi-value">{moderate}</div>
        <div className="kpi-caption">{riskLevelCaption("moderate", cuts)}</div>
      </div>
      <div className="kpi-card success"
           role="group" aria-label={riskCardAria("healthy", healthy, cuts)}>
        <div className="kpi-label">{RISK_LEVEL_LABEL.healthy}</div>
        <div className="kpi-value">{healthy}</div>
        <div className="kpi-caption">{riskLevelCaption("healthy", cuts)}</div>
      </div>
      <div className="kpi-card"
           role="group" aria-label={`Single-Point Failures: ${singlePointFailures}`}>
        <div className="kpi-label">Single-Point Failures</div>
        <div className="kpi-value">{singlePointFailures}</div>
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
           role="group" aria-label={`Monitored Services: ${monitoredServices}`}>
        <div className="kpi-label">Monitored Services</div>
        <div className="kpi-value">{monitoredServices}</div>
      </div>
      {/* UX-REVENUE-DISPLAY: Core business metric (~$47.7M/year project value) */}
      {/* BUG-DW-190: always render the card so the 9-card layout (BUG-DW-034 skeleton) never collapses;
          a null value is shown honestly as "Not available" (same rule as BUG-DW-164/166). */}
      <div className="kpi-card critical"
           role="group" aria-label={revenueAtRisk == null
             ? "Revenue at Risk: not available"
             : `Revenue at Risk: $${v4Kpis ? formatMillions(revenueAtRisk) : (revenueAtRisk / 1_000_000).toFixed(1)}M${v4Kpis ? " per month" : ""}`}>
        {headerVariant ? (
          <div className="kpi-label kpi-label-row kpi-label-row--interim">
            <span>Revenue at Risk</span>
            <InterimBadge variant={headerVariant} />
          </div>
        ) : (
          <div className="kpi-label">Revenue at Risk</div>
        )}
        {revenueAtRisk == null ? (
          <>
            <div className="kpi-value" aria-hidden="true">{"\u2014"}</div>
            <div className="kpi-caption">Not available</div>
          </>
        ) : (
          <div className="kpi-value">
            ${v4Kpis ? formatMillions(revenueAtRisk) : (revenueAtRisk / 1_000_000).toFixed(1)}M
            {v4Kpis && <span className="kpi-sub">/mo</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export function ScorecardHeader() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <RetryBoundary
          onReset={reset}
          fallback={(retryButton) => (
            /* BUG-DW-170: role=alert so the failure is announced (WCAG 4.1.3), matching ProductCatalog/ServiceTable */
            <div className="kpi-row" role="alert">
              <div className="kpi-card">
                <p>Failed to load summary</p>
                {retryButton}
              </div>
            </div>
          )}
          loading={
            <LoadingRegion className="kpi-row" label="Loading KPI summary">
              {Array.from({ length: 9 }).map((_, i) => ( /* BUG-DW-034: match 9 KPI cards including Revenue at Risk */
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))}
            </LoadingRegion>
          }
        >
          <ScorecardHeaderContent />
        </RetryBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
