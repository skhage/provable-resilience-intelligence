/**
 * Lakelink Fiber - shared resilience score band (BUG-DW-189, WCAG 1.4.1 / 1.4.11).
 * Pure functions, no React import, so they can be evaluated with Node in tests.
 *
 * One source of truth for the score thresholds used by the Home Avg Resilience Score card
 * (scorecard-header.tsx) and the service table gauge (service-table.tsx): 85/70/55/40.
 * Colour is supplementary only; the band label is the text signal.
 */

export type ScoreBandKey = "excellent" | "good" | "fair" | "poor" | "failing";

export interface ScoreBand {
  key: ScoreBandKey;
  label: string;
}

const BANDS: ReadonlyArray<{ min: number; key: ScoreBandKey; label: string }> = [
  { min: 85, key: "excellent", label: "Excellent" },
  { min: 70, key: "good", label: "Good" },
  { min: 55, key: "fair", label: "Fair" },
  { min: 40, key: "poor", label: "Poor" },
];

/** Band for a 0-100 resilience score. Non-finite input is treated as failing. */
export function scoreBand(score: number): ScoreBand {
  if (Number.isFinite(score)) {
    for (const b of BANDS) {
      if (score >= b.min) return { key: b.key, label: b.label };
    }
  }
  return { key: "failing", label: "Failing" };
}

/** .kpi-card border modifier for a band (existing tokens only; colour is supplementary). */
const KPI_BORDER_CLASS: Record<ScoreBandKey, string> = {
  excellent: "success",
  good: "success",
  fair: "warning",
  poor: "high",
  failing: "critical",
};

export function scoreBandKpiClass(score: number): string {
  return KPI_BORDER_CLASS[scoreBand(score).key];
}
