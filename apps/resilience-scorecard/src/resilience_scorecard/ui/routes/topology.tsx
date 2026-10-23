/**
 * Lakelink Fiber — Network Topology Graph View
 * TOPOLOGY-VIS-SPEC §9.1, §13 (phases 13a–13e)
 *
 * Region-level aggregation (4 regions) with drill-in to site-level nodes
 * and conduit edges. Service path trace with diversity coloring (§2),
 * SRLG overlay with pulsing glow (§3), hazard overlay (§4),
 * edge detail panel (§5.2), cross-view navigation (§9.2).
 */
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { createFileRoute, useNavigate, useSearch, Link } from "@tanstack/react-router";

// ---------------------------------------------------------------------------
// Route definition
// ---------------------------------------------------------------------------

export const Route = createFileRoute("/topology")({
  component: TopologyPage,
  validateSearch: (search: Record<string, unknown>) => ({
    service: (search.service as string) ?? undefined,
    hazard: (search.hazard as string) ?? undefined,
  }),
});

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RegionSummary {
  region: string;
  site_count: number;
  tier_1_count: number;
  tier_2_count: number;
  tier_3_count: number;
  co_count: number;
  dc_count: number;
  conduit_count: number;
  span_count: number;
}

interface SiteNode {
  site_id: string;
  site_name: string;
  site_type: string;
  clli_code: string | null;
  latitude: number;
  longitude: number;
  city: string;
  state: string;
  region: string;
  tier: string | null;
  conduit_count: number;
}

interface ConduitEdge {
  conduit_id: string;
  conduit_name: string | null;
  corridor: string | null;
  conduit_type: string;
  length_km: number;
  site_a_id: string;
  site_z_id: string;
  span_count: number;
}

interface Overlays {
  diversity: boolean;
  srlg: boolean;
  hazard: boolean;
}

interface PathHop {
  service_id: string;
  hop_index: number;
  span_id: string;
  path_type: string;
  conduit_id: string | null;
  span_site_a_id: string;
  span_site_z_id: string;
  span_length_km: number;
  fiber_type: string | null;
  strand_count: number;
  conduit_type: string | null;
  conduit_length_km: number;
  corridor: string | null;
  site_a_name: string | null;
  site_z_name: string | null;
}

interface ServiceDiversity {
  service_id: string;
  diversity_status: string;
  working_hops: number;
  protect_hops: number;
  shared_srlg_count: number;
}

interface SrlgMember {
  srlg_id: string;
  srlg_type: string;
  severity: string | null;
  span_id: string;
  description: string | null;
  site_a_id: string;
  site_z_id: string;
  conduit_id: string | null;
  span_length_km: number;
  site_a_name: string | null;
  site_z_name: string | null;
}

interface HazardOverlay {
  hazard_id: string;
  hazard_type: string;
  name: string;
  severity: string;
  latitude: number;
  longitude: number;
  direct_impact_spans: number;
  near_impact_spans: number;
  advisory_spans: number;
}

// SRLG type icons per §3.1
const SRLG_ICONS: Record<string, string> = {
  shared_conduit: "⛓️",
  bridge: "🌉",
  rail_crossing: "🚂",
  power_feed: "⚡",
  tunnel: "🛤️",
  central_office: "🏢",
};

const SRLG_COLORS: Record<string, string> = {
  shared_conduit: "#4D4D4D",
  bridge: "#D97706",
  rail_crossing: "#D97706",
  power_feed: "#F26522",
  tunnel: "#4D4D4D",
  central_office: "#D32F2F",
};

// Hazard type icons per HAZARD-VIS-SPEC §1
const HAZARD_ICONS: Record<string, string> = {
  wildfire: "🔥",
  flood: "🌊",
  severe_weather: "⛈️",
  earthquake: "🌍",
  dig_ticket: "🚧",
};

// Diversity colors per §2.1
const DIVERSITY_COLORS: Record<string, string> = {
  fully_diverse: "#16A34A",
  partially_diverse: "#D97706",
  single_path: "#DC2626",
  unknown: "#9CA3AF",
};

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const CANVAS_W = 1200;
const CANVAS_H = 600;
const REGION_W = 220;
const REGION_H = 140;
const REGION_SPACING = 60;
const NODE_RADIUS_T1 = 20;
const NODE_RADIUS_T2 = 14;
const BRAND = {
  darkTeal: "#006272",
  platinum: "#E8E8E8",
  iron: "#4D4D4D",
  orange: "#F26522",
  white: "#FFFFFF",
  riskRed: "#D32F2F",
  riskGreen: "#2E7D32",
};

