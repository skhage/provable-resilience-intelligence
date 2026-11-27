/**
 * Lakelink Fiber - governed resilience risk level (P363, V4-KPI-COPY-SPEC §8.1/§8.2).
 * Pure functions, no React import, so they can be evaluated with Node in tests.
 *
 * One source of truth for the Home KPI risk cards, the Avg Resilience Score caption
 * (scorecard-header.tsx) and the service table gauge (service-table.tsx). Levels and cuts
 * match risk_band_vocabulary GOVERNED_RISK_LEVEL, the resilience_score metric view, Genie and
 * the dashboards: critical < 40 <= at_risk < 60 <= moderate < 80 <= healthy.
 * The header passes the cuts it gets from /api/scores/summary (risk_level_cuts); the constant
 * below is only the fallback. Colour is supplementary; the label is the text signal.
 */

export type ScoreBandKey = "critical" | "at_risk" | "moderate" | "healthy";

export interface ScoreBand {
  key: ScoreBandKey;
  label: string;
}

/** Same shape as the API RiskLevelCutOut. */
export interface RiskLevelCut {
  level: string;
  score_min_inclusive: number;
  score_max_exclusive: number;
}

/** Worst to best (governed_sort_order 1..4). */
export const RISK_LEVEL_ORDER: ReadonlyArray<ScoreBandKey> = ["critical", "at_risk", "moderate", "healthy"];

/** §8.1 card labels, verbatim. The word Risk is not appended. */
export const RISK_LEVEL_LABEL: Readonly<Record<ScoreBandKey, string>> = {
  critical: "Critical",
  at_risk: "At Risk",
  moderate: "Moderate",
  healthy: "Healthy",
};

/** Fallback when the API sends no cuts (mirrors backend/risk_levels.py GOVERNED_RISK_CUTS). */
export const GOVERNED_RISK_CUTS: ReadonlyArray<RiskLevelCut> = [
  { level: "critical", score_min_inclusive: 0, score_max_exclusive: 40 },
  { level: "at_risk", score_min_inclusive: 40, score_max_exclusive: 60 },
  { level: "moderate", score_min_inclusive: 60, score_max_exclusive: 80 },
  { level: "healthy", score_min_inclusive: 80, score_max_exclusive: 100.01 },
];

function isKey(v: string): v is ScoreBandKey {
  return Object.prototype.hasOwnProperty.call(RISK_LEVEL_LABEL, v);
}

/** Usable cuts: the API list when it has all four governed levels, else the fallback. */
export function resolveCuts(cuts?: ReadonlyArray<RiskLevelCut> | null): ReadonlyArray<RiskLevelCut> {
  if (!cuts || cuts.length === 0) return GOVERNED_RISK_CUTS;
  const ok = RISK_LEVEL_ORDER.every((k) =>
    cuts.some((c) => c.level === k && Number.isFinite(c.score_min_inclusive) && Number.isFinite(c.score_max_exclusive)));
  return ok ? cuts : GOVERNED_RISK_CUTS;
}

/** Governed level for a 0-100 resilience score. Non-finite input is treated as critical. */
export function scoreBand(score: number, cuts?: ReadonlyArray<RiskLevelCut> | null): ScoreBand {
  if (Number.isFinite(score)) {
    const bands = [...resolveCuts(cuts)]
      .filter((c) => isKey(c.level))
      .sort((a, b) => b.score_min_inclusive - a.score_min_inclusive);
    for (const b of bands) {
      if (score >= b.score_min_inclusive) {
        const key = b.level as ScoreBandKey;
        return { key, label: RISK_LEVEL_LABEL[key] };
      }
    }
  }
  return { key: "critical", label: RISK_LEVEL_LABEL.critical };
}

/** .kpi-card border modifier per §8.1 Card class column (existing tokens only). */
export const KPI_BORDER_CLASS: Readonly<Record<ScoreBandKey, string>> = {
  critical: "critical",
  at_risk: "high",
  moderate: "warning",
  healthy: "success",
};

export function scoreBandKpiClass(score: number, cuts?: ReadonlyArray<RiskLevelCut> | null): string {
  return KPI_BORDER_CLASS[scoreBand(score, cuts).key];
}

function fmtCut(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/**
 * §8.1 caption, verbatim pattern, built from the cuts (never hard-coded in the component):
 * critical 'Score below 40', at_risk 'Score 40 to 59', moderate 'Score 60 to 79',
 * healthy 'Score 80 or above'.
 */
export function riskLevelCaption(level: ScoreBandKey, cuts?: ReadonlyArray<RiskLevelCut> | null): string {
  const c = resolveCuts(cuts).find((x) => x.level === level) ?? GOVERNED_RISK_CUTS.find((x) => x.level === level)!;
  if (level === "critical") return `Score below ${fmtCut(c.score_max_exclusive)}`;
  if (level === "healthy") return `Score ${fmtCut(c.score_min_inclusive)} or above`;
  return `Score ${fmtCut(c.score_min_inclusive)} to ${fmtCut(Math.ceil(c.score_max_exclusive) - 1)}`;
}

/** §8.1 aria-label: '<Label>: <count> services, <caption lower-case>'. */
export function riskCardAria(level: ScoreBandKey, count: string | number, cuts?: ReadonlyArray<RiskLevelCut> | null): string {
  const cap = riskLevelCaption(level, cuts);
  return `${RISK_LEVEL_LABEL[level]}: ${count} services, ${cap.charAt(0).toLowerCase()}${cap.slice(1)}`;
}

/** §8.2 Avg card caption: '<Label> band', e.g. 'Moderate band'. */
export function avgBandCaption(score: number, cuts?: ReadonlyArray<RiskLevelCut> | null): string {
  return `${scoreBand(score, cuts).label} band`;
}
