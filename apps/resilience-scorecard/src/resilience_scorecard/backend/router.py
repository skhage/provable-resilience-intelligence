"""API routes for Lakelink Fiber Resilience Scorecard & Action Queue.

Scorecard data: live from Unity Catalog gold tables (8K services, 10.8K actions)
with automatic fallback to mock when warehouse is unavailable.
Action queue: Lakebase Postgres for durable state; UC for read-only listing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from .core import Dependencies
from .models import (
    ActionQueueSummaryOut,
    ActionStatusUpdate,
    HealthOut,
    ProactiveActionOut,
    ResilienceScoreOut,
    ResilienceSummaryOut,
    RiskDistributionOut,
)
from .services.mock_data import (
    generate_mock_actions,
    generate_mock_action_summary,
    generate_mock_scores,
    generate_mock_summary,
)

logger = logging.getLogger("resilience_scorecard.router")

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthOut, operation_id="getHealth")
def health(lb: Dependencies.LakebaseClient, csql: Dependencies.CatalogSql):
    """Readiness probe — reports Lakebase connectivity and data source."""
    gold_available = hasattr(csql, "is_available") and csql.is_available
    return HealthOut(
        status="ok",
        lakebase_connected=lb.is_connected if hasattr(lb, "is_connected") else False,
        gold_tables_available=gold_available,
        data_source="live" if gold_available else "mock",
    )


# ---------------------------------------------------------------------------
# Resilience Scorecard
# ---------------------------------------------------------------------------


@router.get(
    "/scores",
    response_model=list[ResilienceScoreOut],
    operation_id="listResilienceScores",
)
def list_resilience_scores(
    csql: Dependencies.CatalogSql,
    min_score: float | None = Query(None, ge=0, le=100, description="Min resilience score filter"),
    max_score: float | None = Query(None, ge=0, le=100, description="Max resilience score filter"),
    customer_id: str | None = Query(None, description="Filter by customer ID"),
    sort_by: str = Query("resilience_score", description="Sort field"),
    sort_dir: str = Query("asc", description="asc or desc"),
):
    """Return resilience score snapshots.

    Uses live Unity Catalog gold tables (8K services) when available,
    falls back to mock data otherwise.
    """
    scores = None
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            scores = csql.list_scores(
                min_score=min_score, max_score=max_score, customer_id=customer_id
            )
        except Exception:
            logger.warning("Live scores failed, falling back to mock", exc_info=True)

    if scores is None:
        scores = generate_mock_scores()
        if min_score is not None:
            scores = [s for s in scores if s["resilience_score"] >= min_score]
        if max_score is not None:
            scores = [s for s in scores if s["resilience_score"] <= max_score]
        if customer_id:
            scores = [s for s in scores if s["customer_id"] == customer_id]

    # Sort
    reverse = sort_dir == "desc"
    scores.sort(key=lambda s: s.get(sort_by, 0), reverse=reverse)

    return scores


@router.get(
    "/scores/summary",
    response_model=ResilienceSummaryOut,
    operation_id="getResilienceSummary",
)
def get_resilience_summary(csql: Dependencies.CatalogSql):
    """Aggregate resilience summary for the dashboard header."""
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            summary = csql.get_summary()
            if summary is not None:
                return summary
        except Exception:
            logger.warning("Live summary failed, falling back to mock", exc_info=True)

    scores = generate_mock_scores()
    return generate_mock_summary(scores)


@router.get(
    "/scores/risk-distribution",
    response_model=list[RiskDistributionOut],
    operation_id="getRiskDistribution",
)
def get_risk_distribution(csql: Dependencies.CatalogSql):
    """Risk breakdown by physical, network, and environmental categories."""
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            dist = csql.get_risk_distribution()
            if dist is not None:
                return dist
        except Exception:
            logger.warning("Live risk dist failed, falling back to mock", exc_info=True)

    scores = generate_mock_scores()
    total = len(scores) or 1

    categories = {
        "Physical Redundancy": [s["physical_redundancy_score"] for s in scores],
        "Network Health": [s["network_health_score"] for s in scores],
        "Environmental Risk": [s["environmental_risk_score"] for s in scores],
    }

    result = []
    for cat, vals in categories.items():
        at_risk = sum(1 for v in vals if v < 60)
        result.append(RiskDistributionOut(
            category=cat,
            count=at_risk,
            percentage=round(at_risk / total * 100, 1),
        ))

    return result


@router.get(
    "/scores/{service_id}",
    response_model=ResilienceScoreOut,
    operation_id="getServiceScore",
)
def get_service_score(service_id: str, csql: Dependencies.CatalogSql):
    """Get resilience score for a single service."""
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            result = csql.get_service_score(service_id)
            if result is not None:
                return result
        except Exception:
            logger.warning("Live service score failed, falling back to mock", exc_info=True)

    scores = generate_mock_scores()
    for s in scores:
        if s["service_id"] == service_id:
            return s
    raise HTTPException(status_code=404, detail=f"Service {service_id} not found")


# ---------------------------------------------------------------------------
# Proactive Action Queue (Lakebase-backed)
# ---------------------------------------------------------------------------


@router.get(
    "/actions",
    response_model=list[ProactiveActionOut],
    operation_id="listActions",
)
def list_actions(
    lb: Dependencies.LakebaseClient,
    csql: Dependencies.CatalogSql,
    status_filter: str | None = Query(None, description="Filter by action status"),
    priority_filter: str | None = Query(None, description="Filter by priority"),
):
    """List proactive actions from the queue.

    If Lakebase is connected, reads from proactive_actions table.
    Falls back to mock data otherwise.
    """
    # Priority: Lakebase (stateful) → UC gold tables (read-only) → mock
    try:
        if hasattr(lb, "is_connected") and lb.is_connected:
            result = lb.list_actions(status_filter=status_filter, priority_filter=priority_filter)
            if result:
                return result
    except Exception:
        logger.warning("Lakebase read failed", exc_info=True)

    try:
        if hasattr(csql, "is_available") and csql.is_available:
            result = csql.list_actions(status_filter=status_filter, priority_filter=priority_filter)
            if result is not None:
                return result
    except Exception:
        logger.warning("UC action read failed, falling back to mock", exc_info=True)

    # Fallback to mock
    actions = generate_mock_actions()
    if status_filter:
        actions = [a for a in actions if a["status"] == status_filter]
    if priority_filter:
        actions = [a for a in actions if a["priority"] == priority_filter]
    return actions


@router.get(
    "/actions/summary",
    response_model=ActionQueueSummaryOut,
    operation_id="getActionSummary",
)
def get_action_summary(lb: Dependencies.LakebaseClient, csql: Dependencies.CatalogSql):
    """Aggregate action queue counts."""
    try:
        if hasattr(lb, "is_connected") and lb.is_connected:
            return lb.get_queue_summary()
    except Exception:
        logger.warning("Lakebase summary failed", exc_info=True)

    try:
        if hasattr(csql, "is_available") and csql.is_available:
            summary = csql.get_action_summary()
            if summary is not None:
                return summary
    except Exception:
        logger.warning("UC action summary failed, falling back to mock", exc_info=True)

    actions = generate_mock_actions()
    return generate_mock_action_summary(actions)


@router.patch(
    "/actions/{action_id}",
    response_model=ProactiveActionOut,
    operation_id="updateActionStatus",
)
def update_action_status(
    action_id: str,
    update: ActionStatusUpdate,
    lb: Dependencies.LakebaseClient,
):
    """Update an action's status (Lakebase write)."""
    try:
        if hasattr(lb, "is_connected") and lb.is_connected:
            result = lb.update_action_status(
                action_id=action_id,
                status=update.status.value,
                resolution_notes=update.resolution_notes,
                assigned_to=update.assigned_to,
            )
            if result is None:
                raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
            return result
    except HTTPException:
        raise
    except Exception:
        logger.warning("Lakebase write failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Lakebase unavailable — action not updated")


@router.get(
    "/actions/{action_id}",
    response_model=ProactiveActionOut,
    operation_id="getAction",
)
def get_action(action_id: str, lb: Dependencies.LakebaseClient):
    """Get a single action by ID."""
    try:
        if hasattr(lb, "is_connected") and lb.is_connected:
            result = lb.get_action(action_id)
            if result:
                return result
    except Exception:
        pass

    # Fallback to mock
    for a in generate_mock_actions():
        if a["action_id"] == action_id:
            return a
    raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
