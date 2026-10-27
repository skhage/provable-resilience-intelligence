/**
 * Lakelink Fiber — InterimBadge (P41-APP-V4-INTERIM-BADGE, V4-KPI-COPY-SPEC §6.2)
 *
 * Platinum #E8E8E8 fill, iron #4D4D4D 12px/600 uppercase text (6.9:1), 1px iron border, 4px radius
 * and a decorative 3px brand-orange #F26522 left accent. Never orange text. role=img gives the badge one
 * stable accessible name (§6.2 aria-label) instead of the bare word "Interim". The Info tooltip
 * reuses InfoTooltip (BUG-DW-092 hover bridge + close delay).
 *
 * Render only when showInterimBadge(v4Kpis, summary.report_status) is true; callers keep the v3
 * freeze markup in the other branch.
 */
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { INTERIM_ARIA, INTERIM_LABEL, INTERIM_TOOLTIP } from "@/lib/v4-delta-format";

export function InterimBadge() {
  return (
    <span className="interim-badge-wrap">
      <span className="interim-badge" role="img" aria-label={INTERIM_ARIA}>
        {INTERIM_LABEL}
      </span>
      <InfoTooltip label="About interim figures" text={INTERIM_TOOLTIP} />
    </span>
  );
}
