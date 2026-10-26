/**
 * Lakelink Fiber — Proactive Action Queue Table
 * Shows pending/in-progress actions with status update buttons.
 * State is persisted in Lakebase Postgres.
 */
import { Suspense, useState, useCallback, useEffect, useRef, Fragment } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import {
  useListActionsSuspense,
  useGetActionSummarySuspense,
  useUpdateActionStatus,
  useV4Kpis,
  useGetMrcProtected,
} from "@/lib/api";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { useQueryClient } from "@tanstack/react-query";
import selector from "@/lib/selector";
import {
  Shuffle,
  Wrench,
  Mail,
  AlertTriangle,
  Scissors,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  MapPin,
  X,
  type LucideIcon,
} from "lucide-react";
import { HazardTypeCell } from "@/components/hazards";

/** Lucide icon per action type — brand guide §6: 1.5px stroke, 16px inline */
const ICON_PROPS = { size: 16, strokeWidth: 1.5, "aria-hidden": true as const } as const;

const ACTION_TYPE_ICONS: Record<string, LucideIcon> = {
  reroute: Shuffle,
  dispatch: Wrench,
  dispatch_crew: Wrench,
  notify: Mail,
  notify_customer: Mail,
  escalate_noc: AlertTriangle,
  preposition_splice: Scissors,
};

/** V4-KPI-COPY-SPEC §1 definition (verbatim; tooltip + README). */
const MRC_PROTECTED_DEFINITION =
  "Monthly recurring charge of distinct services with at least one completed proactive action. Each service is counted once.";

/** $ + millions to 1 dp + M; under $1M use $###K. Returns [display, spoken]. */
function formatMonthlyUsd(usd: number): [string, string] {
  if (usd >= 1_000_000) {
    const m = (usd / 1_000_000).toFixed(1);
    return [`$${m}M`, `$${m} million`];
  }
  const k = Math.round(usd / 1_000);
  return [`$${k}K`, `$${k} thousand`];
}

/**
 * P36-APP-V4-MRC-PROTECTED-KPI: 5th Action Queue card, after Completed.
 * Source: mv_mrc_protected_v4_candidate (distinct service_id, never summed per action).
 * Null / error / zero: render nothing (never $0).
 * Pending: same-size decorative skeleton card (BUG-DW-092) so the other 4
 * cards in the auto-fit .kpi-row do not resize when the value arrives.
 */
function MrcProtectedCard() {
  const { data, isError, isPending } = useGetMrcProtected(true);
  if (isPending) {
    return (
      <div className="kpi-card kpi-card-skeleton" aria-hidden="true">
        <Skeleton className="kpi-skel-label" />
        <Skeleton className="kpi-skel-value" />
        <Skeleton className="kpi-skel-caption" />
      </div>
    );
  }
  if (isError || !data || !(data.mrc_protected_usd > 0) || !(data.services_protected > 0)) {
    return null;
  }
  const [value, spoken] = formatMonthlyUsd(data.mrc_protected_usd);
  const services = data.services_protected.toLocaleString("en-US");
  const share = (data.mrc_share * 100).toFixed(1);
  return (
    <div className="kpi-card success"
         role="group"
         aria-label={`MRC Protected: ${spoken} per month across ${services} services with at least one completed action`}>
      <div className="kpi-label kpi-label-row">
        <span>MRC Protected</span>
        <InfoTooltip label="About MRC Protected" text={MRC_PROTECTED_DEFINITION} />
      </div>
      <div className="kpi-value">
        {value}<span className="kpi-sub">/mo</span>
      </div>
      <div className="kpi-caption">{services} services · {share}% of MRC</div>
    </div>
  );
}

function ActionSummaryCards() {
  const { data: summary } = useGetActionSummarySuspense(selector());
  const v4Kpis = useV4Kpis();

  return (
    <div className="kpi-row">
      <div className="kpi-card critical"
           role="group" aria-label={`Critical Pending: ${summary.critical_pending}`}>
        <div className="kpi-label">Critical Pending</div>
        <div className="kpi-value">{summary.critical_pending}</div>
      </div>
      <div className="kpi-card warning"
           role="group" aria-label={`Total Pending: ${summary.pending_count}`}>
        <div className="kpi-label">Total Pending</div>
        <div className="kpi-value">{summary.pending_count}</div>
      </div>
      <div className="kpi-card"
           role="group" aria-label={`In Progress: ${summary.in_progress_count}`}>
        <div className="kpi-label">In Progress</div>
        <div className="kpi-value">{summary.in_progress_count}</div>
      </div>
      <div className="kpi-card success"
           role="group" aria-label={`Completed: ${summary.completed_count}`}>
        <div className="kpi-label">Completed</div>
        <div className="kpi-value">{summary.completed_count}</div>
      </div>
      {v4Kpis && <MrcProtectedCard />}
    </div>
  );
}

