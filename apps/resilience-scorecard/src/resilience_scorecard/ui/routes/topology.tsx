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
// Viewport width hook (§6.2 — Mobile tree fallback below 768px)
// ---------------------------------------------------------------------------

function useWindowWidth(): number {
  const [width, setWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : 1024
  );
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}

const MOBILE_BREAKPOINT = 768;

// ---------------------------------------------------------------------------
// Focus trap hook for dialog panels (WCAG 2.4.3 — Focus Order)
// Traps Tab / Shift+Tab within the panel, handles Escape to close,
// and auto-focuses the close button on mount.
// ---------------------------------------------------------------------------

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function useFocusTrap(
  ref: React.RefObject<HTMLDivElement | null>,
  onClose: () => void
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Auto-focus the close button on mount
    const closeBtn = el.querySelector<HTMLElement>(".panel-close");
    closeBtn?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const focusable = Array.from(
        el.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((node) => !node.hasAttribute("disabled"));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        // Shift+Tab: wrap from first → last
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        // Tab: wrap from last → first
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    // Attach to the panel element so the trap only fires when focus is inside
    el.addEventListener("keydown", handleKeyDown);
    // Also attach on document to catch the very first Tab before focus enters
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      el.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [ref, onClose]);
}

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

// BUG-DW-070: all SRLG strokes >=3:1 vs platinum #E8E8E8 canvas (WCAG 1.4.11).
// #D97706 (2.60:1) -> #B45309 (4.10:1); #F26522 (2.57:1) -> #C2410C (4.23:1).
// Brand orange #F26522 is reserved for decorative fills/accents only.
const SRLG_COLORS: Record<string, string> = {
  shared_conduit: "#4D4D4D",   // 6.90:1
  bridge: "#B45309",           // 4.10:1
  rail_crossing: "#B45309",    // 4.10:1
  power_feed: "#C2410C",       // 4.23:1
  tunnel: "#4D4D4D",           // 6.90:1
  central_office: "#D32F2F",   // 4.06:1
};

// BUG-DW-070: SRLG types that share a color get a unique dash pattern so the
// type is distinguishable without color (WCAG 1.4.1). Icon + text label in the
// legend and conduit panel carry the type as well.
const SRLG_DASHES: Record<string, string> = {
  shared_conduit: "",          // solid
  tunnel: "10,3,2,3",          // dash-dot
  bridge: "",                  // solid
  rail_crossing: "4,2",        // short dashes
  power_feed: "8,2,2,2",       // long dash-dot
  central_office: "12,3",      // long dashes
};

const SRLG_LABELS: Record<string, string> = {
  shared_conduit: "Shared Conduit",
  bridge: "Bridge",
  rail_crossing: "Rail Crossing",
  power_feed: "Power Feed",
  tunnel: "Tunnel",
  central_office: "Central Office",
};

// BUG-DW-070: hazard severity encoded by color AND stroke pattern/width so it
// survives grayscale and forced-colors (WCAG 1.4.1, 1.4.11). All colors >=3:1 vs #E8E8E8.
const HAZARD_SEVERITY_STYLES: Record<string, { color: string; dash: string; width: number; label: string }> = {
  critical: { color: "#D32F2F", dash: "", width: 2.5, label: "Critical" },     // 4.06:1, solid
  high: { color: "#C2410C", dash: "6,3", width: 2, label: "High" },            // 4.23:1, dashed
  medium: { color: "#B45309", dash: "2,3", width: 1.5, label: "Medium" },      // 4.10:1, dotted
  low: { color: "#4D4D4D", dash: "1,4", width: 1.5, label: "Low" },           // 6.90:1, sparse dots
};

// Hazard type icons per HAZARD-VIS-SPEC §1
const HAZARD_ICONS: Record<string, string> = {
  wildfire: "🔥",
  flood: "🌊",
  severe_weather: "⛈️",
  earthquake: "🌍",
  dig_ticket: "🚧",
};

