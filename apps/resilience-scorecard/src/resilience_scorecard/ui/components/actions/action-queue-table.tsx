/**
 * Lakelink Fiber — Proactive Action Queue Table
 * Shows pending/in-progress actions with status update buttons.
 * State is persisted in Lakebase Postgres.
 */
import { Suspense, useState, useCallback, useEffect } from "react";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useListActionsSuspense,
  useGetActionSummarySuspense,
  useUpdateActionStatus,
} from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import selector from "@/lib/selector";
import {
  Shuffle,
  Wrench,
  Mail,
  AlertTriangle,
  Scissors,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

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

function ActionSummaryCards() {
  const { data: summary } = useGetActionSummarySuspense(selector());

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
    </div>
  );
}

const PAGE_SIZES = [10, 25, 50, 100] as const;

function ActionTableContent() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(25);
  const [toasts, setToasts] = useState<Array<{ id: number; message: string; variant: string }>>([]);
  const { data: actions } = useListActionsSuspense({
    params: { status_filter: statusFilter },
    ...selector(),
  });
  const queryClient = useQueryClient();

  const addToast = useCallback((message: string, variant = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, []);

  const { mutate: updateStatus, isPending } = useUpdateActionStatus({
    mutation: {
      onSuccess: (_data, variables) => {
        queryClient.invalidateQueries({ queryKey: ["listActions"] });
        queryClient.invalidateQueries({ queryKey: ["getActionSummary"] });
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
        {[undefined, "pending", "in_progress", "completed", "dismissed"].map((s) => (
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
            <div className="empty-icon" aria-hidden="true">✅</div>
            <p>No actions match this filter</p>
            <p className="empty-hint">Try selecting a different status or view all actions.</p>
          </div>
        </div>
      ) : (
        <div className="data-table">
          <table aria-label="Proactive action queue">
            <thead>
              <tr>
                <th>Type</th>
                <th>Service</th>
                <th>Risk Trigger</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Assigned To</th>
                <th>Actions</th>
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
              })().map((a) => (
                <tr key={a.action_id}>
                  <td>
                    <span title={a.action_type} className="action-type-cell">
                      {(() => {
                        const Icon = ACTION_TYPE_ICONS[a.action_type] ?? HelpCircle;
                        return <Icon {...ICON_PROPS} />;
                      })()}
                      {" "}{a.action_type.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="text-medium">{a.service_name}</td>
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
              ))}
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

      {/* BUG-QA-021: Toast notifications — error uses role=alert (assertive), success uses role=status (polite) */}
      {toasts.filter((t) => t.variant === "error").length > 0 && (
        <div className="toast-container" role="alert">
          {toasts.filter((t) => t.variant === "error").map((t) => (
            <div key={t.id} className={`toast-item ${t.variant}`}>
              {t.message}
            </div>
          ))}
        </div>
      )}
      {toasts.filter((t) => t.variant !== "error").length > 0 && (
        <div className="toast-container" role="status" aria-live="polite">
          {toasts.filter((t) => t.variant !== "error").map((t) => (
            <div key={t.id} className={`toast-item ${t.variant}`}>
              {t.message}
            </div>
          ))}
        </div>
      )}
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
            <div style={{ padding: 24 }}>
              <p>Failed to load action queue</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div aria-busy="true" aria-label="Loading action queue">
                <div className="kpi-row">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-24 w-full rounded-lg" />
                  ))}
                </div>
                <Skeleton className="h-96 w-full rounded-lg" />
              </div>
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
