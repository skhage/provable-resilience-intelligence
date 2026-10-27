"""Pydantic models for the Lakelink Fiber Resilience Scorecard & Action Queue."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PathDiversityRating(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class ActionType(str, Enum):
    REROUTE = "reroute"
    DISPATCH = "dispatch"
    DISPATCH_CREW = "dispatch_crew"
    NOTIFY = "notify"
    NOTIFY_CUSTOMER = "notify_customer"
    ESCALATE = "escalate"
    ESCALATE_NOC = "escalate_noc"
    PREPOSITION = "preposition"
    PREPOSITION_SPLICE = "preposition_splice"


class ActionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Resilience Score Models
# ---------------------------------------------------------------------------

class ResilienceScoreOut(BaseModel):
    """Single service resilience score snapshot."""
    service_id: str
    service_name: str
    customer_id: str
    customer_name: str
    resilience_score: float = Field(ge=0, le=100)
    physical_redundancy_score: float = Field(ge=0, le=100)
    network_health_score: float = Field(ge=0, le=100)
    environmental_risk_score: float = Field(ge=0, le=100)
    path_diversity_rating: PathDiversityRating
    srlg_count: int = Field(ge=0)
    single_point_failures: int = Field(ge=0)
    snapshot_timestamp: datetime
    revenue_at_risk_usd: float | None = Field(default=None, description="Monthly revenue at risk in USD")


class ResilienceSummaryOut(BaseModel):
    """Aggregate resilience dashboard summary."""
    total_services: int
    avg_resilience_score: float
    critical_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    total_single_point_failures: int
    total_srlg_groups: int
    total_revenue_at_risk_usd: float | None = Field(default=None, description="Sum of monthly revenue at risk across all services (USD)")
    # P36-APP-V4-BB-SRLG-DISCLOSURE (V4-KPI-COPY-SPEC §2). Set only when PRI_V4_KPIS=true; null = v3 UI.
    bb_srlg_coverage: Literal["complete", "partial"] | None = Field(
        default=None,
        description="'partial' while the SRLG table the app reads has no backbone (BB-*/BBS-*) span rows; "
                    "'complete' once backbone shared-risk groups are present",
    )


class RiskDistributionOut(BaseModel):
    """Risk breakdown by category."""
    category: str
    count: int
    percentage: float


# ---------------------------------------------------------------------------
# Proactive Action Models (Lakebase state-managed)
# ---------------------------------------------------------------------------

class ProactiveActionOut(BaseModel):
    """Proactive action triggered by resilience risk thresholds."""
    action_id: str
    action_type: ActionType
    service_id: str
    service_name: str
    risk_trigger: str
    priority: RiskLevel
    status: ActionStatus
    assigned_to: str | None = None
    description: str
    resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    # Hazard context (HAZARD-VIS-SPEC §5) — populated when action is hazard-triggered
    hazard_type: str | None = Field(default=None, description="Hazard type key (e.g. wildfire, flood)")
    hazard_name: str | None = Field(default=None, description="Hazard event description/name")
    hazard_severity: str | None = Field(default=None, description="Hazard severity: critical|high|medium|low")
    hazard_spans_affected: int | None = Field(default=None, description="Span count in proximity zone")
    hazard_latitude: float | None = Field(default=None, description="Hazard epicenter latitude")
    hazard_longitude: float | None = Field(default=None, description="Hazard epicenter longitude")
    hazard_containment_pct: float | None = Field(default=None, description="Containment % (wildfire)")
    hazard_last_update: datetime | None = Field(default=None, description="Last hazard event update")


class ActionStatusUpdate(BaseModel):
    """Input model to update an action's status."""
    status: ActionStatus
    resolution_notes: str | None = None
    assigned_to: str | None = None


class ActionQueueSummaryOut(BaseModel):
    """Action queue aggregate counts."""
    total_actions: int
    pending_count: int
    in_progress_count: int
    completed_count: int
    cancelled_count: int
    critical_pending: int


class FeatureFlagsOut(BaseModel):
    """UI feature flags (V4-KPI-COPY-SPEC §0). v4_kpis=False renders the v3 freeze UI."""
    v4_kpis: bool = False


