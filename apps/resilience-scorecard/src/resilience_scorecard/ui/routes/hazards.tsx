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
import { useCutoverManifest, useV4Kpis } from "@/lib/api";
import {
  PROVISIONAL_PAGE_NOTE,
  showProvisionalPageNote,
} from "@/lib/provisional-disclosure";

export const Route = createFileRoute("/hazards")({
  component: HazardExposurePage,
});

function HazardExposurePage() {
  const v4Kpis = useV4Kpis();
  const manifest = useCutoverManifest();
  const showNote = showProvisionalPageNote(
    v4Kpis, manifest?.provisional_objects ?? [], "hazards_page",
  );
  return (
    <>
      <section aria-label="Hazard exposure KPIs">
        <div className="section-header">
          <div>
            <h2>Hazard &times; Span Exposure</h2>
            {/* P68-APP-PROVISIONAL-BADGE §7.4: page note under the h2 */}
            {showNote && (
              <p role="note" className="provisional-page-note">
                <strong>Provisional:</strong> hazard exposure on this page uses the v3 hazard model. Topology and conduits use the v4 build.
              </p>
            )}
            <p className="section-subtitle">
              Spatial crosswalk of geographic hazard events intersecting Lakelink Fiber network spans.
              Computed via Haversine great-circle distance with bounding-box pre-filter.
            </p>
          </div>
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
