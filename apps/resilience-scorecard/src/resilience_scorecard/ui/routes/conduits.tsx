/**
 * Lakelink Fiber — Conduit Coverage (list + map)
 * P35-APP-CONDUIT-COVERAGE-BADGE
 *
 * Reads physical_resource_conduit_v4_candidate (v4 shadow, read-only) via /api/conduits.
 * Default filter: span_coverage_class = REAL_SEGMENTED (55 conduits with real SPAN-* segments).
 * BB_SEGMENTED (92 CDT-BBR-* backbone route conduits carrying synthetic BBS-* segments, DE B2,
 * only 31 distinct geometries per BUG-QA-074) and INVENTORY_ONLY (1,914, no spans) are opt-in
 * and get a coverage badge + legend entry. BB_ONLY (P35 value, superseded by B2) is still
 * rendered if it reappears, and legacy ?coverage=BB_ONLY links map to BB_SEGMENTED.
 * Unknown future classes render with a neutral fallback badge instead of crashing.
 * Coverage is never shown by color alone: every badge has a glyph + text label, and map lines
 * use distinct dash patterns and stroke widths (WCAG 1.4.1, 1.4.11). The table is the accessible
 * alternative to the map.
 * Deep links: /conduits?coverage=BB_SEGMENTED&region=Central
 */
import { Suspense, useMemo, type ReactNode } from "react";
import { createFileRoute, useNavigate, useSearch } from "@tanstack/react-router";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingRegion } from "@/components/ui/loading-region";
import {
  useGetConduitCoverageSummarySuspense,
  useListConduitCoverageSuspense,
  type ConduitCoverage,
  type SpanCoverageClass,
} from "@/lib/api";

type CoverageFilter = SpanCoverageClass | "ALL";

const COVERAGE_FILTERS: readonly CoverageFilter[] = ["REAL_SEGMENTED", "BB_SEGMENTED", "INVENTORY_ONLY", "ALL"];
const REGIONS = ["West", "Central", "East", "Southeast"] as const;
const TABLE_ROW_LIMIT = 200;

export const Route = createFileRoute("/conduits")({
  component: ConduitCoveragePage,
  validateSearch: (search: Record<string, unknown>) => {
    let raw = typeof search.coverage === "string" ? search.coverage.toUpperCase() : "";
    if (raw === "BB_ONLY") raw = "BB_SEGMENTED"; // superseded by DE B2
    const coverage = (COVERAGE_FILTERS as readonly string[]).includes(raw)
      ? (raw as CoverageFilter)
      : "REAL_SEGMENTED";
    const region =
      typeof search.region === "string" && (REGIONS as readonly string[]).includes(search.region)
        ? search.region
        : undefined;
    return { coverage, region };
  },
});

// ---------------------------------------------------------------------------
// Coverage class presentation (Lakelink brand tokens; see lakelink-theme.css .cov-*)
// ---------------------------------------------------------------------------
type CoverageMeta = { label: string; glyph: string; cls: string; description: string; order: number };

const COVERAGE_META: Record<SpanCoverageClass, CoverageMeta> = {
  REAL_SEGMENTED: {
    label: "Real segmented",
    glyph: "\u25CF", // filled circle
    cls: "cov-real",
    description: "Has at least one real fiber span segment. Path evidence is verifiable.",
    order: 3,
  },
  BB_SEGMENTED: {
    label: "Backbone segmented",
    glyph: "\u25D0", // half circle
    cls: "cov-bb",
    description:
      "Backbone route conduit with synthetic segments. Parallel routes share geometry, so they are not independent diversity proof yet.",
    order: 2,
  },
  BB_ONLY: {
    label: "Backbone only (legacy)",
    glyph: "\u25D0",
    cls: "cov-bb",
    description: "Superseded class: synthetic backbone placeholder spans only. Do not use as path proof.",
    order: 1,
  },
  INVENTORY_ONLY: {
    label: "Inventory only",
    glyph: "\u25CB", // empty circle
    cls: "cov-inv",
    description: "Conduit exists in inventory with no spans. No physical path evidence.",
    order: 0,
  },
};

function metaFor(cls: string): CoverageMeta {
  return (
    COVERAGE_META[cls as SpanCoverageClass] ?? {
      label: cls.replace(/_/g, " ").toLowerCase(),
      glyph: "\u25C7", // diamond
      cls: "cov-inv",
      description: "Unrecognized coverage class from the data pipeline.",
      order: -1,
    }
  );
}

