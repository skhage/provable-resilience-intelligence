/**
 * Lakelink Fiber — Provable Resilience Intelligence
 * Action Queue Route: Proactive actions triggered by risk thresholds
 *
 * Actions are state-managed in Lakebase Postgres:
 * - reroute: redirect traffic via alternate path
 * - dispatch: send field crew to inspect at-risk span
 * - notify: alert customer about potential service impact
 *
 * Status transitions: pending → in_progress → completed | dismissed
 * Header/nav/skip-nav live in __root.tsx (UX-REM-LAYOUT-ROOT).
 */
import { createFileRoute } from "@tanstack/react-router";
import { ActionQueueTable } from "@/components/actions/action-queue-table";

export const Route = createFileRoute("/actions")({
  component: ActionsPage,
});

function ActionsPage() {
  return (
    <section aria-label="Action queue">
      <div className="section-header">
        <h2>Proactive Action Queue</h2>
      </div>
      <p className="text-caption mb-md">
        Actions triggered by resilience risk thresholds. Status persisted in Lakebase.
      </p>
      <ActionQueueTable />
    </section>
  );
}
