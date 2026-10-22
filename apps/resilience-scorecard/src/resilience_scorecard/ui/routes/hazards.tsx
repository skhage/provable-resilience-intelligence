/**
 * Lakelink Fiber — Hazard Exposure (Crosswalk) Route
 * P10-APP-HAZARD-XWALK-VIEW
 *
 * Dedicated page showing the hazard×span intersection crosswalk:
 * - KPI row: total intersections, network exposure %, direct impact count, hazard types
 * - Filterable matrix table: hazard_type × proximity_band breakdown
 * - Sortable columns: intersections, spans, avg services, avg distance
 *
 * Data source: hazard_span_intersection table (79,116 rows, 5 hazard types, 3 bands)
 * Header/nav/skip-nav live in __root.tsx (UX-REM-LAYOUT-ROOT).
 */
import { createFileRoute } from "@tanstack/react-router";
import { HazardCrosswalkKpis, HazardCrosswalkTable } from "@/components/hazards";

export const Route = createFileRoute("/hazards")({
  component: HazardExposurePage,
});

function HazardExposurePage() {
  return (
    <>
      <section aria-label="Hazard exposure KPIs">
        <div className="section-header">
          <h2>Hazard &times; Span Exposure</h2>
          <p style={{ color: "var(--lf-iron)", fontSize: "0.875rem", margin: "4px 0 0" }}>
            Spatial crosswalk of geographic hazard events intersecting Lakelink Fiber network spans.
            Computed via Haversine great-circle distance with bounding-box pre-filter.
          </p>
        </div>
        <HazardCrosswalkKpis />
      </section>

      <section aria-label="Hazard crosswalk matrix" className="mt-lg">
        <div className="section-header">
          <h2>Exposure Matrix</h2>
        </div>
        <HazardCrosswalkTable />
      </section>
    </>
  );
}
