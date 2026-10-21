"""Pydantic models for the Lakelink Fiber Resilience Scorecard & Action Queue."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

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
# Health / readiness
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str = "ok"
    lakebase_connected: bool
    gold_tables_available: bool
    data_source: str  # "live" | "mock"
