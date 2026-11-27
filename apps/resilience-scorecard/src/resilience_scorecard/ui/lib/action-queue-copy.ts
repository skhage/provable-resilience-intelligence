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

/**
 * BUG-DW-191: known action_type labels, checked before the generic sentence-case rule so
 * acronyms survive ('escalate_noc' -> 'Escalate to NOC', not 'Escalate noc'). Keys are the
 * lowercase enum values. The other live types (reroute, dispatch_crew, notify_customer,
 * preposition_splice) stay on the generic rule.
 */
export const ACTION_TYPE_LABEL: Readonly<Record<string, string>> = {
  escalate_noc: "Escalate to NOC",
};

/**
 * BUG-DW-185: Type-column label for an action_type enum. Sentence case with every underscore
 * replaced ('reroute_service' -> 'Reroute service'), matching statusLabel(). Done in source,
 * not CSS text-transform, so screen readers announce the same text that is shown.
 * BUG-DW-191: ACTION_TYPE_LABEL is consulted first (own-property only, case-insensitive key).
 */
export function actionTypeLabel(actionType: string | null | undefined): string {
  if (!actionType) return "";
  const key = actionType.trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(ACTION_TYPE_LABEL, key)) return ACTION_TYPE_LABEL[key];
  const spaced = actionType.replace(/_/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase() : "";
}

/**
 * P363 / V4-KPI-COPY-SPEC §8.3: proactive_action.priority is action urgency, not a risk level.
 * Stored values are unchanged; only the badge text and aria-label change, so a badge never
 * reuses a risk word. Order is P1..P4 for any filter or sort control.
 */
export const PRIORITY_ORDER: ReadonlyArray<string> = ["critical", "high", "medium", "low"];

export const PRIORITY_LABEL: Readonly<Record<string, string>> = {
  critical: "P1 Urgent",
  high: "P2 High",
  medium: "P3 Normal",
  low: "P4 Low",
};

export const PRIORITY_ARIA: Readonly<Record<string, string>> = {
  critical: "Priority 1, urgent",
  high: "Priority 2, high",
  medium: "Priority 3, normal",
  low: "Priority 4, low",
};

function priorityKey(priority: string | null | undefined): string | null {
  if (!priority) return null;
  const key = String(priority).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(PRIORITY_LABEL, key) ? key : null;
}

/** Badge text: 'P1 Urgent'..'P4 Low'; unknown or null -> 'Unranked' (never blank). */
export function priorityLabel(priority: string | null | undefined): string {
  const k = priorityKey(priority);
  return k ? PRIORITY_LABEL[k] : "Unranked";
}

/** aria-label: 'Priority 1, urgent'..; unknown or null -> 'Priority unranked'. */
export function priorityAria(priority: string | null | undefined): string {
  const k = priorityKey(priority);
  return k ? PRIORITY_ARIA[k] : "Priority unranked";
}

/** Existing .badge.<priority> colour class (BUG-QA-018 contrast); 'neutral' when unknown. */
export function priorityBadgeClass(priority: string | null | undefined): string {
  return priorityKey(priority) ?? "neutral";
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