class MrcProtectedOut(BaseModel):
    """MRC Protected KPI (V4-KPI-COPY-SPEC §1, DEC-PRI-REV-PROTECTED-DEFINITION).

    Monthly recurring charge of distinct services with at least one completed proactive
    action. Each service is counted once (never summed per action).
    """
    mrc_protected_usd: float = Field(gt=0)
    services_protected: int = Field(gt=0)
    mrc_share: float = Field(ge=0, le=1, description="Share of total MRC, 0..1")
    total_mrc_usd: float
    total_services: int
    source: str = "mv_mrc_protected_v4_candidate"


# ---------------------------------------------------------------------------
# Hazard Summary Models (HAZARD-VIS-SPEC §6.1)
# ---------------------------------------------------------------------------

class HazardListItemOut(BaseModel):
    """Single hazard event for the hazard summary table (HAZARD-VIS-SPEC §6.2)."""
    hazard_id: str
    hazard_type: str
    name: str
    severity: str
    location: str
    spans_affected: int = Field(ge=0)
    is_active: bool
    last_update: datetime


class HazardSummaryOut(BaseModel):
    """Hazard dashboard KPI summary — active hazards impacting the Lakelink Fiber network."""
    active_hazards: int = Field(ge=0, description="Count of geographic hazard events with no end date")
    spans_at_risk: int = Field(ge=0, description="Distinct spans within direct impact zone (<5 km)")
    services_impacted: int = Field(ge=0, description="Distinct services with at least one span at risk")
    revenue_exposed_usd: float = Field(ge=0, description="Annual revenue exposed (MRC×12) for impacted services")


# ---------------------------------------------------------------------------
# Product Offering Models (P10-APP-PRODUCT-VIEW-PREP)
# ---------------------------------------------------------------------------

class ProductOfferingOut(BaseModel):
    """Lakelink Fiber product offering aligned to TMF product catalog."""
    product_offering_id: str = Field(description="Unique product offering ID")
    service_type: str = Field(description="Network service type: wavelength|ethernet|dark_fiber|ip_vpn|managed_security")
    product_name: str = Field(description="Commercial product name as marketed by Lakelink Fiber")
    product_category: str = Field(description="Product family grouping")
    network_technology: str = Field(description="Underlying network technology")
    technology_domain: str = Field(description="TMF SID technology domain")
    sla_tier_default: str = Field(description="Default SLA tier: standard|premium|premium_plus")
    bandwidth_options: str = Field(description="Comma-separated bandwidth tiers")
    is_diverse_eligible: bool = Field(description="Supports path diversity")
    mrc_range_usd: str = Field(description="Monthly recurring charge range (min-max)")


# ---------------------------------------------------------------------------
# Hazard × Span Crosswalk Models (P10-APP-HAZARD-XWALK-VIEW)
# ---------------------------------------------------------------------------

class HazardCrosswalkRowOut(BaseModel):
    """Single row in the hazard×span crosswalk aggregation (by type × proximity band)."""
    hazard_type: str = Field(description="Normalized type: severe_weather|earthquake|flood|wildfire|dig_ticket")
    proximity_band: str = Field(description="Distance band: direct_impact|near_field|buffer_zone")
    intersection_count: int = Field(ge=0, description="Number of hazard×span intersection records")
    distinct_spans: int = Field(ge=0, description="Distinct spans exposed in this bucket")
    avg_services_per_span: float = Field(ge=0, description="Average services per affected span")
    avg_distance_km: float = Field(ge=0, description="Average haversine distance in km")


class HazardCrosswalkSummaryOut(BaseModel):
    """KPI summary for the hazard×span crosswalk view."""
    total_intersections: int = Field(ge=0, description="Total hazard×span intersection records")
    distinct_spans_exposed: int = Field(ge=0, description="Distinct spans within any hazard zone")
    total_spans: int = Field(ge=0, description="Total spans in the network")
    exposure_pct: float = Field(ge=0, le=100, description="Percent of network spans exposed")
    hazard_types: int = Field(ge=0, description="Distinct hazard types with intersections")
    direct_impact_count: int = Field(ge=0, description="Intersections in direct_impact band (<1km)")
    near_field_count: int = Field(ge=0, description="Intersections in near_field band (1-5km)")
    buffer_zone_count: int = Field(ge=0, description="Intersections in buffer_zone band (5-radius_km)")


