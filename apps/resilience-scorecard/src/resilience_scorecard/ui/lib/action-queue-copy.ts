/**
 * Lakelink Fiber - Action Queue copy helpers (BUG-DW-104).
 * Pure functions and constants, no imports, so Node can evaluate them directly in tests.
 */

/** Human-readable label for every action status enum value (BUG-DW-104 item 1). */
export const STATUS_LABEL: Readonly<Record<string, string>> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
  cancelled: "Cancelled",
};

/**
 * Label for a status. Unknown values fall back to sentence case with EVERY underscore
 * replaced (the old .replace("_", " ") only replaced the first one).
 */
export function statusLabel(status: string | null | undefined): string {
  if (!status) return "All";
  const known = STATUS_LABEL[status];
  if (known) return known;
  const spaced = status.replace(/_/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase() : "All";
}

/** Success toast after a status change: 'Action marked In progress for <service_name>'. */
export function statusToast(status: string, serviceName?: string | null): string {
  const base = `Action marked ${statusLabel(status)}`;
  return serviceName ? `${base} for ${serviceName}` : base;
}

/** Error-boundary copy for the action queue (BUG-DW-104 item 5). */
export const ACTION_QUEUE_LOAD_ERROR =
  "Couldn\u2019t load the action queue. Check your connection and retry.";

/**
 * Hazard 'Last Update' format with an explicit time zone (BUG-DW-104 item 6).
 * Equivalent to {dateStyle:'medium', timeStyle:'short'} plus timeZoneName:'short'. ECMA-402
 * throws a TypeError when dateStyle/timeStyle are combined with timeZoneName, so the
 * medium/short styles are spelled out as components: 'Oct 30, 2026, 8:05 AM MDT'.
 */
export const HAZARD_TIME_FORMAT: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
};

/** Format a hazard timestamp; returns the raw value when it is not a valid date. */
export function formatHazardTime(value: unknown, locale?: string, timeZone?: string): string {
  const raw = String(value);
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const opts: Intl.DateTimeFormatOptions = timeZone
    ? { ...HAZARD_TIME_FORMAT, timeZone }
    : HAZARD_TIME_FORMAT;
  return d.toLocaleString(locale, opts);
}

/** Number of KPI skeleton cards in the Suspense fallback: 5 with the v4 MRC card (item 7). */
export function actionKpiSkeletonCount(v4Kpis: boolean): number {
  return v4Kpis ? 5 : 4;
}
