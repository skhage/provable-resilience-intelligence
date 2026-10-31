/**
 * Lakelink Fiber — InterimBadge (P41-APP-V4-INTERIM-BADGE + P68-APP-PROVISIONAL-BADGE)
 * V4-KPI-COPY-SPEC §6.2 (interim) and §7.3 (provisional).
 *
 * Platinum #E8E8E8 fill, iron #4D4D4D 12px/600 uppercase text (6.9:1), 1px iron border, 4px radius
 * and a decorative 3px brand-orange #F26522 left accent. Never orange text. role=img gives the badge
 * one stable accessible name instead of the bare word. The Info tooltip reuses InfoTooltip
 * (BUG-DW-092 hover bridge + close delay).
 *
 * §7.3: the variants differ by text only (WCAG 1.4.1). Same CSS class (.interim-badge) for both
 * so tokens never drift. PROVISIONAL replaces INTERIM; they never appear on the same element.
 */
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { INTERIM_ARIA, INTERIM_LABEL, INTERIM_TOOLTIP } from "@/lib/v4-delta-format";
import {
  PROVISIONAL_ARIA,
  PROVISIONAL_LABEL,
  PROVISIONAL_TOOLTIP,
  PROVISIONAL_INFO_LABEL,
  type BadgeVariant,
} from "@/lib/provisional-disclosure";

const COPY: Record<BadgeVariant, { label: string; aria: string; tooltip: string; info: string }> = {
  interim: {
    label: INTERIM_LABEL,
    aria: INTERIM_ARIA,
    tooltip: INTERIM_TOOLTIP,
    info: "About interim figures",
  },
  provisional: {
    label: PROVISIONAL_LABEL,
    aria: PROVISIONAL_ARIA,
    tooltip: PROVISIONAL_TOOLTIP,
    info: PROVISIONAL_INFO_LABEL,
  },
};

export function InterimBadge({ variant = "interim" }: { variant?: BadgeVariant }) {
  const c = COPY[variant];
  return (
    <span className="interim-badge-wrap">
      <span className="interim-badge" role="img" aria-label={c.aria}>
        {c.label}
      </span>
      <InfoTooltip label={c.info} text={c.tooltip} />
    </span>
  );
}
