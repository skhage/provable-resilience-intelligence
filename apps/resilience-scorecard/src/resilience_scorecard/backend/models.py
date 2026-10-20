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
    NOTIFY = "notify"


class ActionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


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
    dismissed_count: int
    critical_pending: int


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str = "ok"
    lakebase_connected: bool
    gold_tables_available: bool
    data_source: str  # "live" | "mock"
