/**
 * Lakelink Fiber — Network Topology Graph View
 * TOPOLOGY-VIS-SPEC §9.1, §13 (phases 13a + 13b)
 *
 * Region-level aggregation (4 regions) with drill-in to site-level nodes
 * and conduit edges. Hierarchical SVG layout per §1.
 */
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { createFileRoute, useNavigate, useSearch } from "@tanstack/react-router";

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
}: {
  sites: SiteNode[];
  conduits: ConduitEdge[];
  onSelectSite: (site: SiteNode | null) => void;
  selectedSiteId: string | null;
}) {
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

      {/* Conduit edges */}
      {conduits.map((c) => {
        const pa = positions.get(c.site_a_id);
        const pz = positions.get(c.site_z_id);
        if (!pa || !pz) return null;
        return (
          <line
            key={c.conduit_id}
            x1={pa.x}
            y1={pa.y}
            x2={pz.x}
            y2={pz.y}
            className="topo-edge"
            strokeWidth={Math.min(1 + c.span_count / 3, 5)}
            opacity={0.5}
          >
            <title>
              {c.conduit_id}: {c.conduit_type} · {c.length_km} km · {c.span_count} spans
            </title>
          </line>
        );
      })}

      {/* Site nodes */}
      {sites.map((s) => {
        const p = positions.get(s.site_id);
        if (!p) return null;
        const isT1 = s.tier === "tier_1";
        const r = isT1 ? NODE_RADIUS_T1 : NODE_RADIUS_T2;
        const isSelected = selectedSiteId === s.site_id;

        return (
          <g
            key={s.site_id}
            className="topo-site-node"
            tabIndex={0}
            role="button"
            aria-label={`${s.site_name} (${s.site_type.replace(/_/g, " ")}, ${s.tier ?? "unknown"}). ${s.conduit_count} conduits. Press Enter for details.`}
            onClick={() => onSelectSite(isSelected ? null : s)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectSite(isSelected ? null : s);
              }
            }}
          >
            <circle
              cx={p.x}
              cy={p.y}
              r={r}
              fill={BRAND.white}
              stroke={isSelected ? BRAND.orange : BRAND.darkTeal}
              strokeWidth={isSelected ? 3 : 2}
            />
            {/* Site type icon (Building2 for T1, Building for T2) */}
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
            {/* Label below */}
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
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

function TopologyPage() {
  const [regions, setRegions] = useState<RegionSummary[]>([]);
  const [sites, setSites] = useState<SiteNode[]>([]);
  const [conduits, setConduits] = useState<ConduitEdge[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [selectedSite, setSelectedSite] = useState<SiteNode | null>(null);
  const [overlays, setOverlays] = useState<Overlays>({
    diversity: false,
    srlg: false,
    hazard: false,
  });
  const [legendCollapsed, setLegendCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);

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

  // Keyboard shortcuts (§7.1)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't intercept when focus is in an input
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
          // Fit — reset viewBox (no-op for now, SVG auto-fits)
          break;
        case "escape":
          if (selectedSite) setSelectedSite(null);
          else if (selectedRegion) setSelectedRegion(null);
          break;
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [selectedSite, selectedRegion]);

  const handleToggle = useCallback((key: keyof Overlays) => {
    setOverlays((o) => ({ ...o, [key]: !o[key] }));
  }, []);

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

      <div className="topo-canvas-wrap" aria-busy={loading}>
        {loading && (
          <div className="topo-loading">
            Loading topology data…
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
          />
        )}

        {!loading && !selectedRegion && regions.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true">
              🌐
            </div>
            <p>No topology data available</p>
            <p className="empty-hint">Gold tables may still be loading</p>
          </div>
        )}

        {!loading && selectedRegion && sites.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon" aria-hidden="true">
              📡
            </div>
            <p>No sites found in {selectedRegion}</p>
          </div>
        )}

        {/* Legend (§8) */}
        <Legend
          collapsed={legendCollapsed}
          onToggle={() => setLegendCollapsed((c) => !c)}
        />

        {/* Detail panel (§5.1) */}
        {selectedSite && (
          <SiteDetailPanel
            site={selectedSite}
            conduits={conduits}
            onClose={() => setSelectedSite(null)}
          />
        )}
      </div>
    </>
  );
}
