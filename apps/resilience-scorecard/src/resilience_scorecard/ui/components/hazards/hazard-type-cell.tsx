/**
 * Lakelink Fiber — HazardTypeCell Component
 * HAZARD-VIS-SPEC §1.2: Hazard type icon + label badge pattern
 *
 * Renders a hazard type as an inline icon + text-label cell.
 * Used in hazard summary tables, action queue cards, and KPI tooltips.
 *
 * Icon library: Lucide React (BRAND-GUIDE §6)
 * Stroke: 1.5px · Inline size: 16px · Standalone: 24px
 * Color: inherits parent text color by default; use CSS variable overrides
 * for standalone emphasis (--lf-hazard-{type}).
 *
 * WCAG 1.4.1: Icon color is NEVER the sole indicator — always paired with text label.
 */
import {
  CloudLightning,
  Activity,
  Waves,
  Flame,
  Construction,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

/** Lucide icon mapping per HAZARD-VIS-SPEC §1 taxonomy */
const HAZARD_ICONS: Record<string, LucideIcon> = {
  severe_weather: CloudLightning,
  earthquake: Activity,
  flood: Waves,
  wildfire: Flame,
  dig_ticket: Construction,
};

/** Human-readable labels (title-case, no underscores) */
const HAZARD_LABELS: Record<string, string> = {
  severe_weather: "Severe Weather",
  earthquake: "Earthquake",
  flood: "Flood",
  wildfire: "Wildfire",
  dig_ticket: "Dig Ticket",
};

/** Default icon props per spec: 16px inline, 1.5px stroke, decorative (aria-hidden) */
const ICON_PROPS = { size: 16, strokeWidth: 1.5, "aria-hidden": true } as const;

export interface HazardTypeCellProps {
  /** Hazard type key from source data (e.g. "severe_weather", "wildfire") */
  type: string;
  /** Optional: override icon size (default 16px inline) */
  iconSize?: number;
  /** Optional: add the .hazard-icon class for severity-based sizing/animation */
  animated?: boolean;
}

/**
 * Inline icon + label cell for hazard type display.
 *
 * @example
 * <HazardTypeCell type="wildfire" />
 * // Renders: 🔥 Wildfire
 *
 * @example — with severity animation context
 * <div className="severity-critical">
 *   <HazardTypeCell type="wildfire" animated />
 * </div>
 * // Icon pulses per HAZARD-VIS-SPEC §3.1
 */
export function HazardTypeCell({ type, iconSize, animated }: HazardTypeCellProps) {
  const Icon = HAZARD_ICONS[type] ?? HelpCircle;
  const label = HAZARD_LABELS[type] ?? type.replace(/_/g, " ");

  return (
    <span className="hazard-type-cell">
      <Icon
        {...ICON_PROPS}
        {...(iconSize ? { size: iconSize } : {})}
        className={animated ? "hazard-icon" : undefined}
      />
      {label}
    </span>
  );
}

/**
 * Utility: get the CSS variable name for a hazard type's icon color.
 * Useful when rendering standalone icons with emphasis color.
 *
 * @example
 * <Icon style={{ color: `var(${getHazardColorVar("wildfire")})` }} />
 */
export function getHazardColorVar(type: string): string {
  const varMap: Record<string, string> = {
    severe_weather: "--lf-hazard-weather",
    earthquake: "--lf-hazard-earthquake",
    flood: "--lf-hazard-flood",
    wildfire: "--lf-hazard-wildfire",
    dig_ticket: "--lf-hazard-dig",
  };
  return varMap[type] ?? "--lf-iron";
}

/** Re-export icon map for downstream consumers (tables, cards) */
export { HAZARD_ICONS, HAZARD_LABELS, ICON_PROPS };
