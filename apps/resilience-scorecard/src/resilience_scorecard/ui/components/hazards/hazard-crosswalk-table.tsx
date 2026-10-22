/**
 * Lakelink Fiber — Hazard × Span Crosswalk Table
 * P10-APP-HAZARD-XWALK-VIEW: Filterable matrix of 79K hazard×span intersections
 *
 * Shows hazard_type × proximity_band breakdown with intersection counts,
 * distinct spans, avg services/span, and avg distance. Filterable by hazard_type.
 * Uses HAZARD-VIS-SPEC badge patterns and HazardTypeCell icons.
 */
import { Suspense, useState, useMemo, useCallback } from "react";
import { QueryErrorResetBoundary, useSuspenseQuery } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { HazardTypeCell } from "./hazard-type-cell";

interface CrosswalkRow {
  hazard_type: string;
  proximity_band: string;
  intersection_count: number;
  distinct_spans: number;
  avg_services_per_span: number;
  avg_distance_km: number;
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
  direct_impact: "Direct Impact (<1km)",
  near_field: "Near Field (1\u20135km)",
  buffer_zone: "Buffer Zone (5\u2013radius km)",
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

function CrosswalkTableContent() {
  const [hazardFilter, setHazardFilter] = useState("");
  const [sortField, setSortField] = useState<SortField>("intersection_count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data: rows } = useCrosswalkData(hazardFilter);

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
    const totalSpans = rows.reduce((s, r) => s + r.distinct_spans, 0);
    const weightedSvc = rows.reduce((s, r) => s + r.avg_services_per_span * r.intersection_count, 0);
    const weightedDist = rows.reduce((s, r) => s + r.avg_distance_km * r.intersection_count, 0);
    return {
      intersection_count: totalIntersections,
      distinct_spans: totalSpans,
      avg_services_per_span: totalIntersections > 0 ? Math.round(weightedSvc / totalIntersections * 10) / 10 : 0,
      avg_distance_km: totalIntersections > 0 ? Math.round(weightedDist / totalIntersections * 100) / 100 : 0,
    };
  }, [rows]);

  const sortIndicator = (field: SortField) =>
    sortField === field ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : "";

  const sortProps = (field: SortField) => ({
    onClick: () => toggleSort(field),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleSort(field);
      }
    },
    tabIndex: 0,
    "aria-sort":
      sortField === field
        ? sortDir === "asc"
          ? ("ascending" as const)
          : ("descending" as const)
        : undefined,
    role: "columnheader" as const,
    style: { cursor: "pointer" } as const,
  });

  if (rows.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <p>No crosswalk data available</p>
          <p className="empty-hint">The hazard\u00d7span intersection pipeline has not run yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="data-table">
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)", marginBottom: "var(--space-md)" }}>
        <label htmlFor="xwalk-hazard-filter" style={{ fontWeight: 500 }}>
          Filter by hazard type:
        </label>
        <select
          id="xwalk-hazard-filter"
          value={hazardFilter}
          onChange={(e) => setHazardFilter(e.target.value)}
          aria-label="Filter crosswalk by hazard type"
          style={{
            padding: "6px 12px",
            borderRadius: "6px",
            border: "1px solid var(--lf-platinum)",
            fontSize: "0.875rem",
          }}
        >
          {HAZARD_TYPES.map((ht) => (
            <option key={ht.value} value={ht.value}>
              {ht.label}
            </option>
          ))}
        </select>
      </div>

      <table aria-label="Hazard span crosswalk matrix">
        <thead>
          <tr>
            <th style={{ width: 150 }}>Hazard Type</th>
            <th style={{ width: 180 }}>Proximity Band</th>
            <th style={{ width: 120 }} {...sortProps("intersection_count")}>
              Intersections{sortIndicator("intersection_count")}
            </th>
            <th style={{ width: 120 }} {...sortProps("distinct_spans")}>
              Spans{sortIndicator("distinct_spans")}
            </th>
            <th style={{ width: 130 }} {...sortProps("avg_services_per_span")}>
              Avg Svc/Span{sortIndicator("avg_services_per_span")}
            </th>
            <th style={{ width: 130 }} {...sortProps("avg_distance_km")}>
              Avg Dist (km){sortIndicator("avg_distance_km")}
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
                <span
                  className={row.proximity_band === "direct_impact" ? "text-medium" : ""}
                  style={
                    row.proximity_band === "direct_impact"
                      ? { color: "var(--lf-risk-red)", fontWeight: 600 }
                      : undefined
                  }
                >
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
              <td className="mono">{totals.distinct_spans.toLocaleString()}</td>
              <td className="mono">{totals.avg_services_per_span.toFixed(1)}</td>
              <td className="mono">{totals.avg_distance_km.toFixed(2)}</td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

export function HazardCrosswalkTable() {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="data-table error-fallback">
              <p>Failed to load crosswalk data</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <div aria-busy="true" aria-label="Loading crosswalk table">
                <Skeleton className="h-96 w-full rounded-lg" />
              </div>
            }
          >
            <CrosswalkTableContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