// Diversity colors per §2.1 — edge stroke colors
// BUG-DW-057: darkened to ≥3:1 non-text contrast against #E8E8E8 canvas (WCAG 1.4.11)
const DIVERSITY_COLORS: Record<string, string> = {
  // BUG-DW-073: ratios re-measured vs #E8E8E8 (WCAG relative luminance)
  fully_diverse: "#15803D",      // was #16A34A (2.69:1) → 4.09:1 ✅
  partially_diverse: "#B45309",  // was #D97706 (2.60:1) → 4.10:1 ✅
  single_path: "#DC2626",        // 3.94:1 ✅
  unknown: "#6B7280",            // was #9CA3AF (2.07:1) → 3.95:1 ✅
};

// BUG-DW-066: Dash patterns per diversity status for forced-colors (WCAG 1.4.1)
// Provides non-color encoding redundancy — protect paths use "8,4" separately.
const DIVERSITY_DASHES: Record<string, string> = {
  fully_diverse: "",          // solid
  partially_diverse: "6,3",   // medium dashes
  single_path: "2,3",         // dots
  unknown: "1,4",             // sparse dots
};

// High-contrast badge pairings per §2.1 (WCAG 1.4.3 AA ≥ 4.5:1)
// BUG-QA-054: border now references DIVERSITY_COLORS (single source of truth)
const DIVERSITY_BADGE_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  fully_diverse: { bg: "#DCFCE7", text: "#166534", border: DIVERSITY_COLORS.fully_diverse },
  partially_diverse: { bg: "#FEF3C7", text: "#92400E", border: DIVERSITY_COLORS.partially_diverse },
  single_path: { bg: "#FEE2E2", text: "#991B1B", border: DIVERSITY_COLORS.single_path },
  unknown: { bg: "#F3F4F6", text: "#4B5563", border: DIVERSITY_COLORS.unknown },
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
  orange: "#F26522",       // decorative fills/accents only (2.57:1 vs platinum)
  orangeStroke: "#C2410C", // BUG-DW-070: selection strokes (4.23:1 vs platinum, 5.18:1 vs white)
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
        <button
          type="button"
          className="topo-legend-collapse-btn"
          onClick={onToggle}
          aria-expanded={false}
          aria-controls="topo-legend-body"
        >
          Legend <span aria-hidden="true">▾</span>
        </button>
      </div>
    );
  }

  return (
    <div className="topo-legend" role="region" aria-label="Graph legend">
      <div id="topo-legend-body">
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

      {/* BUG-DW-066: SVG line swatches with dash patterns for forced-colors (WCAG 1.4.1) */}
      <div className="legend-section">
        <div className="legend-section-title">Diversity</div>
        {[
          { key: "fully_diverse", color: DIVERSITY_COLORS.fully_diverse, dash: DIVERSITY_DASHES.fully_diverse, label: "Fully Diverse" },
          { key: "partially_diverse", color: DIVERSITY_COLORS.partially_diverse, dash: DIVERSITY_DASHES.partially_diverse, label: "Partially Diverse" },
          { key: "single_path", color: DIVERSITY_COLORS.single_path, dash: DIVERSITY_DASHES.single_path, label: "Single Path" },
          { key: "unknown", color: DIVERSITY_COLORS.unknown, dash: DIVERSITY_DASHES.unknown, label: "Unknown" },
        ].map((d) => (
          <div key={d.key} className="legend-item">
            <svg width="24" height="12" aria-hidden="true" className="legend-swatch" style={{ border: `1px solid ${d.color}`, borderRadius: 2 }}>
              <line x1="2" y1="6" x2="22" y2="6" stroke={d.color} strokeWidth="3" strokeDasharray={d.dash || undefined} />
            </svg>
            {d.label}
          </div>
        ))}
      </div>

      {/* BUG-DW-070: SRLG types — icon + text + dash pattern (color is not the only cue) */}
      <div className="legend-section">
        <div className="legend-section-title">Shared Risk Groups</div>
        {Object.keys(SRLG_COLORS).map((k) => (
          <div key={k} className="legend-item">
            <svg width="24" height="12" aria-hidden="true" className="legend-swatch">
              <line x1="2" y1="6" x2="22" y2="6" stroke={SRLG_COLORS[k]} strokeWidth="3" strokeDasharray={SRLG_DASHES[k] || undefined} />
            </svg>
            <span aria-hidden="true">{SRLG_ICONS[k]}</span>
            {SRLG_LABELS[k]}
          </div>
        ))}
      </div>

      {/* BUG-DW-070: hazard severity — ring stroke pattern + width, grayscale-safe */}
      <div className="legend-section">
        <div className="legend-section-title">Hazard Severity</div>
        {Object.entries(HAZARD_SEVERITY_STYLES).map(([k, st]) => (
          <div key={k} className="legend-item">
            <svg width="14" height="14" aria-hidden="true" className="legend-swatch">
              <circle cx="7" cy="7" r="5" fill="none" stroke={st.color} strokeWidth={st.width} strokeDasharray={st.dash || undefined} />
            </svg>
            {st.label}
          </div>
        ))}
      </div>
      </div>

      <button
        type="button"
        className="topo-legend-collapse-btn"
        onClick={onToggle}
        aria-expanded={true}
        aria-controls="topo-legend-body"
      >
        Collapse <span aria-hidden="true">▴</span>
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

  // Focus trap: traps Tab/Shift+Tab within panel, Escape to close (WCAG 2.4.3)
  useFocusTrap(panelRef, onClose);

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

  // Focus trap: traps Tab/Shift+Tab within panel, Escape to close (WCAG 2.4.3)
  useFocusTrap(panelRef, onClose);

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
          {conduit.conduit_name ? ` · ${conduit.conduit_name}` : ""}
        </h3>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">
          ✕
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
                    {SRLG_ICONS[s.srlg_type] ?? "⚠️"}
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
                  {s.description ? ` — ${s.description}` : ""}
                </div>
                {/* BUG-DW-055: Cross-view link to Action Queue per §9.2 */}
                <Link
                  to="/actions"
                  search={{ srlg: s.srlg_id }}
                  className="panel-action-link"
                  aria-label={`Open actions for SRLG ${s.srlg_id}`}
                >
                  Open action →
                </Link>
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
                    {HAZARD_ICONS[h.hazard_type] ?? "⚠️"}
                  </span>
                  {h.name}
                </div>
                <div className="conduit-meta">
                  {h.severity} · {h.direct_impact_spans} direct impact spans
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
          style={(() => {
            const badge = DIVERSITY_BADGE_STYLES[diversity?.diversity_status ?? "unknown"] ?? DIVERSITY_BADGE_STYLES.unknown;
            return { background: badge.bg, color: badge.text, borderColor: badge.border };
          })()}
        >
          {divLabel}
        </span>
        <span className="mono" style={{ fontWeight: 600 }}>
          {serviceId}
        </span>
        <span className="path-trace-stats">
          {workingHops.length} working hops
          {protectHops.length > 0 ? ` · ${protectHops.length} protect hops` : " · no protect path"}
          {diversity && diversity.shared_srlg_count > 0
            ? ` · ${diversity.shared_srlg_count} shared SRLGs`
            : ""}
        </span>
      </div>
      <div className="path-trace-actions">
        <Link
          to="/"
          search={{ service: serviceId }}
          className="path-trace-link"
        >
          View in Service Table →
        </Link>
        <button className="path-trace-clear" onClick={onClear}>
          ✕ Clear trace
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
          // BUG-DW-066: Non-color dash encoding for forced-colors (WCAG 1.4.1)
          if (hasWorking) {
            const divDash = DIVERSITY_DASHES[diversity?.diversity_status ?? "unknown"] ?? "";
            if (divDash) dashArray = divDash;
          }
        }
        if (hasSrlg) {
          const firstSrlg = srlgs.find((s) => s.conduit_id === c.conduit_id);
          if (firstSrlg) {
            edgeColor = SRLG_COLORS[firstSrlg.srlg_type] ?? BRAND.iron;
            // BUG-DW-070: non-color SRLG type encoding
            const srlgDash = SRLG_DASHES[firstSrlg.srlg_type];
            if (srlgDash) dashArray = srlgDash;
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
            stroke={isSelected ? BRAND.orangeStroke : edgeColor}
            strokeWidth={isOnPath ? 3 : Math.min(1 + c.span_count / 3, 5)}
            strokeDasharray={dashArray}
            opacity={edgeOpacity}
            style={hasSrlg ? { ["--srlg-color" as string]: edgeColor } : undefined}
            tabIndex={0}
            role="button"
            aria-label={`Conduit ${c.conduit_id}: ${c.conduit_type}, ${c.length_km} km, ${c.span_count} spans${hasSrlg ? " (SRLG member)" : ""}. Press Enter for details.`}
            aria-describedby={`conduit-desc-${c.conduit_id}`}
            onClick={() => onSelectConduit(isSelected ? null : c)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectConduit(isSelected ? null : c);
              }
            }}
          >
            <title id={`conduit-desc-${c.conduit_id}`}>
              {c.conduit_id}: {c.conduit_type} · {c.length_km} km · {c.span_count} spans
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
          nodeStroke = BRAND.orangeStroke;
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

      {/* Hazard overlay markers (§4.2) — BUG-DW-056: a11y fix */}
      {overlays.hazard && hazards.map((h) => {
        // Simple position: use lat/lon scaled relative to visible sites
        // For demo, place hazards based on hash of hazard_id in visible area
        const hash = h.hazard_id.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
        const hx = 80 + (hash % (CANVAS_W - 160));
        const hy = 60 + ((hash * 7) % (CANVAS_H - 120));
        // BUG-DW-070: color + stroke pattern/width per severity (grayscale-safe)
        const sev = HAZARD_SEVERITY_STYLES[h.severity] ?? HAZARD_SEVERITY_STYLES.medium;
        const hazColor = sev.color;

        return (
          <g
            key={h.hazard_id}
            className="hazard-overlay-marker"
            role="img"
            aria-label={`${h.hazard_type.replace(/_/g, " ")} hazard: ${h.name}, severity ${h.severity}, ${h.direct_impact_spans} direct impact spans, ${h.near_impact_spans} near impact spans`}
            tabIndex={0}
          >
            <title>
              {h.hazard_type.replace(/_/g, " ")} hazard: {h.name} ({h.severity}) — {h.direct_impact_spans} direct, {h.near_impact_spans} near impact spans
            </title>
            {/* Proximity ring */}
            <circle
              cx={hx}
              cy={hy}
              r={h.direct_impact_spans > 0 ? 30 : 20}
              fill={hazColor}
              fillOpacity={0.08}
              stroke={hazColor}
              strokeWidth={sev.width}
              strokeDasharray={sev.dash || undefined}
            />
            {/* Hazard icon hexagon */}
            <circle
              cx={hx}
              cy={hy}
              r={16}
              fill={hazColor}
              fillOpacity={0.2}
              stroke={hazColor}
              strokeWidth={sev.width}
            />
            <text
              x={hx}
              y={hy + 5}
              textAnchor="middle"
              fontSize={14}
              aria-hidden="true"
            >
              {HAZARD_ICONS[h.hazard_type] ?? "⚠️"}
            </text>
            <text
              x={hx}
              y={hy + 30}
              textAnchor="middle"
              fontSize={9}
              fill={BRAND.iron}
              fontFamily="'Inter', sans-serif"
              aria-hidden="true"
            >
              {h.name.slice(0, 20)}
            </text>
          </g>
        );
      })}

      {/* BUG-DW-056: sr-only hazard summary for screen readers (WCAG 4.1.2) */}
      {overlays.hazard && hazards.length > 0 && (
        <foreignObject x="0" y="0" width="1" height="1" overflow="visible">
          <div className="sr-only" role="status" aria-live="polite">
            {hazards.length} active hazard{hazards.length !== 1 ? "s" : ""} on map:{" "}
            {hazards.map((h) => `${h.name} (${h.severity})`).join(", ")}
          </div>
        </foreignObject>
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Mobile Tree View (TOPOLOGY-VIS-SPEC §6.2 — <768px fallback)
// Replaces the SVG graph with an accessible, searchable tree view.
// Hierarchy: Region → Site → Conduit (with span count)
// ---------------------------------------------------------------------------

interface MobileTreeProps {
  regions: RegionSummary[];
  onSelectSite: (site: SiteNode) => void;
  onSelectConduit: (conduit: ConduitEdge) => void;
  overlays: Overlays;
  diversity: ServiceDiversity | null;
  tracedServiceId: string | null;
}

function MobileTreeView({
  regions,
  onSelectSite,
  onSelectConduit,
  overlays,
  diversity,
  tracedServiceId,
}: MobileTreeProps) {
  const [expandedRegions, setExpandedRegions] = useState<Set<string>>(
    new Set()
  );
  const [expandedSites, setExpandedSites] = useState<Set<string>>(new Set());
  const [regionData, setRegionData] = useState<
    Record<string, { sites: SiteNode[]; conduits: ConduitEdge[] }>
  >({});
  const [searchTerm, setSearchTerm] = useState("");
  const [loadingRegion, setLoadingRegion] = useState<string | null>(null);
  const [detailSite, setDetailSite] = useState<SiteNode | null>(null);
  const [detailConduit, setDetailConduit] = useState<ConduitEdge | null>(null);
  const treeRef = useRef<HTMLUListElement>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  // Focus trap for the full-screen detail modal
  useFocusTrap(detailRef, () => {
    setDetailSite(null);
    setDetailConduit(null);
  });

  // Lazy-load sites + conduits per region on expand
  const toggleRegion = useCallback(
    (region: string) => {
      setExpandedRegions((prev) => {
        const next = new Set(prev);
        if (next.has(region)) {
          next.delete(region);
        } else {
          next.add(region);
          // Fetch data if not cached
          if (!regionData[region]) {
            setLoadingRegion(region);
            Promise.all([
              fetch(
                `/api/topology/sites?region=${encodeURIComponent(region)}`
              ).then((r) => r.json()),
              fetch(
                `/api/topology/conduits?region=${encodeURIComponent(region)}`
              ).then((r) => r.json()),
            ])
              .then(([sites, conduits]) => {
                setRegionData((d) => ({ ...d, [region]: { sites, conduits } }));
                setLoadingRegion(null);
              })
              .catch(() => setLoadingRegion(null));
          }
        }
        return next;
      });
    },
    [regionData]
  );

  const toggleSite = useCallback((siteId: string) => {
    setExpandedSites((prev) => {
      const next = new Set(prev);
      if (next.has(siteId)) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  }, []);

  // Arrow key navigation for role="tree" (WCAG 2.1.1)
  const handleTreeKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (!target.matches('[role="treeitem"]')) return;

      const items = Array.from(
        treeRef.current?.querySelectorAll<HTMLElement>('[role="treeitem"]') ?? []
      );
      const idx = items.indexOf(target);
      if (idx === -1) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          items[Math.min(idx + 1, items.length - 1)]?.focus();
          break;
        case "ArrowUp":
          e.preventDefault();
          items[Math.max(idx - 1, 0)]?.focus();
          break;
        case "ArrowRight": {
          const regionKey = target.dataset.region;
          const siteKey = target.dataset.site;
          if (regionKey && !expandedRegions.has(regionKey))
            toggleRegion(regionKey);
          else if (siteKey && !expandedSites.has(siteKey))
            toggleSite(siteKey);
          break;
        }
        case "ArrowLeft": {
          const regionKey = target.dataset.region;
          const siteKey = target.dataset.site;
          if (regionKey && expandedRegions.has(regionKey))
            toggleRegion(regionKey);
          else if (siteKey && expandedSites.has(siteKey))
            toggleSite(siteKey);
          break;
        }
        case "Enter":
        case " ":
          e.preventDefault();
          target.click();
          break;
      }
    },
    [expandedRegions, expandedSites, toggleRegion, toggleSite]
  );

  // Filter helper
  const matchesSearch = useCallback(
    (text: string) =>
      !searchTerm || text.toLowerCase().includes(searchTerm.toLowerCase()),
    [searchTerm]
  );

  // Tier label for display
  const tierLabel = (tier: string | null): string => {
    if (!tier) return "";
    return tier === "tier_1" ? "T1" : tier === "tier_2" ? "T2" : "T3";
  };

  // Diversity badge for a status
  const diversityBadge = (status: string | undefined) => {
    if (!status || !overlays.diversity) return null;
    const style = DIVERSITY_BADGE_STYLES[status];
    if (!style) return null;
    const label =
      status === "fully_diverse"
        ? "Diverse"
        : status === "partially_diverse"
        ? "Partial"
        : status === "single_path"
        ? "Single"
        : "Unknown";
    return (
      <span
        className="mobile-tree-badge"
        style={{
          backgroundColor: style.bg,
          color: style.text,
          borderColor: style.border,
        }}
        aria-label={`Diversity: ${label}`}
      >
        {label}
      </span>
    );
  };

  // Group conduits by site_a_id for tree nesting
  const conduitsForSite = useCallback(
    (region: string, siteId: string): ConduitEdge[] => {
      const data = regionData[region];
      if (!data) return [];
      return data.conduits.filter((c) => c.site_a_id === siteId);
    },
    [regionData]
  );

  return (
    <div className="mobile-tree-container">
      {/* Search input (§6.2) */}
      <div className="mobile-tree-search">
        <label htmlFor="mobile-tree-search" className="sr-only">
          Search sites, conduits, spans
        </label>
        <input
          id="mobile-tree-search"
          type="search"
          placeholder="🔍 Search sites, conduits, spans…"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="mobile-tree-search-input"
          autoComplete="off"
        />
      </div>

      {/* Accessible tree (WCAG 1.3.1) */}
      <ul
        ref={treeRef}
        role="tree"
        aria-label="Network topology tree"
        className="mobile-tree-list"
        onKeyDown={handleTreeKeyDown}
      >
        {regions
          .filter((r) => matchesSearch(r.region))
          .map((region) => {
            const isExpanded = expandedRegions.has(region.region);
            const data = regionData[region.region];
            const isLoading = loadingRegion === region.region;

            return (
              <li
                key={region.region}
                role="treeitem"
                aria-expanded={isExpanded}
                aria-label={`${region.region} region, ${region.site_count} sites, ${region.conduit_count} conduits`}
                tabIndex={0}
                data-region={region.region}
                className="mobile-tree-region"
              >
                <div
                  className="mobile-tree-row mobile-tree-row--region"
                  onClick={() => toggleRegion(region.region)}
                >
                  <span className="mobile-tree-chevron" aria-hidden="true">
                    {isExpanded ? "▾" : "▸"}
                  </span>
                  <span className="mobile-tree-label">
                    {region.region} Region
                  </span>
                  <span className="mobile-tree-meta">
                    {region.site_count} sites
                  </span>
                </div>

                {/* Expanded region: show sites */}
                {isExpanded && (
                  <ul role="group" className="mobile-tree-group">
                    {isLoading && (
                      <li className="mobile-tree-loading" aria-live="polite">
                        Loading sites…
                      </li>
                    )}
                    {data &&
                      data.sites
                        .filter(
                          (s) =>
                            matchesSearch(s.site_name) ||
                            matchesSearch(s.city) ||
                            matchesSearch(s.site_id)
                        )
                        .sort((a, b) => {
                          // Sort: tier_1 first, then tier_2, then tier_3
                          const tierOrder = (t: string | null) =>
                            t === "tier_1" ? 0 : t === "tier_2" ? 1 : 2;
                          return tierOrder(a.tier) - tierOrder(b.tier);
                        })
                        .map((site) => {
                          const siteExpanded = expandedSites.has(site.site_id);
                          const siteConduits = conduitsForSite(
                            region.region,
                            site.site_id
                          );

                          return (
                            <li
                              key={site.site_id}
                              role="treeitem"
                              aria-expanded={
                                siteConduits.length > 0
                                  ? siteExpanded
                                  : undefined
                              }
                              aria-label={`${site.site_name}, ${site.site_type}, ${site.city} ${site.state}, ${tierLabel(site.tier)}`}
                              tabIndex={-1}
                              data-site={site.site_id}
                              className="mobile-tree-site"
                            >
                              <div
                                className="mobile-tree-row mobile-tree-row--site"
                                onClick={() => {
                                  if (siteConduits.length > 0)
                                    toggleSite(site.site_id);
                                  else setDetailSite(site);
                                }}
                              >
                                <span
                                  className="mobile-tree-chevron"
                                  aria-hidden="true"
                                >
                                  {siteConduits.length > 0
                                    ? siteExpanded
                                      ? "▾"
                                      : "▸"
                                    : "•"}
                                </span>
                                <span className="mobile-tree-label">
                                  {site.site_name}
                                </span>
                                <span className="mobile-tree-meta">
                                  {site.city}{" "}
                                  <span className="mobile-tree-tier">
                                    [{tierLabel(site.tier)}]
                                  </span>
                                </span>
                                <button
                                  className="mobile-tree-detail-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setDetailSite(site);
                                  }}
                                  aria-label={`View details for ${site.site_name}`}
                                >
                                  ℹ️
                                </button>
                              </div>

                              {/* Expanded site: show conduits */}
                              {siteExpanded && siteConduits.length > 0 && (
                                <ul role="group" className="mobile-tree-group">
                                  {siteConduits
                                    .filter(
                                      (c) =>
                                        matchesSearch(
                                          c.conduit_name || c.conduit_id
                                        ) || matchesSearch(c.corridor || "")
                                    )
                                    .map((conduit) => (
                                      <li
                                        key={conduit.conduit_id}
                                        role="treeitem"
                                        tabIndex={-1}
                                        aria-label={`Conduit ${conduit.conduit_name || conduit.conduit_id}, ${conduit.conduit_type}, ${conduit.length_km.toFixed(1)} km, ${conduit.span_count} spans`}
                                        className="mobile-tree-conduit"
                                      >
                                        <div
                                          className="mobile-tree-row mobile-tree-row--conduit"
                                          onClick={() =>
                                            setDetailConduit(conduit)
                                          }
                                        >
                                          <span
                                            className="mobile-tree-connector"
                                            aria-hidden="true"
                                          >
                                            ├─
                                          </span>
                                          <span className="mobile-tree-label">
                                            {conduit.conduit_name ||
                                              conduit.conduit_id}
                                          </span>
                                          <span className="mobile-tree-meta">
                                            {conduit.length_km.toFixed(1)}km
                                            · {conduit.span_count} spans
                                          </span>
                                        </div>
                                      </li>
                                    ))}
                                </ul>
                              )}
                            </li>
                          );
                        })}
                  </ul>
                )}
              </li>
            );
          })}
      </ul>

      {/* Diversity summary when tracing */}
      {tracedServiceId && diversity && overlays.diversity && (
        <div className="mobile-tree-diversity-summary" role="status">
          <strong>Tracing:</strong> {tracedServiceId}
          {diversityBadge(diversity.diversity_status)}
        </div>
      )}

      {/* Full-screen detail modal (§6.2) */}
      {(detailSite || detailConduit) && (
        <div
          className="mobile-detail-modal"
          role="dialog"
          aria-modal="true"
          aria-label={
            detailSite
              ? `Details for ${detailSite.site_name}`
              : `Details for ${detailConduit?.conduit_name || detailConduit?.conduit_id}`
          }
          ref={detailRef}
        >
          <div className="mobile-detail-header">
            <h2 className="mobile-detail-title">
              {detailSite
                ? detailSite.site_name
                : detailConduit?.conduit_name || detailConduit?.conduit_id}
            </h2>
            <button
              className="panel-close mobile-detail-close"
              onClick={() => {
                setDetailSite(null);
                setDetailConduit(null);
              }}
              aria-label="Close detail panel"
            >
              ✕
            </button>
          </div>
          <div className="mobile-detail-body">
            {detailSite && (
              <dl className="mobile-detail-dl">
                <dt>Type</dt>
                <dd>{detailSite.site_type}</dd>
                <dt>CLLI</dt>
                <dd>{detailSite.clli_code || "—"}</dd>
                <dt>Location</dt>
                <dd>
                  {detailSite.city}, {detailSite.state}
                </dd>
                <dt>Region</dt>
                <dd>{detailSite.region}</dd>
                <dt>Tier</dt>
                <dd>{tierLabel(detailSite.tier) || "—"}</dd>
                <dt>Coordinates</dt>
                <dd>
                  {detailSite.latitude.toFixed(4)},{" "}
                  {detailSite.longitude.toFixed(4)}
                </dd>
                <dt>Conduits</dt>
                <dd>{detailSite.conduit_count}</dd>
              </dl>
            )}
            {detailConduit && (
              <dl className="mobile-detail-dl">
                <dt>Type</dt>
                <dd>{detailConduit.conduit_type}</dd>
                <dt>Corridor</dt>
                <dd>{detailConduit.corridor || "—"}</dd>
                <dt>Length</dt>
                <dd>{detailConduit.length_km.toFixed(1)} km</dd>
                <dt>Spans</dt>
                <dd>{detailConduit.span_count}</dd>
                <dt>Endpoints</dt>
                <dd>
                  {detailConduit.site_a_id} → {detailConduit.site_z_id}
                </dd>
              </dl>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main TopologyPage
// ---------------------------------------------------------------------------

function TopologyPage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/topology" });
  const viewportWidth = useWindowWidth();
  const isMobile = viewportWidth < MOBILE_BREAKPOINT;

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
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
    fetch("/api/topology/regions")
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load regions (${r.status})`);
        return r.json();
      })
      .then((data) => {
        setRegions(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load topology data");
        setLoading(false);
      });
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
      .catch((err) => {
        setError(err.message || "Failed to load region data");
        setLoading(false);
      });
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

      {error && (
        <div className="error-banner" role="alert">
          <strong>Error:</strong> {error}
          {/* BUG-DW-062: Replaced inline styles with CSS class; WCAG 2.5.8 24px target */}
          <button
            className="error-retry-btn"
            onClick={() => { setError(null); setLoading(true); fetch("/api/topology/regions").then((r) => r.json()).then(setRegions).catch(() => {}).finally(() => setLoading(false)); }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Mobile tree view fallback (§6.2) — replaces graph below 768px */}
      {isMobile ? (
        <div className="topo-canvas-wrap topo-canvas-wrap--mobile" aria-busy={loading}>
          {loading && (
            <div className="topo-loading" role="status" aria-label="Loading topology data">
              <div className="topo-skeleton-grid">
                {[1, 2].map((i) => (
                  <div key={i} className="topo-skeleton-card">
                    <div className="skeleton-loading" style={{ width: '60%', height: 16, marginBottom: 8 }} />
                    <div className="skeleton-loading" style={{ width: '80%', height: 12, marginBottom: 6 }} />
                    <div className="skeleton-loading" style={{ width: '45%', height: 12 }} />
                  </div>
                ))}
              </div>
              <span className="sr-only">Loading topology data…</span>
            </div>
          )}
          {!loading && regions.length > 0 && (
            <MobileTreeView
              regions={regions}
              onSelectSite={setSelectedSite}
              onSelectConduit={setSelectedConduit}
              overlays={overlays}
              diversity={diversity}
              tracedServiceId={tracedServiceId}
            />
          )}
          {!loading && regions.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon" aria-hidden="true">🌐</div>
              <p>No topology data available</p>
              <p className="empty-hint">Gold tables may still be loading</p>
            </div>
          )}
        </div>
      ) : (
        /* Desktop/tablet: full SVG graph */
        <div className="topo-canvas-wrap" aria-busy={loading}>
          {loading && (
            <div className="topo-loading" role="status" aria-label="Loading topology data">
              <div className="topo-skeleton-grid">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="topo-skeleton-card">
                    <div className="skeleton-loading" style={{ width: '60%', height: 16, marginBottom: 8 }} />
                    <div className="skeleton-loading" style={{ width: '80%', height: 12, marginBottom: 6 }} />
                    <div className="skeleton-loading" style={{ width: '45%', height: 12 }} />
                  </div>
                ))}
              </div>
              <span className="sr-only">Loading topology data…</span>
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
      )}
    </>
  );
}