const FILTER_LABELS: Record<CoverageFilter, string> = {
  REAL_SEGMENTED: "Real segmented (default)",
  BB_SEGMENTED: "Backbone segmented",
  BB_ONLY: "Backbone only (legacy)",
  INVENTORY_ONLY: "Inventory only",
  ALL: "All coverage classes",
};

// Not exported: route modules export only Route (react-refresh/only-export-components).
function CoverageBadge({ value }: { value: string }) {
  const m = metaFor(value);
  return (
    <span className={`badge coverage-badge ${m.cls}`}>
      <span className="coverage-glyph" aria-hidden="true">{m.glyph}</span> {m.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Legend (counts from /api/conduits/coverage-summary)
// ---------------------------------------------------------------------------
function LineSwatch({ cls }: { cls: string }) {
  return (
    <svg width="36" height="12" aria-hidden="true" focusable="false" className="coverage-swatch">
      <line x1="2" y1="6" x2="34" y2="6" className={`conduit-line ${cls}`} />
    </svg>
  );
}

function CoverageLegend() {
  const { data: summary } = useGetConduitCoverageSummarySuspense({ query: { staleTime: 60_000 } });
  return (
    <ul className="coverage-legend" aria-label="Span coverage legend">
      {summary.classes.map((c) => {
        const m = metaFor(c.span_coverage_class);
        return (
          <li key={c.span_coverage_class} className="coverage-legend-item">
            <LineSwatch cls={m.cls} />
            <CoverageBadge value={c.span_coverage_class} />
            <span className="mono coverage-legend-count">
              {c.conduit_count.toLocaleString()} conduits · {Math.round(c.length_km).toLocaleString()} km
            </span>
            <span className="text-caption">{m.description}</span>
          </li>
        );
      })}
      <li className="coverage-legend-item text-caption">
        Total {summary.total_conduits.toLocaleString()} active conduits · source{" "}
        <span className="mono">{summary.source_table}</span> (v4 shadow)
      </li>
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Map: equirectangular projection of CONUS, A-end to Z-end straight segments
// ---------------------------------------------------------------------------
const MAP_W = 960;
const MAP_H = 500;
const LON_MIN = -125;
const LON_MAX = -66;
const LAT_MIN = 24;
const LAT_MAX = 50;

const projX = (lon: number) => ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * MAP_W;
const projY = (lat: number) => ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * MAP_H;

const hasCoords = (c: ConduitCoverage) =>
  c.lat_a !== null && c.lon_a !== null && c.lat_z !== null && c.lon_z !== null;

// Draw order (metaFor().order): inventory under backbone under real, so verified paths stay on top.

function ConduitMap({ conduits, filterLabel }: { conduits: ConduitCoverage[]; filterLabel: string }) {
  const drawable = useMemo(
    () =>
      conduits
        .filter(hasCoords)
        .sort((a, b) => metaFor(a.span_coverage_class).order - metaFor(b.span_coverage_class).order),
    [conduits],
  );
  const sites = useMemo(() => {
    const m = new Map<string, [number, number]>();
    for (const c of drawable) {
      m.set(`${c.lat_a},${c.lon_a}`, [c.lon_a as number, c.lat_a as number]);
      m.set(`${c.lat_z},${c.lon_z}`, [c.lon_z as number, c.lat_z as number]);
    }
    return [...m.values()];
  }, [drawable]);

  return (
    <div className="conduit-map-card">
      <svg
        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
        className="conduit-map"
        role="img"
        aria-label={`Conduit coverage map, ${filterLabel}: ${drawable.length} conduits drawn. The table below lists the same conduits.`}
      >
        <rect x="0" y="0" width={MAP_W} height={MAP_H} className="conduit-map-bg" />
        {drawable.map((c) => {
          const m = metaFor(c.span_coverage_class);
          return (
            <line
              key={c.conduit_id}
              x1={projX(c.lon_a as number)}
              y1={projY(c.lat_a as number)}
              x2={projX(c.lon_z as number)}
              y2={projY(c.lat_z as number)}
              className={`conduit-line ${m.cls}`}
            >
              <title>{`${c.conduit_id} · ${m.label} · ${c.length_km} km · ${c.coverage_pct}% segmented`}</title>
            </line>
          );
        })}
        {sites.map(([lon, lat]) => (
          <circle key={`${lat},${lon}`} cx={projX(lon)} cy={projY(lat)} r={2.5} className="conduit-map-site" />
        ))}
      </svg>
      {drawable.length < conduits.length && (
        <p className="text-caption">
          {conduits.length - drawable.length} conduit(s) have no site coordinates and are listed in the table only.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------
function ConduitTable({ conduits }: { conduits: ConduitCoverage[] }) {
  const shown = conduits.slice(0, TABLE_ROW_LIMIT);
  if (conduits.length === 0) {
    return (
      <div className="data-table">
        <div className="empty-state">
          <p>No conduits match this filter</p>
          <p className="empty-hint">Try another coverage class or region.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="data-table">
      <table aria-label="Conduits by span coverage">
        <caption className="text-caption coverage-caption">
          Showing {shown.length.toLocaleString()} of {conduits.length.toLocaleString()} conduits, longest first.
        </caption>
        <thead>
          <tr>
            <th scope="col">Conduit</th>
            <th scope="col">Name</th>
            <th scope="col">Region</th>
            <th scope="col">Type</th>
            <th scope="col">Coverage</th>
            <th scope="col" className="num">Length (km)</th>
            <th scope="col" className="num">Segmented (km)</th>
            <th scope="col" className="num">Coverage %</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((c) => (
            <tr key={c.conduit_id}>
              <td className="mono">{c.conduit_id}</td>
              <td>{c.conduit_name ?? "\u2014"}</td>
              <td>{c.region ?? "\u2014"}</td>
              <td>{c.conduit_type ? c.conduit_type.replace(/_/g, " ") : "\u2014"}</td>
              <td>
                <CoverageBadge value={c.span_coverage_class} />
              </td>
              <td className="mono num">{c.length_km.toLocaleString()}</td>
              <td className="mono num">{c.segmented_km.toLocaleString()}</td>
              <td className="mono num">{c.coverage_pct.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConduitListAndMap({ coverage, region }: { coverage: CoverageFilter; region?: string }) {
  const { data: conduits } = useListConduitCoverageSuspense({
    params: { coverage_class: coverage, region },
    query: { staleTime: 60_000 },
  });
  const includesSynthetic = coverage === "BB_SEGMENTED" || coverage === "BB_ONLY" || coverage === "ALL";
  return (
    <>
      {includesSynthetic && (
        <p className="coverage-warning" role="note">
          <span aria-hidden="true">{COVERAGE_META.BB_SEGMENTED.glyph} </span>
          Backbone segmented conduits carry synthetic segments, and parallel backbone routes share the same
          geometry. Treat them as one corridor, not as independent path-diversity proof.
        </p>
      )}
      <ConduitMap conduits={conduits} filterLabel={FILTER_LABELS[coverage]} />
      <ConduitTable conduits={conduits} />
    </>
  );
}

function Boundary({ label, children }: { label: string; children: ReactNode }) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ resetErrorBoundary }) => (
            <div className="data-table error-fallback" role="alert">
              <p>Failed to load {label.toLowerCase()}</p>
              <button className="btn btn-outline" onClick={resetErrorBoundary}>
                Retry
              </button>
            </div>
          )}
        >
          <Suspense
            fallback={
              <LoadingRegion label={`Loading ${label.toLowerCase()}`}>
                <Skeleton className="h-48 w-full rounded-lg" />
              </LoadingRegion>
            }
          >
            {children}
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
function ConduitCoveragePage() {
  const { coverage, region } = useSearch({ from: "/conduits" });
  const navigate = useNavigate({ from: "/conduits" });

  return (
    <>
      <section aria-labelledby="coverage-heading">
        <div className="section-header">
          <div>
            <h2 id="coverage-heading">Conduit Span Coverage</h2>
            <p className="section-subtitle">
              Which Lakelink Fiber conduits have real fiber span evidence. Only real segmented conduits count
              as verified physical paths.
            </p>
          </div>
        </div>
        <Boundary label="Coverage legend">
          <CoverageLegend />
        </Boundary>
      </section>

      <section aria-label="Conduit list and map" className="mt-lg">
        <div className="filter-bar">
          <label htmlFor="coverage-filter" className="filter-label">
            Coverage:
          </label>
          <select
            id="coverage-filter"
            className="filter-select"
            value={coverage}
            onChange={(e) =>
              navigate({ search: (prev) => ({ ...prev, coverage: e.target.value as CoverageFilter }) })
            }
          >
            {COVERAGE_FILTERS.map((f) => (
              <option key={f} value={f}>
                {FILTER_LABELS[f]}
              </option>
            ))}
          </select>
          <label htmlFor="region-filter" className="filter-label">
            Region:
          </label>
          <select
            id="region-filter"
            className="filter-select"
            value={region ?? ""}
            onChange={(e) =>
              navigate({ search: (prev) => ({ ...prev, region: e.target.value || undefined }) })
            }
          >
            <option value="">All regions</option>
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <Boundary label="Conduits">
          <ConduitListAndMap coverage={coverage} region={region} />
        </Boundary>
      </section>
    </>
  );
}