// Region layout positions (left-to-right: West → Central → East → Southeast)
const REGION_ORDER = ["West", "Central", "East", "Southeast"];
const regionPos = (idx: number) => ({
  x: 80 + idx * (REGION_W + REGION_SPACING),
  y: (CANVAS_H - REGION_H) / 2,
});

// ---------------------------------------------------------------------------
// Toolbar component (§7)
// ---------------------------------------------------------------------------

function Toolbar({
  overlays,
  onToggle,
  onFit,
  onZoomIn,
  onZoomOut,
  selectedRegion,
  onBack,
}: {
  overlays: Overlays;
  onToggle: (key: keyof Overlays) => void;
  onFit: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  selectedRegion: string | null;
  onBack: () => void;
}) {
  return (
    <div className="topo-toolbar" role="toolbar" aria-label="Graph controls">
      {selectedRegion && (
        <div className="topo-breadcrumb">
          <button onClick={onBack} aria-label="Back to all regions">
            All Regions
          </button>
          <span className="separator" aria-hidden="true">
            ›
          </span>
          <span style={{ fontWeight: 600 }}>{selectedRegion}</span>
        </div>
      )}
      <div className="topo-btn-group">
        <button onClick={onFit} aria-label="Fit graph to viewport" title="Fit (F)">
          ⊞
        </button>
        <button onClick={onZoomIn} aria-label="Zoom in" title="Zoom in (+)">
          +
        </button>
        <button onClick={onZoomOut} aria-label="Zoom out" title="Zoom out (−)">
          −
        </button>
      </div>
      <div className="topo-divider" aria-hidden="true" />
      <button
        className="topo-toggle"
        role="switch"
        aria-checked={overlays.diversity}
        onClick={() => onToggle("diversity")}
        title="Toggle diversity overlay (D)"
      >
        <span className="toggle-dot" aria-hidden="true" />
        Diversity
      </button>
      <button
        className="topo-toggle"
        role="switch"
        aria-checked={overlays.srlg}
        onClick={() => onToggle("srlg")}
        title="Toggle SRLG overlay (S)"
      >
        <span className="toggle-dot" aria-hidden="true" />
        SRLGs
      </button>
      <button
        className="topo-toggle"
        role="switch"
        aria-checked={overlays.hazard}
        onClick={() => onToggle("hazard")}
        title="Toggle hazard overlay (H)"
      >
        <span className="toggle-dot" aria-hidden="true" />
        Hazards
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend component (§8)
// ---------------------------------------------------------------------------

function Legend({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  if (collapsed) {
    return (
      <div className="topo-legend" role="region" aria-label="Graph legend">
        <button className="topo-legend-collapse-btn" onClick={onToggle}>
          Legend ▾
        </button>
      </div>
    );
  }

  return (
    <div className="topo-legend" role="region" aria-label="Graph legend">
      <h4>Legend</h4>

      <div className="legend-section">
        <div className="legend-section-title">Nodes</div>
        <div className="legend-item">
          <svg width="14" height="14">
            <circle cx="7" cy="7" r="6" fill="none" stroke={BRAND.darkTeal} strokeWidth="2" />
          </svg>
          Backbone Site (tier_1)
        </div>
        <div className="legend-item">
          <svg width="14" height="14">
            <circle cx="7" cy="7" r="5" fill="none" stroke={BRAND.darkTeal} strokeWidth="1.5" />
          </svg>
          Regional Site (tier_2)
        </div>
      </div>

      <div className="legend-section">
        <div className="legend-section-title">Edges</div>
        <div className="legend-item">
          <div className="legend-line" style={{ background: BRAND.darkTeal }} />
          Conduit
        </div>
      </div>

      <div className="legend-section">
        <div className="legend-section-title">Diversity</div>
        {[
          { color: "#16A34A", label: "Fully Diverse" },
          { color: "#D97706", label: "Partially Diverse" },
          { color: "#DC2626", label: "Single Path" },
          { color: "#9CA3AF", label: "Unknown" },
        ].map((d) => (
          <div key={d.label} className="legend-item">
            <span className="legend-swatch" style={{ background: d.color }} />
            {d.label}
          </div>
        ))}
      </div>

      <button className="topo-legend-collapse-btn" onClick={onToggle}>
        Collapse ▴
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Site Detail Panel (§5.1)
// ---------------------------------------------------------------------------

function SiteDetailPanel({
  site,
  conduits,
  onClose,
}: {
  site: SiteNode;
  conduits: ConduitEdge[];
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = panelRef.current;
    if (el) {
      const close = el.querySelector<HTMLElement>(".panel-close");
      close?.focus();
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const connected = conduits.filter(
    (c) => c.site_a_id === site.site_id || c.site_z_id === site.site_id
  );

  return (
    <div
      ref={panelRef}
      className="topo-detail-panel"
      role="dialog"
      aria-label={`Site detail: ${site.site_name}`}
    >
      <div className="panel-header">
        <h3>
          <span className="mono">{site.site_id}</span> · {site.site_name}
        </h3>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">
          ✕
        </button>
      </div>
      <div className="panel-body">
        <div className="detail-row">
          <span className="detail-label">Type</span>
          <span>{site.site_type.replace(/_/g, " ")}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Tier</span>
          <span>{site.tier ?? "—"}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">CLLI</span>
          <span className="mono">{site.clli_code ?? "—"}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Location</span>
          <span>
            {site.city}, {site.state}
          </span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Region</span>
          <span>{site.region}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Coordinates</span>
          <span className="mono">
            {site.latitude.toFixed(4)}°N, {Math.abs(site.longitude).toFixed(4)}°W
          </span>
        </div>

        <h4 className="panel-section-title">
          Connected Conduits ({connected.length})
        </h4>
        {connected.map((c) => (
          <div key={c.conduit_id} className="panel-conduit-item">
            <div className="conduit-name">
              <span className="mono">{c.conduit_id}</span>
            </div>
            <div className="conduit-meta">
              {c.conduit_type.replace(/_/g, " ")} · {c.length_km} km · {c.span_count} spans
              {c.corridor ? ` · ${c.corridor}` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edge Detail Panel (§5.2)
// ---------------------------------------------------------------------------

function EdgeDetailPanel({
  conduit,
  srlgs,
  hazards,
  onClose,
}: {
  conduit: ConduitEdge;
  srlgs: SrlgMember[];
  hazards: HazardOverlay[];
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = panelRef.current;
    if (el) {
      const close = el.querySelector<HTMLElement>(".panel-close");
      close?.focus();
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  // SRLGs touching this conduit
  const conduitSrlgs = srlgs.filter((s) => s.conduit_id === conduit.conduit_id);
  // Unique SRLG groups
  const srlgGroups = Array.from(
    new Map(conduitSrlgs.map((s) => [s.srlg_id, s])).values()
  );

  return (
    <div
      ref={panelRef}
      className="topo-detail-panel"
      role="dialog"
      aria-label={`Conduit detail: ${conduit.conduit_id}`}
    >
      <div className="panel-header">
        <h3>
          <span className="mono">{conduit.conduit_id}</span>
          {conduit.conduit_name ? ` \u00b7 ${conduit.conduit_name}` : ""}
        </h3>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">
          \u2715
        </button>
      </div>
      <div className="panel-body">
        <div className="detail-row">
          <span className="detail-label">Type</span>
          <span>{conduit.conduit_type.replace(/_/g, " ")}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Length</span>
          <span>{conduit.length_km} km</span>
        </div>
        {conduit.corridor && (
          <div className="detail-row">
            <span className="detail-label">Corridor</span>
            <span>{conduit.corridor}</span>
          </div>
        )}
        <div className="detail-row">
          <span className="detail-label">Spans</span>
          <span>{conduit.span_count}</span>
        </div>

        {srlgGroups.length > 0 && (
          <>
            <h4 className="panel-section-title">
              Shared Risk Groups ({srlgGroups.length})
            </h4>
            {srlgGroups.map((s) => (
              <div key={s.srlg_id} className="panel-conduit-item">
                <div className="conduit-name">
                  <span style={{ marginRight: 6 }}>
                    {SRLG_ICONS[s.srlg_type] ?? "\u26a0\ufe0f"}
                  </span>
                  <span className="mono">{s.srlg_id}</span>
                  {s.severity && (
                    <span
                      className="srlg-severity-badge"
                      data-severity={s.severity}
                    >
                      {s.severity.toUpperCase()}
                    </span>
                  )}
                </div>
                <div className="conduit-meta">
                  {s.srlg_type.replace(/_/g, " ")}
                  {s.description ? ` \u2014 ${s.description}` : ""}
                </div>
              </div>
            ))}
          </>
        )}

        {hazards.length > 0 && (
          <>
            <h4 className="panel-section-title">Hazard Exposure</h4>
            {hazards.map((h) => (
              <div key={h.hazard_id} className="panel-conduit-item">
                <div className="conduit-name">
                  <span style={{ marginRight: 6 }}>
                    {HAZARD_ICONS[h.hazard_type] ?? "\u26a0\ufe0f"}
                  </span>
                  {h.name}
                </div>
                <div className="conduit-meta">
                  {h.severity} \u00b7 {h.direct_impact_spans} direct impact spans
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Service Path Info Banner (§2 — shows when a service is traced)
// ---------------------------------------------------------------------------

function PathTraceBanner({
  serviceId,
  diversity,
  hops,
  onClear,
}: {
  serviceId: string;
  diversity: ServiceDiversity | null;
  hops: PathHop[];
  onClear: () => void;
}) {
  const workingHops = hops.filter((h) => h.path_type === "working");
  const protectHops = hops.filter((h) => h.path_type === "protect");
  const divColor = diversity
    ? DIVERSITY_COLORS[diversity.diversity_status] ?? DIVERSITY_COLORS.unknown
    : DIVERSITY_COLORS.unknown;
  const divLabel = diversity
    ? diversity.diversity_status.replace(/_/g, " ")
    : "unknown";

  return (
    <div className="path-trace-banner" role="status" aria-live="polite">
      <div className="path-trace-info">
        <span
          className="diversity-badge"
          style={{ background: divColor + "22", color: divColor, borderColor: divColor }}
        >
          {divLabel}
        </span>
        <span className="mono" style={{ fontWeight: 600 }}>
          {serviceId}
        </span>
        <span className="path-trace-stats">
          {workingHops.length} working hops
          {protectHops.length > 0 ? ` \u00b7 ${protectHops.length} protect hops` : " \u00b7 no protect path"}
          {diversity && diversity.shared_srlg_count > 0
            ? ` \u00b7 ${diversity.shared_srlg_count} shared SRLGs`
            : ""}
        </span>
      </div>
      <div className="path-trace-actions">
        <Link
          to="/"
          search={{ service: serviceId }}
          className="path-trace-link"
        >
          View in Service Table \u2192
        </Link>
        <button className="path-trace-clear" onClick={onClear}>
          \u2715 Clear trace
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Region-Level Graph (default view — §1.2, §10.1)
// ---------------------------------------------------------------------------

function RegionGraph({
  regions,
  onDrillIn,
}: {
  regions: RegionSummary[];
  onDrillIn: (region: string) => void;
}) {
  const sorted = REGION_ORDER.map((name) => regions.find((r) => r.region === name)).filter(
    Boolean
  ) as RegionSummary[];

  // Inter-region links (adjacent pairs)
  const links = [
    [0, 1],
    [1, 2],
    [2, 3],
    [1, 3],
  ];

  const totalSites = regions.reduce((s, r) => s + r.site_count, 0);
  const totalConduits = regions.reduce((s, r) => s + r.conduit_count, 0);

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      role="img"
      aria-label={`Network topology overview: ${totalSites} sites, ${totalConduits} conduits across ${sorted.length} regions`}
      style={{ width: "100%", height: "100%", minHeight: 500 }}
    >
      {/* Inter-region links */}
      {links.map(([a, b]) => {
        if (!sorted[a] || !sorted[b]) return null;
        const pa = regionPos(a);
        const pb = regionPos(b);
        return (
          <line
            key={`link-${a}-${b}`}
            x1={pa.x + REGION_W / 2}
            y1={pa.y + REGION_H / 2}
            x2={pb.x + REGION_W / 2}
            y2={pb.y + REGION_H / 2}
            className="topo-edge"
            strokeWidth={2}
            strokeDasharray="8,4"
            opacity={0.3}
          />
        );
      })}

      {/* Region nodes */}
      {sorted.map((r, i) => {
        const pos = regionPos(i);
        return (
          <g
            key={r.region}
            className="topo-region-node"
            tabIndex={0}
            role="button"
            aria-label={`${r.region} region: ${r.site_count} sites, ${r.conduit_count} conduits. Press Enter to drill in.`}
            onClick={() => onDrillIn(r.region)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onDrillIn(r.region);
              }
            }}
          >
            <rect
              x={pos.x}
              y={pos.y}
              width={REGION_W}
              height={REGION_H}
              rx={12}
              ry={12}
              fill={BRAND.white}
              stroke={BRAND.darkTeal}
              strokeWidth={2}
            />
            {/* Globe icon placeholder */}
            <text
              x={pos.x + 16}
              y={pos.y + 28}
              fontSize={16}
              fill={BRAND.darkTeal}
              fontWeight={700}
              fontFamily="'Inter', sans-serif"
            >
              {r.region}
            </text>
            <text
              x={pos.x + 16}
              y={pos.y + 50}
              fontSize={12}
              fill={BRAND.iron}
              fontFamily="'Inter', sans-serif"
            >
              {r.site_count} sites · {r.co_count} COs · {r.dc_count} DCs
            </text>
            <text
              x={pos.x + 16}
              y={pos.y + 68}
              fontSize={12}
              fill={BRAND.iron}
              fontFamily="'Inter', sans-serif"
            >
              {r.conduit_count} conduits · {r.span_count} spans
            </text>
            <text
              x={pos.x + 16}
              y={pos.y + 90}
              fontSize={11}
              fill={BRAND.iron}
              fontFamily="'Inter', sans-serif"
            >
              T1: {r.tier_1_count} · T2: {r.tier_2_count} · T3: {r.tier_3_count}
            </text>
            {/* Drill-in hint */}
            <text
              x={pos.x + REGION_W / 2}
              y={pos.y + REGION_H - 12}
              textAnchor="middle"
              fontSize={11}
              fill={BRAND.darkTeal}
              fontWeight={600}
              fontFamily="'Inter', sans-serif"
            >
              Click to explore →
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Site-Level Graph (drill-in view — §1.2, §10.2)
// ---------------------------------------------------------------------------

function layoutSites(sites: SiteNode[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const t1 = sites.filter((s) => s.tier === "tier_1");
  const t2 = sites.filter((s) => s.tier === "tier_2");

  // Tier 1 top row
  const t1Spacing = Math.max(60, (CANVAS_W - 100) / Math.max(t1.length, 1));
  t1.forEach((s, i) => {
    positions.set(s.site_id, {
      x: 50 + i * t1Spacing + t1Spacing / 2,
      y: 120,
    });
  });

  // Tier 2 bottom row
  const t2Spacing = Math.max(50, (CANVAS_W - 100) / Math.max(t2.length, 1));
  t2.forEach((s, i) => {
    positions.set(s.site_id, {
      x: 50 + i * t2Spacing + t2Spacing / 2,
      y: 380,
    });
  });

  return positions;
}

function SiteGraph({
  sites,
  conduits,
  onSelectSite,
  selectedSiteId,
  onSelectConduit,
  selectedConduitId,
  pathHops,
  srlgs,
  hazards,
  overlays,
  diversity,
}: {
  sites: SiteNode[];
  conduits: ConduitEdge[];
  onSelectSite: (site: SiteNode | null) => void;
  selectedSiteId: string | null;
  onSelectConduit: (conduit: ConduitEdge | null) => void;
  selectedConduitId: string | null;
  pathHops: PathHop[];
  srlgs: SrlgMember[];
  hazards: HazardOverlay[];
  overlays: Overlays;
  diversity: ServiceDiversity | null;
}) {
  // Build lookup sets for path trace
  const pathSiteIds = useMemo(() => {
    const ids = new Set<string>();
    pathHops.forEach((h) => {
      ids.add(h.span_site_a_id);
      ids.add(h.span_site_z_id);
    });
    return ids;
  }, [pathHops]);

  const pathConduitIds = useMemo(() => {
    const ids = new Set<string>();
    pathHops.forEach((h) => {
      if (h.conduit_id) ids.add(h.conduit_id);
    });
    return ids;
  }, [pathHops]);

  // Build SRLG lookup: conduit_id -> set of srlg_ids
  const srlgByConduit = useMemo(() => {
    const map = new Map<string, Set<string>>();
    srlgs.forEach((s) => {
      if (s.conduit_id) {
        if (!map.has(s.conduit_id)) map.set(s.conduit_id, new Set());
        map.get(s.conduit_id)!.add(s.srlg_id);
      }
    });
    return map;
  }, [srlgs]);

  const hasPathTrace = pathHops.length > 0;
  const divColor = diversity
    ? DIVERSITY_COLORS[diversity.diversity_status] ?? BRAND.darkTeal
    : BRAND.darkTeal;
  const positions = useMemo(() => layoutSites(sites), [sites]);

  const totalSites = sites.length;
  const t1Count = sites.filter((s) => s.tier === "tier_1").length;
  const t2Count = sites.filter((s) => s.tier === "tier_2").length;
  const regionName = sites[0]?.region ?? "Region";

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      role="img"
      aria-label={`${regionName} topology: ${totalSites} sites (${t1Count} backbone, ${t2Count} regional), ${conduits.length} conduits`}
      style={{ width: "100%", height: "100%", minHeight: 500 }}
    >
      {/* Layer labels */}
      <text x={20} y={80} fontSize={11} fill={BRAND.iron} fontWeight={600} fontFamily="'Inter', sans-serif">
        BACKBONE (TIER 1)
      </text>
      <text x={20} y={340} fontSize={11} fill={BRAND.iron} fontWeight={600} fontFamily="'Inter', sans-serif">
        REGIONAL (TIER 2)
      </text>

      {/* Conduit edges — enhanced with path trace, SRLG, hazard overlays */}
      {conduits.map((c) => {
        const pa = positions.get(c.site_a_id);
        const pz = positions.get(c.site_z_id);
        if (!pa || !pz) return null;

        const isOnPath = hasPathTrace && pathConduitIds.has(c.conduit_id);
        const hasSrlg = overlays.srlg && srlgByConduit.has(c.conduit_id);
        const isSelected = selectedConduitId === c.conduit_id;

        // Determine working vs protect for this conduit in the trace
        const conduitHops = pathHops.filter((h) => h.conduit_id === c.conduit_id);
        const hasWorking = conduitHops.some((h) => h.path_type === "working");
        const hasProtect = conduitHops.some((h) => h.path_type === "protect");

        // Color priority: Hazard > SRLG > Diversity > Default
        let edgeColor = BRAND.darkTeal;
        let edgeOpacity = hasPathTrace ? (isOnPath ? 1 : 0.15) : 0.5;
        let dashArray: string | undefined = undefined;
        let glowClass = "";

        if (isOnPath && overlays.diversity) {
          edgeColor = divColor;
        }
        if (hasSrlg) {
          const firstSrlg = srlgs.find((s) => s.conduit_id === c.conduit_id);
          if (firstSrlg) {
            edgeColor = SRLG_COLORS[firstSrlg.srlg_type] ?? BRAND.iron;
            glowClass = firstSrlg.severity === "critical" ? "srlg-highlight srlg-critical" : "srlg-highlight";
          }
          edgeOpacity = 1;
        }
        if (isOnPath && hasProtect && !hasWorking) {
          dashArray = "8,4";
        }

        return (
          <line
            key={c.conduit_id}
            x1={pa.x}
            y1={pa.y}
            x2={pz.x}
            y2={pz.y}
            className={`topo-edge topo-edge-clickable ${glowClass}`}
            stroke={isSelected ? BRAND.orange : edgeColor}
            strokeWidth={isOnPath ? 3 : Math.min(1 + c.span_count / 3, 5)}
            strokeDasharray={dashArray}
            opacity={edgeOpacity}
            style={hasSrlg ? { ["--srlg-color" as string]: edgeColor } : undefined}
            tabIndex={0}
            role="button"
            aria-label={`Conduit ${c.conduit_id}: ${c.conduit_type}, ${c.length_km} km, ${c.span_count} spans${hasSrlg ? " (SRLG member)" : ""}. Press Enter for details.`}
            onClick={() => onSelectConduit(isSelected ? null : c)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectConduit(isSelected ? null : c);
              }
            }}
          >
            <title>
              {c.conduit_id}: {c.conduit_type} \u00b7 {c.length_km} km \u00b7 {c.span_count} spans
            </title>
          </line>
        );
      })}

      {/* Site nodes — with path trace highlighting */}
      {sites.map((s) => {
        const p = positions.get(s.site_id);
        if (!p) return null;
        const isT1 = s.tier === "tier_1";
        const r = isT1 ? NODE_RADIUS_T1 : NODE_RADIUS_T2;
        const isSelected = selectedSiteId === s.site_id;
        const isOnPath = hasPathTrace && pathSiteIds.has(s.site_id);
        const dimmed = hasPathTrace && !isOnPath;

        // Node stroke: selected orange > on-path diversity color > default teal
        let nodeStroke = BRAND.darkTeal;
        let nodeStrokeWidth = 2;
        if (isSelected) {
          nodeStroke = BRAND.orange;
          nodeStrokeWidth = 3;
        } else if (isOnPath && overlays.diversity) {
          nodeStroke = divColor;
          nodeStrokeWidth = 3;
        }

        return (
          <g
            key={s.site_id}
            className={`topo-site-node${dimmed ? " topo-dimmed" : ""}`}
            tabIndex={0}
            role="button"
            aria-label={`${s.site_name} (${s.site_type.replace(/_/g, " ")}, ${s.tier ?? "unknown"}). ${s.conduit_count} conduits${isOnPath ? ". On traced service path" : ""}. Press Enter for details.`}
            onClick={() => onSelectSite(isSelected ? null : s)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectSite(isSelected ? null : s);
              }
            }}
            opacity={dimmed ? 0.25 : 1}
          >
            <circle
              cx={p.x}
              cy={p.y}
              r={r}
              fill={BRAND.white}
              stroke={nodeStroke}
              strokeWidth={nodeStrokeWidth}
            />
            <text
              x={p.x}
              y={p.y + 4}
              textAnchor="middle"
              fontSize={isT1 ? 14 : 11}
              fill={BRAND.darkTeal}
              fontWeight={600}
              fontFamily="'Inter', sans-serif"
            >
              {s.site_type === "data_center" ? "DC" : "CO"}
            </text>
            {isT1 && (
              <text
                x={p.x}
                y={p.y + r + 16}
                textAnchor="middle"
                fontSize={10}
                fill={BRAND.iron}
                fontFamily="'JetBrains Mono', monospace"
              >
                {s.clli_code ?? s.site_id}
              </text>
            )}
          </g>
        );
      })}

      {/* Hazard overlay markers (§4.2) */}
      {overlays.hazard && hazards.map((h) => {
        // Simple position: use lat/lon scaled relative to visible sites
        // For demo, place hazards based on hash of hazard_id in visible area
        const hash = h.hazard_id.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
        const hx = 80 + (hash % (CANVAS_W - 160));
        const hy = 60 + ((hash * 7) % (CANVAS_H - 120));
        const hazColor = h.severity === "critical" ? BRAND.riskRed
          : h.severity === "high" ? BRAND.orange
          : "#D97706";

        return (
          <g key={h.hazard_id} className="hazard-overlay-marker">
            {/* Proximity ring */}
            <circle
              cx={hx}
              cy={hy}
              r={h.direct_impact_spans > 0 ? 30 : 20}
              fill={hazColor}
              fillOpacity={0.08}
              stroke={hazColor}
              strokeWidth={1.5}
              strokeDasharray="4,3"
            />
            {/* Hazard icon hexagon */}
            <circle
              cx={hx}
              cy={hy}
              r={16}
              fill={hazColor}
              fillOpacity={0.2}
              stroke={hazColor}
              strokeWidth={1.5}
            />
            <text
              x={hx}
              y={hy + 5}
              textAnchor="middle"
              fontSize={14}
            >
              {HAZARD_ICONS[h.hazard_type] ?? "\u26a0\ufe0f"}
            </text>
            <text
              x={hx}
              y={hy + 30}
              textAnchor="middle"
              fontSize={9}
              fill={BRAND.iron}
              fontFamily="'Inter', sans-serif"
            >
              {h.name.slice(0, 20)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

function TopologyPage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/topology" });

  const [regions, setRegions] = useState<RegionSummary[]>([]);
  const [sites, setSites] = useState<SiteNode[]>([]);
  const [conduits, setConduits] = useState<ConduitEdge[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [selectedSite, setSelectedSite] = useState<SiteNode | null>(null);
  const [selectedConduit, setSelectedConduit] = useState<ConduitEdge | null>(null);
  const [overlays, setOverlays] = useState<Overlays>({
    diversity: false,
    srlg: false,
    hazard: false,
  });
  const [legendCollapsed, setLegendCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);

  // Path trace state (§2)
  const [tracedServiceId, setTracedServiceId] = useState<string | null>(null);
  const [pathHops, setPathHops] = useState<PathHop[]>([]);
  const [diversity, setDiversity] = useState<ServiceDiversity | null>(null);

  // SRLG overlay state (§3)
  const [srlgs, setSrlgs] = useState<SrlgMember[]>([]);

  // Hazard overlay state (§4)
  const [hazards, setHazards] = useState<HazardOverlay[]>([]);

  // Cross-view nav: auto-trace if ?service= is in URL (§9.2)
  useEffect(() => {
    if (search.service && search.service !== tracedServiceId) {
      setTracedServiceId(search.service);
      setOverlays((o) => ({ ...o, diversity: true }));
    }
  }, [search.service]);

  // Cross-view nav: auto-enable hazard overlay if ?hazard= (§9.2)
  useEffect(() => {
    if (search.hazard) {
      setOverlays((o) => ({ ...o, hazard: true }));
    }
  }, [search.hazard]);

  // Fetch region summaries on mount
  useEffect(() => {
    setLoading(true);
    fetch("/api/topology/regions")
      .then((r) => r.json())
      .then((data) => {
        setRegions(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Fetch sites + conduits when drilling into a region
  useEffect(() => {
    if (!selectedRegion) {
      setSites([]);
      setConduits([]);
      return;
    }
    setLoading(true);
    setSelectedSite(null);
    setSelectedConduit(null);
    Promise.all([
      fetch(`/api/topology/sites?region=${encodeURIComponent(selectedRegion)}`).then((r) =>
        r.json()
      ),
      fetch(`/api/topology/conduits?region=${encodeURIComponent(selectedRegion)}`).then((r) =>
        r.json()
      ),
    ])
      .then(([s, c]) => {
        setSites(s);
        setConduits(c);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [selectedRegion]);

  // Fetch path trace when a service is selected (§2, §10.2)
  useEffect(() => {
    if (!tracedServiceId) {
      setPathHops([]);
      setDiversity(null);
      return;
    }
    Promise.all([
      fetch(`/api/topology/path-trace/${encodeURIComponent(tracedServiceId)}`).then((r) => r.json()),
      fetch(`/api/topology/diversity/${encodeURIComponent(tracedServiceId)}`).then((r) =>
        r.ok ? r.json() : null
      ),
    ])
      .then(([hops, div]) => {
        setPathHops(hops);
        setDiversity(div);
        // Auto-navigate to first region on path if not already in one
        if (hops.length > 0 && !selectedRegion) {
          const firstRegion = hops[0].site_a_region;
          if (firstRegion) setSelectedRegion(firstRegion);
        }
      })
      .catch(() => {
        setPathHops([]);
        setDiversity(null);
      });
  }, [tracedServiceId]);

  // Fetch SRLGs when overlay toggled on and region selected (§3)
  useEffect(() => {
    if (!overlays.srlg || !selectedRegion) {
      setSrlgs([]);
      return;
    }
    fetch(`/api/topology/srlgs?region=${encodeURIComponent(selectedRegion)}`)
      .then((r) => r.json())
      .then(setSrlgs)
      .catch(() => setSrlgs([]));
  }, [overlays.srlg, selectedRegion]);

  // Fetch hazards when overlay toggled on (§4)
  useEffect(() => {
    if (!overlays.hazard) {
      setHazards([]);
      return;
    }
    fetch("/api/topology/hazards")
      .then((r) => r.json())
      .then(setHazards)
      .catch(() => setHazards([]));
  }, [overlays.hazard]);

  // Keyboard shortcuts (§7.1)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      switch (e.key.toLowerCase()) {
        case "d":
          setOverlays((o) => ({ ...o, diversity: !o.diversity }));
          break;
        case "s":
          setOverlays((o) => ({ ...o, srlg: !o.srlg }));
          break;
        case "h":
          setOverlays((o) => ({ ...o, hazard: !o.hazard }));
          break;
        case "f":
          break;
        case "escape":
          if (selectedConduit) setSelectedConduit(null);
          else if (selectedSite) setSelectedSite(null);
          else if (selectedRegion) setSelectedRegion(null);
          break;
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [selectedSite, selectedRegion, selectedConduit]);

  const handleToggle = useCallback((key: keyof Overlays) => {
    setOverlays((o) => ({ ...o, [key]: !o[key] }));
  }, []);

  const handleClearTrace = useCallback(() => {
    setTracedServiceId(null);
    setPathHops([]);
    setDiversity(null);
    // Clear URL param
    navigate({ to: "/topology", search: {} });
  }, [navigate]);

  return (
    <>
      <Toolbar
        overlays={overlays}
        onToggle={handleToggle}
        onFit={() => {}}
        onZoomIn={() => {}}
        onZoomOut={() => {}}
        selectedRegion={selectedRegion}
        onBack={() => setSelectedRegion(null)}
      />

      {/* Path trace banner (§2) */}
      {tracedServiceId && pathHops.length > 0 && (
        <PathTraceBanner
          serviceId={tracedServiceId}
          diversity={diversity}
          hops={pathHops}
          onClear={handleClearTrace}
        />
      )}

      <div className="topo-canvas-wrap" aria-busy={loading}>
        {loading && (
          <div className="topo-loading">
            Loading topology data\u2026
          </div>
        )}

        {!loading && !selectedRegion && regions.length > 0 && (
          <RegionGraph regions={regions} onDrillIn={setSelectedRegion} />
        )}

        {!loading && selectedRegion && sites.length > 0 && (
          <SiteGraph
            sites={sites}
            conduits={conduits}
            onSelectSite={setSelectedSite}
            selectedSiteId={selectedSite?.site_id ?? null}
            onSelectConduit={setSelectedConduit}
            selectedConduitId={selectedConduit?.conduit_id ?? null}
            pathHops={pathHops}
            srlgs={srlgs}
            hazards={hazards}
            overlays={overlays}
            diversity={diversity}
          />
        )}

        {!loading && !selectedRegion && regions.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true">
              \ud83c\udf10
            </div>
            <p>No topology data available</p>
            <p className="empty-hint">Gold tables may still be loading</p>
          </div>
        )}

        {!loading && selectedRegion && sites.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true">
              \ud83d\udce1
            </div>
            <p>No sites found in {selectedRegion}</p>
          </div>
        )}

        {/* Legend (§8) */}
        <Legend
          collapsed={legendCollapsed}
          onToggle={() => setLegendCollapsed((c) => !c)}
        />

        {/* Site detail panel (§5.1) */}
        {selectedSite && !selectedConduit && (
          <SiteDetailPanel
            site={selectedSite}
            conduits={conduits}
            onClose={() => setSelectedSite(null)}
          />
        )}

        {/* Edge detail panel (§5.2) */}
        {selectedConduit && (
          <EdgeDetailPanel
            conduit={selectedConduit}
            srlgs={srlgs}
            hazards={hazards}
            onClose={() => setSelectedConduit(null)}
          />
        )}
      </div>
    </>
  );
}
