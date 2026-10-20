/**
 * Lakelink Fiber — Provable Resilience Intelligence
 * Main Dashboard Route: Resilience Scorecard
 *
 * Shows:
 * - KPI header (avg score, risk counts, SPFs, SRLGs)
 * - Per-service resilience table with inline score gauges
 *
 * Header/nav/skip-nav live in __root.tsx (UX-REM-LAYOUT-ROOT).
 */
import { createFileRoute } from "@tanstack/react-router";
import { ScorecardHeader } from "@/components/dashboard/scorecard-header";
import { ServiceTable } from "@/components/dashboard/service-table";

export const Route = createFileRoute("/")({
  component: DashboardPage,
});

function DashboardPage() {
  return (
    <>
      <section aria-label="KPIs">
        <div className="section-header">
          <h2>Service Resilience Scorecard</h2>
        </div>
        <ScorecardHeader />
      </section>

      <section aria-label="Service detail table" className="mt-lg">
        <div className="section-header">
          <h2>Service Detail</h2>
        </div>
        <ServiceTable />
      </section>
    </>
  );
}