const PAGE_SIZES = [10, 25, 50, 100] as const;

function ActionTableContent() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [toasts, setToasts] = useState<Array<{ id: number; message: string; variant: string }>>([]);
  const [expandedActions, setExpandedActions] = useState<Set<string>>(new Set());

  const toggleExpand = useCallback((actionId: string) => {
    setExpandedActions((prev) => {
      const next = new Set(prev);
      if (next.has(actionId)) next.delete(actionId);
      else next.add(actionId);
      return next;
    });
  }, []);
  const { data: actions } = useListActionsSuspense({
    params: { status_filter: statusFilter },
    ...selector(),
  });
  const queryClient = useQueryClient();

  // BUG-DW-074: monotonic counter avoids Date.now() id collisions on rapid clicks
  const toastIdRef = useRef(0);
  const toastTimersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismissToast = useCallback((id: number) => {
    const timer = toastTimersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      toastTimersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, variant = "success") => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, variant }]);
    // BUG-DW-074 (WCAG 2.2.1 / 4.1.3): error toasts persist until dismissed;
    // only success/status toasts auto-dismiss after 5s.
    if (variant !== "error") {
      const timer = setTimeout(() => {
        toastTimersRef.current.delete(id);
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 5000);
      toastTimersRef.current.set(id, timer);
    }
  }, []);

  // Clear pending timers on unmount
  useEffect(() => {
    const timers = toastTimersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  const { mutate: updateStatus, isPending } = useUpdateActionStatus({
    mutation: {
      onSuccess: (_data, variables) => {
        queryClient.invalidateQueries({ queryKey: ["listActions"] });
        queryClient.invalidateQueries({ queryKey: ["getActionSummary"] });
        queryClient.invalidateQueries({ queryKey: ["getMrcProtected"] });
        const label = variables.data.status.replace("_", " ");
        addToast(`Action updated to ${label}`);
      },
      onError: () => {
        addToast("Failed to update action", "error");
      },
    },
  });

  const handleStatusChange = (actionId: string, newStatus: string) => {
    updateStatus({
      actionId,
      data: { status: newStatus },
    });
  };

  return (
    <>
      {/* Status filter tabs (UX-REM-A11Y-LANDMARKS §5 + UX-REM-A11Y-FILTER-PRESSED) */}
      <div role="group" aria-label="Status filters" className="filter-bar">
        {[undefined, "pending", "in_progress", "completed", "cancelled"].map((s) => (
          <button
            key={s ?? "all"}
            className={`btn ${statusFilter === s ? "btn-primary" : "btn-outline"}`}
            onClick={() => { setStatusFilter(s); setPage(1); }}
            aria-pressed={statusFilter === s}
          >
            {s ? s.replace("_", " ") : "All"}
          </button>
        ))}
      </div>

      {/* BUG-QA-020: Pagination state derived from filtered actions */}
      {actions.length === 0 ? (
        <div className="data-table">
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
            <p>No actions match this filter</p>
            <p className="empty-hint">Try selecting a different status or view all actions.</p>
          </div>
        </div>
      ) : (
        <div className="data-table">
          <table aria-label="Proactive action queue">
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">Service</th>
                <th scope="col">Risk Trigger</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Assigned To</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const totalPages = Math.max(1, Math.ceil(actions.length / pageSize));
                const safeCurrentPage = Math.min(page, totalPages);
                return actions.slice(
                  (safeCurrentPage - 1) * pageSize,
                  safeCurrentPage * pageSize,
                );
              })().map((a) => {
                const hasHazard = !!a.hazard_type;
                const isExpanded = expandedActions.has(a.action_id);
                return (
                  <Fragment key={a.action_id}>
                    <tr>
                      <td>
                        <span title={a.action_type} className="action-type-cell">
                          {(() => {
                            const Icon = ACTION_TYPE_ICONS[a.action_type] ?? HelpCircle;
                            return <Icon {...ICON_PROPS} />;
                          })()}
                          {" "}{a.action_type.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="text-medium">
                        {a.service_name}
                        {hasHazard && (
                          <button
                            className="expand-toggle ml-auto"
                            onClick={() => toggleExpand(a.action_id)}
                            aria-expanded={isExpanded}
                            aria-label={`${isExpanded ? "Collapse" : "Expand"} hazard details for ${a.service_name}`}
                          >
                            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </button>
                        )}
                      </td>
                      <td className="text-sm max-w-280">{a.risk_trigger}</td>
                      <td>
                        <span className={`badge ${a.priority}`}>{a.priority}</span>
                      </td>
                      <td>
                        <span className={`badge ${a.status}`}>
                          {a.status.replace("_", " ")}
                        </span>
                      </td>
                      <td>{a.assigned_to ?? "—"}</td>
                      <td>
                        {a.status === "pending" && (
                          <button
                            className="btn btn-primary"
                            disabled={isPending}
                            onClick={() => handleStatusChange(a.action_id, "in_progress")}
                            aria-label={`Start action for ${a.service_name}`}
                          >
                            Start
                          </button>
                        )}
                        {a.status === "in_progress" && (
                          <button
                            className="btn btn-primary"
                            disabled={isPending}
                            onClick={() => handleStatusChange(a.action_id, "completed")}
                            aria-label={`Complete action for ${a.service_name}`}
                          >
                            Complete
                          </button>
                        )}
                      </td>
                    </tr>
                    {/* HAZARD-VIS-SPEC §5: Expandable hazard detail row */}
                    {hasHazard && isExpanded && (
                      <tr className="hazard-detail-row">
                        <td colSpan={7}>
                          <div className="hazard-detail-content">
                            <div>
                              <div className="detail-label">Hazard</div>
                              <div className="detail-value">
                                <HazardTypeCell type={a.hazard_type!} animated />
                              </div>
                            </div>
                            <div>
                              <div className="detail-label">Event</div>
                              <div className="detail-value">{a.hazard_name ?? "—"}</div>
                            </div>
                            <div>
                              <div className="detail-label">Severity</div>
                              <div className="detail-value">
                                <span className={`badge severity-${a.hazard_severity}`}>
                                  {a.hazard_severity}
                                </span>
                              </div>
                            </div>
                            <div>
                              <div className="detail-label">Spans Affected</div>
                              <div className="detail-value">{a.hazard_spans_affected ?? "—"}</div>
                            </div>
                            {a.hazard_latitude != null && a.hazard_longitude != null && (
                              <div>
                                <div className="detail-label">Coordinates</div>
                                <div className="detail-value mono">
                                  <MapPin size={12} strokeWidth={1.5} aria-hidden className="" />{" "}
                                  {a.hazard_latitude.toFixed(2)}°, {a.hazard_longitude.toFixed(2)}°
                                </div>
                              </div>
                            )}
                            {a.hazard_containment_pct != null && (
                              <div>
                                <div className="detail-label">Containment</div>
                                <div className="detail-value">{a.hazard_containment_pct}%</div>
                              </div>
                            )}
                            {a.hazard_last_update && (
                              <div>
                                <div className="detail-label">Last Update</div>
                                <div className="detail-value">
                                  <time dateTime={String(a.hazard_last_update)}>
                                    {new Date(String(a.hazard_last_update)).toLocaleString()}
                                  </time>
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

          {/* BUG-QA-020: Pagination controls (ported from ServiceTable) */}
          {(() => {
            const totalPages = Math.max(1, Math.ceil(actions.length / pageSize));
            const safeCurrentPage = Math.min(page, totalPages);
            return (
              <nav className="pagination-bar" aria-label="Action queue pagination">
                <span>
                  Showing {(safeCurrentPage - 1) * pageSize + 1}–
                  {Math.min(safeCurrentPage * pageSize, actions.length)} of {actions.length}
                </span>
                <div className="page-controls">
                  <label>
                    Rows:
                    <select
                      value={pageSize}
                      onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                      aria-label="Rows per page"
                    >
                      {PAGE_SIZES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </label>
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={safeCurrentPage <= 1}
                    aria-label="Previous page"
                  >
                    ‹ Prev
                  </button>
                  <span>Page {safeCurrentPage} of {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={safeCurrentPage >= totalPages}
                    aria-label="Next page"
                  >
                    Next ›
                  </button>
                </div>
              </nav>
            );
          })()}
        </div>
      )}

      {/* BUG-QA-021 + BUG-DW-074 (WCAG 4.1.3): live regions are ALWAYS mounted (empty when
          no toasts) so assistive tech registers them before content is injected.
          Errors -> role=alert (assertive, persistent until dismissed); success -> role=status (polite). */}
      <div className="toast-stack">
        <div className="toast-container" role="alert" aria-atomic="true">
          {toasts.filter((t) => t.variant === "error").map((t) => (
            <div key={t.id} className={`toast-item ${t.variant}`}>
              <span className="toast-message">{t.message}</span>
              <button
                type="button"
                className="toast-dismiss"
                onClick={() => dismissToast(t.id)}
                aria-label="Dismiss notification"
              >
                <X size={16} strokeWidth={1.5} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
        <div className="toast-container" role="status" aria-live="polite" aria-atomic="true">
          {toasts.filter((t) => t.variant !== "error").map((t) => (
            <div key={t.id} className={`toast-item ${t.variant}`}>
              <span className="toast-message">{t.message}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export function ActionQueueTable() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="error-fallback">
              <p>Failed to load action queue</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <LoadingRegion label="Loading action queue">
                <div className="kpi-row">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-24 w-full rounded-lg" />
                  ))}
                </div>
                <Skeleton className="h-96 w-full rounded-lg" />
              </LoadingRegion>
            }
          >
            <ActionSummaryCards />
            <ActionTableContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
