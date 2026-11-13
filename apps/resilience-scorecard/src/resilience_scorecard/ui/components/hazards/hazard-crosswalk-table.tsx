/**
 * Lakelink Fiber — Hazard × Span Crosswalk Table
 * P10-APP-HAZARD-XWALK-VIEW: Filterable matrix of in-radius hazard×span intersections
 * (is_within_radius = TRUE only; P108-APP-HSI-CROSSWALK-IN-RADIUS / BUG-QA-129)
 *
 * Shows hazard_type × proximity_band breakdown with intersection counts,
 * distinct spans, avg services/span, and avg distance. Filterable by hazard_type.
 * Uses HAZARD-VIS-SPEC badge patterns and HazardTypeCell icons.
 */
import { Suspense, useState, useMemo, useCallback, useTransition, useEffect } from "react";
import { QueryErrorResetBoundary, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import { HazardTypeCell } from "./hazard-type-cell";

interface CrosswalkRow {
  hazard_type: string;
  proximity_band: string;
  intersection_count: number;
  distinct_spans: number;
  avg_services_per_span: number;
  avg_distance_km: number;
}

// BUG-DW-164: true (non-additive) totals from /api/hazards/crosswalk/totals.
interface CrosswalkTotals {
  hazard_type: string | null;
  intersection_count: number;
  distinct_spans: number;
}

type SortField = "intersection_count" | "distinct_spans" | "avg_services_per_span" | "avg_distance_km";
type SortDir = "asc" | "desc";

const HAZARD_TYPES = [
  { value: "", label: "All Hazard Types" },
  { value: "severe_weather", label: "Severe Weather" },
  { value: "earthquake", label: "Earthquake" },
  { value: "flood", label: "Flood" },
  { value: "wildfire", label: "Wildfire" },
  { value: "dig_ticket", label: "Dig Ticket" },
] as const;

const BAND_LABELS: Record<string, string> = {
  direct_impact: "Direct Impact (<1 km)",
  near_field: "Near Field (1–5 km)",
  buffer_zone: "Buffer Zone (≥5 km)",
};

const BAND_ORDER: Record<string, number> = {
  direct_impact: 1,
  near_field: 2,
  buffer_zone: 3,
};

const BAND_CLASSES: Record<string, string> = {
  direct_impact: "severity-critical",
  near_field: "severity-major",
  buffer_zone: "severity-moderate",
};

function useCrosswalkData(hazardType: string) {
  return useSuspenseQuery<CrosswalkRow[]>({
    queryKey: ["hazardCrosswalk", hazardType],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (hazardType) params.set("hazard_type", hazardType);
      const url = `/api/hazards/crosswalk${params.toString() ? `?${params}` : ""}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 60_000,
  });
}

// BUG-DW-164: distinct_spans is COUNT(DISTINCT span_id) per bucket, and one span
// can sit in many buckets, so the tfoot must NOT sum it. Fetch the true distinct
// total for the current filter scope instead. Non-suspense so a failure only
// degrades the Spans tfoot cell to an em dash.
function useCrosswalkTotals(hazardType: string) {
  return useQuery<CrosswalkTotals>({
    queryKey: ["hazardCrosswalkTotals", hazardType],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (hazardType) params.set("hazard_type", hazardType);
      const url = `/api/hazards/crosswalk/totals${params.toString() ? `?${params}` : ""}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    staleTime: 60_000,
  });
}

function CrosswalkTableContent({
  hazardFilter,
  isPending,
  filterLabel,
  onStatusChange,
}: {
  hazardFilter: string;
  isPending: boolean;
  filterLabel: string;
  onStatusChange: (text: string) => void;
}) {
  const [sortField, setSortField] = useState<SortField>("intersection_count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data: rows } = useCrosswalkData(hazardFilter);
  const {
    data: trueTotals,
    isError: totalsError,
    isFetching: totalsFetching,
  } = useCrosswalkTotals(hazardFilter);

  // BUG-DW-163 (b): announce row count after data arrives.
  useEffect(() => {
    if (rows.length === 0) {
      onStatusChange("No crosswalk rows.");
    } else {
      const label = hazardFilter ? filterLabel : "all hazard types";
      onStatusChange(
        `Showing ${rows.length.toLocaleString()} rows for ${label}.`,
      );
    }
  }, [rows, hazardFilter, filterLabel, onStatusChange]);

  const toggleSort = useCallback(
    (field: SortField) => {
      if (field === sortField) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDir("desc");
      }
    },
    [sortField],
  );

  const sorted = useMemo(() => {
    const items = [...rows];
    const dir = sortDir === "asc" ? 1 : -1;
    items.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      return (aVal - bVal) * dir;
    });
    return items;
  }, [rows, sortField, sortDir]);

  // Totals row
  const totals = useMemo(() => {
    if (rows.length === 0) return null;
    const totalIntersections = rows.reduce((s, r) => s + r.intersection_count, 0);
    const weightedSvc = rows.reduce((s, r) => s + r.avg_services_per_span * r.intersection_count, 0);
    const weightedDist = rows.reduce((s, r) => s + r.avg_distance_km * r.intersection_count, 0);
    return {
      intersection_count: totalIntersections,
      // BUG-DW-164: true distinct total from the backend, or null (em dash). Never a sum.
      distinct_spans: typeof trueTotals?.distinct_spans === "number" ? trueTotals.distinct_spans : null,
      avg_services_per_span: totalIntersections > 0 ? Math.round(weightedSvc / totalIntersections * 10) / 10 : 0,
      avg_distance_km: totalIntersections > 0 ? Math.round(weightedDist / totalIntersections * 100) / 100 : 0,
    };
  }, [rows, trueTotals]);

  const sortIndicator = (field: SortField) =>
    sortField === field ? (sortDir === "asc" ? " ▲" : " ▼") : "";

  // BUG-DW-147 (WCAG 4.1.2): APG sortable-table pattern. The th only carries
  // aria-sort; sortButton() renders the operable native button inside it.
  const sortProps = (field: SortField) => ({
    "aria-sort":
      sortField === field
        ? sortDir === "asc"
          ? ("ascending" as const)
          : ("descending" as const)
        : undefined,
  });

  const sortButton = (field: SortField, label: string) => (
    <button type="button" className="th-sort-button" onClick={() => toggleSort(field)}>
      {label}
      <span aria-hidden="true">{sortIndicator(field)}</span>
    </button>
  );

  if (rows.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <p>No crosswalk data available</p>
          <p className="empty-hint">Hazard exposure data is not available yet.</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* BUG-DW-150 (WCAG 2.1.1/1.4.10): scroll-region pattern for keyboard access */}
      <p className="text-caption table-scroll-hint" aria-hidden="true">
        Scroll for more columns →
      </p>
      <div
        className="data-table table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Hazard span crosswalk matrix, scrolls horizontally"
        aria-busy={isPending}
      >
      <table aria-label="Hazard span crosswalk matrix">
        <thead>
          <tr>
            <th style={{ width: 150 }}>Hazard Type</th>
            <th style={{ width: 180 }}>Proximity Band</th>
            <th style={{ width: 120 }} {...sortProps("intersection_count")}>
              {sortButton("intersection_count", "Intersections")}
            </th>
            <th style={{ width: 120 }} {...sortProps("distinct_spans")}>
              {sortButton("distinct_spans", "Spans")}
            </th>
            <th style={{ width: 130 }} {...sortProps("avg_services_per_span")}>
              {sortButton("avg_services_per_span", "Avg Svc/Span")}
            </th>
            <th style={{ width: 130 }} {...sortProps("avg_distance_km")}>
              {sortButton("avg_distance_km", "Avg Dist (km)")}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={`${row.hazard_type}-${row.proximity_band}`}>
              <td>
                <span className={`badge ${row.hazard_type}`}>
                  <HazardTypeCell type={row.hazard_type} />
                </span>
              </td>
              <td>
                <span className={`badge ${BAND_CLASSES[row.proximity_band] ?? ""}`}>
                  {BAND_LABELS[row.proximity_band] ?? row.proximity_band}
                </span>
              </td>
              <td className="mono">
                {/* BUG-DW-172: same 4.06:1 zebra-row failure as hazard-summary-table; use the AA-safe dark risk-red class */}
                <span className={row.proximity_band === "direct_impact" ? "text-risk-strong text-semibold" : ""}>
                  {row.intersection_count.toLocaleString()}
                </span>
              </td>
              <td className="mono">{row.distinct_spans.toLocaleString()}</td>
              <td className="mono">{row.avg_services_per_span.toFixed(1)}</td>
              <td className="mono">{row.avg_distance_km.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr style={{ fontWeight: 700, borderTop: "2px solid var(--lf-dark-teal)" }}>
              <td colSpan={2}>Total / Weighted Avg</td>
              <td className="mono">{totals.intersection_count.toLocaleString()}</td>
              {/* BUG-DW-166: three honest states. Value when present; "Loading" while the
                  totals query is in flight with no value; "unavailable" ONLY on isError. */}
              <td className="mono" aria-busy={totalsFetching}>
                {totals.distinct_spans !== null ? (
                  <>
                    {totals.distinct_spans.toLocaleString()}
                    <span className="sr-only"> distinct spans, not a sum of rows</span>
                  </>
                ) : totalsError || !totalsFetching ? (
                  <>
                    <span aria-hidden="true">—</span>
                    <span className="sr-only">Distinct span total unavailable; per-row span counts are not additive</span>
                  </>
                ) : (
                  <>
                    <Skeleton className="tfoot-total-skeleton" aria-hidden="true" style={{ display: "inline-block", width: 48, height: 14 }} />
                    <span className="sr-only">Loading distinct span total</span>
                  </>
                )}
              </td>
              <td className="mono">{totals.avg_services_per_span.toFixed(1)}</td>
              <td className="mono">{totals.avg_distance_km.toFixed(2)}</td>
            </tr>
          </tfoot>
        )}
      </table>
      </div>
    </>
  );
}