# ---------------------------------------------------------------------------
# Topology Models (TOPOLOGY-VIS-SPEC §10, §13)
# ---------------------------------------------------------------------------


class TopologyRegionSummaryOut(BaseModel):
    """Region-level topology summary for the overview graph."""
    region: str = Field(description="Lakelink Fiber operational region")
    site_count: int = Field(ge=0, description="Total active sites in region")
    tier_1_count: int = Field(ge=0, description="Backbone COs and DCs")
    tier_2_count: int = Field(ge=0, description="Regional COs and DCs")
    tier_3_count: int = Field(ge=0, description="Access sites (huts, customer premises)")
    co_count: int = Field(ge=0, description="Central offices")
    dc_count: int = Field(ge=0, description="Data centers")
    conduit_count: int = Field(ge=0, description="Active conduits touching this region")
    span_count: int = Field(ge=0, description="Active spans in this region")


class TopologySiteOut(BaseModel):
    """Site node for the topology graph."""
    site_id: str = Field(description="Unique site identifier")
    site_name: str = Field(description="Human-readable site name")
    site_type: str = Field(description="central_office | data_center | customer_premise | hut")
    clli_code: str | None = Field(default=None, description="CLLI code")
    latitude: float = Field(description="WGS84 latitude")
    longitude: float = Field(description="WGS84 longitude")
    city: str = Field(description="City name")
    state: str = Field(description="US state abbreviation")
    region: str = Field(description="Operational region")
    tier: str | None = Field(default=None, description="tier_1 | tier_2 | tier_3")
    conduit_count: int = Field(ge=0, description="Connected conduit count")


class TopologyConduitOut(BaseModel):
    """Conduit edge for the topology graph."""
    conduit_id: str = Field(description="Unique conduit identifier")
    conduit_name: str | None = Field(default=None, description="Route label")
    corridor: str | None = Field(default=None, description="Named corridor (e.g. I-70, US-36)")
    conduit_type: str = Field(description="underground | aerial | submarine | direct_buried")
    length_km: float = Field(ge=0, description="Route length in km")
    site_a_id: str = Field(description="A-end site")
    site_z_id: str = Field(description="Z-end site")
    span_count: int = Field(ge=0, description="Number of active spans in conduit")
    backbone_span_count: int = Field(default=0, ge=0, description="Active backbone (BB-*/BBS-*) spans in conduit")


# ---------------------------------------------------------------------------
# Conduit coverage (P35-APP-CONDUIT-COVERAGE-BADGE, v4 shadow — read-only)
# Source: physical_resource_conduit_v4_candidate.span_coverage_class (DE S35)
# ---------------------------------------------------------------------------


class SpanCoverageClass(str, Enum):
    """Known values. Live v4 (post BUG-DP-068 B2, 2026-10-25): REAL 55 / BB_SEGMENTED 92 / INVENTORY 1,914.

    Response models type the field as str so a new DE class never 500s the API
    (which would silently drop to mock data); the UI renders unknown classes generically.
    """
    REAL_SEGMENTED = "REAL_SEGMENTED"  # >=1 real SPAN-* segment
    BB_SEGMENTED = "BB_SEGMENTED"      # CDT-BBR-* backbone route conduit carrying BBS-* segments (B2)
    BB_ONLY = "BB_ONLY"                # legacy P35/span@11 value, superseded by B2 (kept for compat)
    INVENTORY_ONLY = "INVENTORY_ONLY"  # no spans; inventory record only


