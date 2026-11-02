/**
 * Lakelink Fiber — Provable Resilience Intelligence
 * Action Queue Route: Proactive actions triggered by risk thresholds
 *
 * Actions are state-managed in Lakebase Postgres:
 * - reroute: redirect traffic via alternate path
 * - dispatch: send field crew to inspect at-risk span
 * - notify: alert customer about potential service impact
 *
 * Status transitions: pending → in_progress → completed | cancelled
 * Header/nav/skip-nav live in __root.tsx (UX-REM-LAYOUT-ROOT).
 */
import { createFileRoute } from "@tanstack/react-router";
import { ActionQueueTable } from "@/components/actions/action-queue-table";
import { useCutoverManifest, useV4Kpis } from "@/lib/api";
import {
  PROVISIONAL_NOTE_BODY,
  PROVISIONAL_NOTE_LEAD,
  showProvisionalPageNote,
} from "@/lib/provisional-disclosure";

export const Route = createFileRoute("/actions")({
  component: ActionsPage,
});

function ActionsPage() {
  const v4Kpis = useV4Kpis();
  const manifest = useCutoverManifest();
  const showNote = showProvisionalPageNote(
    v4Kpis, manifest?.provisional_objects ?? [], "actions_page",
  );
  return (
    <section aria-label="Action queue">
      <div className="section-header">
        {/* BUG-DW-122: wrap h2 + note in a plain div (same as hazards.tsx) so the
            flex .section-header does not place the note beside the heading. */}
        <div>
          <h2>Proactive Action Queue</h2>
          {/* P68-APP-PROVISIONAL-BADGE §7.4: page note under the h2 */}
          {showNote && (
            <p role="note" className="provisional-page-note">
              <strong>{PROVISIONAL_NOTE_LEAD}</strong>{PROVISIONAL_NOTE_BODY}
            </p>
          )}
        </div>
      </div>
      <p className="text-caption mb-md">
        Actions triggered by resilience risk thresholds. Status persisted in Lakebase.
      </p>
      <ActionQueueTable />
    </section>
  );
}