/**
 * BUG-DW-163 (WCAG 2.4.3 / 3.2.2 / 4.1.3): The filter <select> and the
 * live-region status text live ABOVE the Suspense boundary so they are never
 * unmounted by a suspension.  Filter changes are wrapped in startTransition,
 * which keeps the previous table mounted (with aria-busy) while the new data
 * loads.  requestedFilter gives immediate visual feedback in the <select>;
 * committedFilter is what the query actually uses.
 */
export function HazardCrosswalkTable() {
  // Filter state lives above Suspense so the <select> is never unmounted.
  const [committedFilter, setCommittedFilter] = useState("");
  const [requestedFilter, setRequestedFilter] = useState("");
  const [isPending, startTransition] = useTransition();
  // BUG-DW-163 (b): live-region row count, updated by CrosswalkTableContent.
  const [statusText, setStatusText] = useState("");

  const changeFilter = useCallback((value: string) => {
    // Immediate: update the <select> value so the user sees their choice.
    setRequestedFilter(value);
    // Deferred: update the committed filter inside a transition so React
    // keeps the current table mounted instead of swapping in the skeleton.
    startTransition(() => {
      setCommittedFilter(value);
    });
  }, []);

  const filterLabel = HAZARD_TYPES.find((h) => h.value === requestedFilter)?.label ?? "All Hazard Types";

  return (
    <>
      {/* BUG-DW-163 (a): filter bar is above Suspense so it never unmounts */}
      <div className="filter-bar">
        <label htmlFor="xwalk-hazard-filter" className="filter-label">
          Filter by hazard type:
        </label>
        <select
          id="xwalk-hazard-filter"
          value={requestedFilter}
          onChange={(e) => changeFilter(e.target.value)}
          // BUG-DW-094 (WCAG 2.5.3 Label in Name): no aria-label here; the
          // accessible name comes from the visible <label htmlFor>.
          className="filter-select"
        >
          {HAZARD_TYPES.map((ht) => (
            <option key={ht.value} value={ht.value}>
              {ht.label}
            </option>
          ))}
        </select>
      </div>

      {/* BUG-DW-163 (b): polite live region announces row count after load */}
      <div role="status" className="sr-only">
        {statusText}
      </div>

      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <div className="data-table error-fallback" role="alert">
                <p>Failed to load crosswalk data</p>
                <button className="btn btn-outline" onClick={resetErrorBoundary}>
                  Retry
                </button>
              </div>
            )}
          >
            <Suspense
              fallback={
                <LoadingRegion label="Loading crosswalk table">
                  <Skeleton className="h-96 w-full rounded-lg" />
                </LoadingRegion>
              }
            >
              <CrosswalkTableContent
                hazardFilter={committedFilter}
                isPending={isPending}
                filterLabel={filterLabel}
                onStatusChange={setStatusText}
              />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </>
  );
}