class ConduitCoverageOut(BaseModel):
    """Conduit row for the conduit list + map with v4 span-coverage class."""
    conduit_id: str
    conduit_name: str | None = None
    corridor: str | None = None
    conduit_type: str | None = None
    owner: str | None = None
    region: str | None = Field(default=None, description="Region of the A-end site")
    length_km: float = Field(ge=0, description="Geodesic route length (BUG-QA-066)")
    span_coverage_class: str = Field(description="See SpanCoverageClass for known values")
    segmented_km: float = Field(ge=0, description="km covered by spans (SPAN-* or BBS-*)")
    coverage_pct: float = Field(ge=0, le=100, description="100*segmented_km/length_km, capped at 100")
    site_a_id: str | None = None
    site_z_id: str | None = None
    lat_a: float | None = None
    lon_a: float | None = None
    lat_z: float | None = None
    lon_z: float | None = None


class ConduitCoverageClassCount(BaseModel):
    span_coverage_class: str
    conduit_count: int = Field(ge=0)
    length_km: float = Field(ge=0)
    segmented_km: float = Field(ge=0)


class ConduitCoverageSummaryOut(BaseModel):
    """Per-class counts for the coverage legend (live v4: 55 / 92 / 1,914)."""
    total_conduits: int = Field(ge=0)
    classes: list[ConduitCoverageClassCount]
    source_table: str = "physical_resource_conduit_v4_candidate"


# ---------------------------------------------------------------------------
# Path Trace + SRLG + Hazard Overlay (TOPOLOGY-VIS-SPEC §2, §3, §4)
# ---------------------------------------------------------------------------


class ServicePathHopOut(BaseModel):
    """Single hop in a service path trace."""
    service_id: str
    hop_index: int = Field(ge=0)
    span_id: str
    path_type: str = Field(description="working | protect")
    conduit_id: str | None = None
    span_site_a_id: str
    span_site_z_id: str
    span_length_km: float = Field(ge=0)
    fiber_type: str | None = None
    strand_count: int = Field(ge=0, default=0)
    conduit_type: str | None = None
    conduit_length_km: float = Field(ge=0, default=0)
    corridor: str | None = None
    site_a_name: str | None = None
    site_z_name: str | None = None
    site_a_region: str | None = None
    site_z_region: str | None = None


class ServiceDiversityOut(BaseModel):
    """Diversity status summary for a service."""
    service_id: str
    diversity_status: str = Field(description="fully_diverse | partially_diverse | single_path | unknown")
    working_hops: int = Field(ge=0)
    protect_hops: int = Field(ge=0)
    working_conduits: int = Field(ge=0)
    protect_conduits: int = Field(ge=0)
    # BUG-QA-080: diversity_status is derived from shared conduits + shared SRLGs.
    shared_conduit_count: int = Field(ge=0, default=0)
    shared_srlg_count: int = Field(ge=0)
    sold_as_diverse: bool | None = None
    path_diversity_score: float | None = Field(default=None, description="Latest resilience_score_snapshot.path_diversity_score (context only)")
    # P36-APP-V4-BB-SRLG-DISCLOSURE: any working/protect hop on a backbone span (BB-*/BBS-*).
    crosses_backbone: bool | None = Field(default=None, description="True if any path hop crosses a backbone span")


class SrlgMemberOut(BaseModel):
    """Single SRLG membership record for a span."""
    srlg_id: str
    srlg_type: str = Field(description="shared_conduit | bridge | rail_crossing | power_feed | tunnel | central_office")
    severity: str | None = None
    span_id: str
    description: str | None = None
    site_a_id: str
    site_z_id: str
    conduit_id: str | None = None
    span_length_km: float = Field(ge=0, default=0)
    site_a_name: str | None = None
    site_z_name: str | None = None


class HazardOverlayOut(BaseModel):
    """Active hazard for the topology overlay."""
    hazard_id: str
    hazard_type: str
    name: str
    severity: str
    latitude: float
    longitude: float
    event_start: datetime | None = None
    direct_impact_spans: int = Field(ge=0, default=0)
    near_impact_spans: int = Field(ge=0, default=0)
    advisory_spans: int = Field(ge=0, default=0)


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str = "ok"
    lakebase_connected: bool
    gold_tables_available: bool
    data_source: str  # "live" | "mock"
