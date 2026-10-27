/**
 * Lakelink Fiber — v4 INTERIM badge copy + v3-to-v4 delta number formatting (P41-APP-V4-INTERIM-BADGE)
 * V4-KPI-COPY-SPEC §6.2 (badge), §6.4 (formatting). Used only when PRI_V4_KPIS=true; the v3
 * freeze UI never calls these helpers.
 *
 * Rules (§6.4): round half up from raw values; deltas are computed from the ROUNDED endpoints so the
 * display arithmetic always reconciles (61.6 − 56.8 = 4.8); U+2212 minus for negatives; thousands
 * separators on counts; money as $#.#M/mo; a zero delta reads "no change" (words, never 0.0);
 * arrows render as → visually and are spoken as "to". Delta colour is neutral iron for every
 * direction (see .v4-delta in lakelink-theme.css), never red/green.
 */

/** §6.2 visible badge text (CSS uppercases it). */
export const INTERIM_LABEL = "Interim";
/** §6.2 badge accessible name, verbatim. */
export const INTERIM_ARIA = "Interim figure, v4 candidate, subject to change";
/** §6.2 Info tooltip text, verbatim. */
export const INTERIM_TOOLTIP =
  "Preliminary v4 figures. Only the hazard-distance fix is included so far. Backbone segmentation and shared-risk updates are still being scored, so these numbers will change.";

export type ReportStatus = "INTERIM" | "FINAL";

/** Badge shows only with the flag on AND an API-reported INTERIM status (never hard-coded). */
export function showInterimBadge(v4Kpis: boolean, reportStatus: unknown): boolean {
  return v4Kpis && reportStatus === "INTERIM";
}

export const MINUS = "\u2212";
export const ARROW = "\u2192";
export const NO_CHANGE = "no change";

/**
 * Round half up (away from zero for negatives, so −4.75 -> −4.8). toPrecision(12) strips binary
 * noise first, so 61.55 (stored as 61.5499999...) rounds to 61.6 as the spec shows.
 */
export function roundHalfUp(x: number, dp: number): number {
  const f = 10 ** dp;
  const scaled = Number((Math.abs(x) * f).toPrecision(12));
  const r = Math.floor(scaled + 0.5) / f;
  return x < 0 && r !== 0 ? -r : r;
}

function fixed(x: number, dp: number): string {
  return roundHalfUp(x, dp).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

/** Avg score: 1 dp (`61.6`). */
export function formatScore(x: number): string {
  return fixed(x, 1);
}

/** Counts: thousands separators, integers (`1,087`). */
export function formatKpiCount(x: number): string {
  return fixed(x, 0);
}

/** USD millions with 1 dp, no unit (`48.4`). */
export function formatMillions(usd: number): string {
  return fixed(usd / 1_000_000, 1);
}

/** Monthly money (`$48.4M/mo`). */
export function formatMoneyPerMonth(usd: number): string {
  return `$${formatMillions(usd)}M/mo`;
}

export type DeltaKind = "score" | "count" | "money" | "percent";

const DP: Record<DeltaKind, number> = { score: 1, count: 0, money: 1, percent: 1 };

function toUnits(kind: DeltaKind, raw: number): number {
  return kind === "money" ? raw / 1_000_000 : raw;
}

function formatValue(kind: DeltaKind, raw: number): string {
  switch (kind) {
    case "score":
      return formatScore(raw);
    case "count":
      return formatKpiCount(raw);
    case "money":
      return formatMoneyPerMonth(raw);
    case "percent":
      return `${fixed(raw, 1)}%`;
  }
}

/**
 * Signed delta from the rounded endpoints: `−4.8`, `+239`, `+$6.0M/mo`, `no change`.
 * Reconciles by construction: delta = round(v4) − round(v3).
 */
export function formatDelta(kind: DeltaKind, v3Raw: number, v4Raw: number): string {
  const dp = DP[kind];
  const d = roundHalfUp(
    roundHalfUp(toUnits(kind, v4Raw), dp) - roundHalfUp(toUnits(kind, v3Raw), dp),
    dp,
  );
  if (d === 0) return NO_CHANGE;
  const sign = d < 0 ? MINUS : "+";
  const mag = Math.abs(d).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
  switch (kind) {
    case "money":
      return `${sign}$${mag}M/mo`;
    case "percent":
      return `${sign}${mag} pts`;
    default:
      return `${sign}${mag}`;
  }
}

export interface DeltaTransition {
  /** e.g. `61.6` */
  from: string;
  /** e.g. `56.8` */
  to: string;
  /** Visual: `61.6 → 56.8` */
  text: string;
  /** e.g. `−4.8` or `no change` */
  delta: string;
  /** Spoken: `Average score 61.6 to 56.8, interim` (arrow read as "to") */
  aria: string;
}

/** §6.4 transition text for any v3-to-v4 delta view. */
export function deltaTransition(
  label: string,
  kind: DeltaKind,
  v3Raw: number,
  v4Raw: number,
  interim: boolean,
): DeltaTransition {
  const from = formatValue(kind, v3Raw);
  const to = formatValue(kind, v4Raw);
  return {
    from,
    to,
    text: `${from} ${ARROW} ${to}`,
    delta: formatDelta(kind, v3Raw, v4Raw),
    aria: `${label} ${from} to ${to}${interim ? ", interim" : ""}`,
  };
}
