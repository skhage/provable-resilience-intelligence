"""API routes for Lakelink Fiber Resilience Scorecard & Action Queue.

Scorecard data: live from Unity Catalog gold tables (8K services, 10.8K actions)
with automatic fallback to mock when warehouse is unavailable.
Action queue: Lakebase Postgres for durable state; UC for read-only listing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response

from .core import Dependencies
from .models import (
    ActionQueueSummaryOut,
    ActionStatusUpdate,
    ConduitCoverageOut,
    ConduitCoverageSummaryOut,
    FeatureFlagsOut,
    HazardCrosswalkRowOut,
    HazardCrosswalkSummaryOut,
    HazardListItemOut,
    HazardOverlayOut,
    HazardSummaryOut,
    HealthOut,
    MrcProtectedOut,
    ProactiveActionOut,
    ProductOfferingOut,
    ResilienceScoreOut,
    ResilienceSummaryOut,
    RiskDistributionOut,
    ServiceDiversityOut,
    ServicePathHopOut,
    SrlgMemberOut,
    TopologyConduitOut,
    TopologyRegionSummaryOut,
    TopologySiteOut,
)
from .services.mock_data import (
    generate_mock_actions,
    generate_mock_action_summary,
    generate_mock_conduit_coverage,
    generate_mock_conduit_coverage_summary,
    generate_mock_crosswalk,
    generate_mock_crosswalk_summary,
    generate_mock_hazard_list,
    generate_mock_hazard_summary,
    generate_mock_product_offerings,
    generate_mock_scores,
    generate_mock_summary,
)

logger = logging.getLogger("resilience_scorecard.router")

router = APIRouter(prefix="/api")

# BUG-QA-080: per-response provenance for topology live queries ('live' | 'unavailable').
DATA_SOURCE_HEADER = "X-PRI-Data-Source"

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
def get_resilience_summary(csql: Dependencies.CatalogSql, config: Dependencies.Config):
    """Aggregate resilience summary for the dashboard header."""
    summary = None
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            summary = csql.get_summary()
        except Exception:
            logger.warning("Live summary failed, falling back to mock", exc_info=True)
    if summary is None:
        summary = generate_mock_summary(generate_mock_scores())
    if getattr(config, "v4_kpis", False):
        summary = {
            **summary,
            "bb_srlg_coverage": _resolve_bb_srlg_coverage(config, csql),
            "report_status": _resolve_v4_report_status(config, csql),
        }
    return summary


def _resolve_v4_report_status(config, csql) -> str:
    """V4-KPI-COPY-SPEC §6.2 badge state. Env override wins; auto reads the attribution table.

    Conservative: the Interim badge is only removed once the report is proven FINAL
    (unknown, empty table or query failure all report INTERIM).
    """
    override = str(getattr(config, "v4_report_status", "auto") or "auto").strip().upper()
    if override in ("INTERIM", "FINAL"):
        return override
    if hasattr(csql, "is_available") and csql.is_available and hasattr(csql, "get_v4_report_status"):
        try:
            state = csql.get_v4_report_status()
            if state in ("INTERIM", "FINAL"):
                return state
        except Exception:
            logger.warning("v4 report_status query failed; reporting INTERIM", exc_info=True)
    return "INTERIM"


def _resolve_bb_srlg_coverage(config, csql) -> str:
    """V4-KPI-COPY-SPEC §2 state. Env override wins; auto derives from data; unknown = partial.

    Conservative by design: the UI only drops the backbone caveat when coverage is proven.
    """
    override = str(getattr(config, "bb_srlg_coverage", "auto") or "auto").strip().lower()
    if override in ("partial", "complete"):
        return override
    if hasattr(csql, "is_available") and csql.is_available and hasattr(csql, "get_bb_srlg_coverage"):
        try:
            state = csql.get_bb_srlg_coverage()
            if state in ("partial", "complete"):
                return state
        except Exception:
            logger.warning("BB SRLG coverage query failed; reporting partial", exc_info=True)
    return "partial"


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
# Hazard Summary (HAZARD-VIS-SPEC §6.1)
# ---------------------------------------------------------------------------


@router.get(
    "/hazards",
    response_model=list[HazardListItemOut],
    operation_id="listHazards",
)
def list_hazards(csql: Dependencies.CatalogSql):
    """List active hazard events for the hazard summary table (HAZARD-VIS-SPEC §6.2)."""
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            hazards = csql.get_hazard_list()
            if hazards is not None:
                return hazards
        except Exception:
            logger.warning("Live hazard list failed, falling back to mock", exc_info=True)

    return generate_mock_hazard_list()


@router.get(
    "/hazards/summary",
    response_model=HazardSummaryOut,
    operation_id="getHazardSummary",
)
def get_hazard_summary(csql: Dependencies.CatalogSql):
    """Hazard KPI summary: active hazards, spans at risk, services impacted, revenue exposed.

    Uses live geographic_hazard_event and hazard_span_proximity gold tables.
    Falls back to mock data when tables are unavailable.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            summary = csql.get_hazard_summary()
            if summary is not None:
                return summary
        except Exception:
            logger.warning("Live hazard summary failed, falling back to mock", exc_info=True)

    return generate_mock_hazard_summary()


# ---------------------------------------------------------------------------
# Product Offerings (P10-APP-PRODUCT-VIEW-PREP)
# ---------------------------------------------------------------------------


@router.get(
    "/products",
    response_model=list[ProductOfferingOut],
    operation_id="listProductOfferings",
)
def list_product_offerings(csql: Dependencies.CatalogSql):
    """Return Lakelink Fiber product catalog.

    Maps service_type to commercial product names, SLA tiers, and bandwidth options.
    Uses live product_offering table when available, falls back to mock.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            rows = csql.list_product_offerings()
            if rows is not None:
                return rows
        except Exception:
            logger.warning("Live product offerings failed, falling back to mock", exc_info=True)

    return generate_mock_product_offerings()


# ---------------------------------------------------------------------------
# Hazard × Span Crosswalk (P10-APP-HAZARD-XWALK-VIEW)
# ---------------------------------------------------------------------------


@router.get(
    "/hazards/crosswalk",
    response_model=list[HazardCrosswalkRowOut],
    operation_id="listHazardCrosswalk",
)
def list_hazard_crosswalk(
    csql: Dependencies.CatalogSql,
    hazard_type: str | None = Query(None, description="Filter by hazard type"),
):
    """Return hazard×span crosswalk aggregated by type × proximity band.

    Uses live hazard_span_intersection table (79K rows).
    Falls back to mock data when unavailable.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            rows = csql.get_crosswalk(hazard_type=hazard_type)
            if rows is not None:
                return rows
        except Exception:
            logger.warning("Live crosswalk failed, falling back to mock", exc_info=True)

    data = generate_mock_crosswalk()
    if hazard_type:
        data = [d for d in data if d["hazard_type"] == hazard_type]
    return data


@router.get(
    "/hazards/crosswalk/summary",
    response_model=HazardCrosswalkSummaryOut,
    operation_id="getHazardCrosswalkSummary",
)
def get_hazard_crosswalk_summary(csql: Dependencies.CatalogSql):
    """KPI summary for the hazard×span crosswalk view.

    Returns total intersections, exposure %, band breakdowns.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            summary = csql.get_crosswalk_summary()
            if summary is not None:
                return summary
        except Exception:
            logger.warning("Live crosswalk summary failed, falling back to mock", exc_info=True)

    return generate_mock_crosswalk_summary()


# ---------------------------------------------------------------------------
# Network Topology (TOPOLOGY-VIS-SPEC §10, §13)
# ---------------------------------------------------------------------------


@router.get(
    "/topology/regions",
    response_model=list[TopologyRegionSummaryOut],
    operation_id="listTopologyRegions",
)
def list_topology_regions(csql: Dependencies.CatalogSql):
    """Region-level topology summary for the overview graph.

    Returns 4 rows (West, Central, East, Southeast) with site/conduit/span counts.
    TOPOLOGY-VIS-SPEC §10.2 — initial load payload (<5KB).
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            regions = csql.get_topology_regions()
            if regions is not None:
                return regions
        except Exception:
            logger.warning("Live topology regions failed, falling back to empty", exc_info=True)

    return []


@router.get(
    "/topology/sites",
    response_model=list[TopologySiteOut],
    operation_id="listTopologySites",
)
def list_topology_sites(
    csql: Dependencies.CatalogSql,
    region: str = Query(..., description="Region name (West, Central, East, Southeast)"),
):
    """Tier-1 and tier-2 sites in a region for the drill-in view.

    TOPOLOGY-VIS-SPEC §10.2 — lazy-loaded on region drill-in.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            sites = csql.get_topology_sites(region)
            if sites is not None:
                return sites
        except Exception:
            logger.warning("Live topology sites failed for %s", region, exc_info=True)

    return []


@router.get(
    "/topology/conduits",
    response_model=list[TopologyConduitOut],
    operation_id="listTopologyConduits",
)
def list_topology_conduits(
    csql: Dependencies.CatalogSql,
    region: str = Query(..., description="Region name"),
):
    """Conduits between tier-1/tier-2 sites in a region.

    TOPOLOGY-VIS-SPEC §10.2 — lazy-loaded on region drill-in.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            conduits = csql.get_topology_conduits(region)
            if conduits is not None:
                return conduits
        except Exception:
            logger.warning("Live topology conduits failed for %s", region, exc_info=True)

    return []


# ---------------------------------------------------------------------------
# Conduit coverage list + map (P35-APP-CONDUIT-COVERAGE-BADGE)
# Reads physical_resource_conduit_v4_candidate (v4 shadow, read-only).
# ---------------------------------------------------------------------------

# BB_SEGMENTED replaced BB_ONLY in DE B2 (conduit_v4 v29). BUG-QA-078: legacy BB_ONLY deep links
# are aliased to BB_SEGMENTED (conduit_v4 has no BB_ONLY rows, so passing it through returned 0).
_COVERAGE_FILTER_VALUES = {"REAL_SEGMENTED", "BB_SEGMENTED", "BB_ONLY", "INVENTORY_ONLY", "ALL"}
_COVERAGE_FILTER_ALIASES = {"BB_ONLY": "BB_SEGMENTED"}


@router.get(
    "/conduits/coverage-summary",
    response_model=ConduitCoverageSummaryOut,
    operation_id="getConduitCoverageSummary",
)
def get_conduit_coverage_summary(csql: Dependencies.CatalogSql):
    """Per-class conduit counts for the coverage legend."""
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            summary = csql.get_conduit_coverage_summary()
            if summary is not None:
                return summary
        except Exception:
            logger.warning("Live conduit coverage summary failed", exc_info=True)
    return generate_mock_conduit_coverage_summary()


@router.get(
    "/conduits",
    response_model=list[ConduitCoverageOut],
    operation_id="listConduitCoverage",
)
def list_conduit_coverage(
    csql: Dependencies.CatalogSql,
    coverage_class: str = Query(
        "REAL_SEGMENTED",
        description="REAL_SEGMENTED (default) | BB_SEGMENTED | INVENTORY_ONLY | ALL",
    ),
    region: str | None = Query(None, description="Filter by A-end site region"),
):
    """Conduits with v4 span-coverage class. Defaults to REAL_SEGMENTED only."""
    cls = coverage_class.upper()
    if cls not in _COVERAGE_FILTER_VALUES:
        raise HTTPException(status_code=422, detail=f"Invalid coverage_class: {coverage_class}")
    cls = _COVERAGE_FILTER_ALIASES.get(cls, cls)
    cls_arg = None if cls == "ALL" else cls

    if hasattr(csql, "is_available") and csql.is_available:
        try:
            rows = csql.list_conduit_coverage(coverage_class=cls_arg, region=region)
            if rows is not None:
                return rows
        except Exception:
            logger.warning("Live conduit coverage failed", exc_info=True)

    rows = generate_mock_conduit_coverage()
    if cls_arg:
        rows = [r for r in rows if r["span_coverage_class"] == cls_arg]
    if region:
        rows = [r for r in rows if r["region"] == region]
    return rows


# ---------------------------------------------------------------------------
# Path Trace + SRLG + Hazard Overlay (TOPOLOGY-VIS-SPEC §2, §3, §4)
# ---------------------------------------------------------------------------


@router.get(
    "/topology/path-trace/{service_id}",
    response_model=list[ServicePathHopOut],
    operation_id="getServicePathTrace",
)
def get_service_path_trace(
    service_id: str,
    csql: Dependencies.CatalogSql,
    response: Response,
):
    """Return hop-by-hop path trace for a service (working + protect).

    TOPOLOGY-VIS-SPEC §2.1 — on-demand query for service path visualization.
    BUG-QA-080: X-PRI-Data-Source is 'live' or 'unavailable' (never silent).
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            hops = csql.get_service_path_trace(service_id)
            if hops is not None:
                response.headers[DATA_SOURCE_HEADER] = "live"
                return hops
        except Exception:
            logger.warning("Live path trace failed for %s", service_id, exc_info=True)
    logger.error("Path trace unavailable for %s (live query failed or warehouse down)", service_id)
    response.headers[DATA_SOURCE_HEADER] = "unavailable"
    return []


@router.get(
    "/topology/diversity/{service_id}",
    response_model=ServiceDiversityOut,
    operation_id="getServiceDiversity",
)
def get_service_diversity(
    service_id: str,
    csql: Dependencies.CatalogSql,
    response: Response,
):
    """Return diversity status for a service.

    TOPOLOGY-VIS-SPEC §2.1 — diversity classification for path coloring.
    BUG-QA-080: 503 when the live query fails (distinct from 404 not-found).
    BUG-QA-086: the service raises CatalogQueryError on a FAILED statement (or any
    exception), which lands here as 503 + header 'unavailable'. 404 is returned only
    when the query succeeded with zero rows.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            div = csql.get_service_diversity(service_id)
        except Exception:
            # Includes CatalogQueryError (FAILED/CANCELED statement or SDK error).
            logger.warning("Live diversity failed for %s", service_id, exc_info=True)
        else:
            if div is not None:
                response.headers[DATA_SOURCE_HEADER] = "live"
                return div
            raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
    raise HTTPException(
        status_code=503,
        detail="Diversity data unavailable",
        headers={DATA_SOURCE_HEADER: "unavailable"},
    )


@router.get(
    "/topology/srlgs",
    response_model=list[SrlgMemberOut],
    operation_id="listTopologySrlgs",
)
def list_topology_srlgs(
    csql: Dependencies.CatalogSql,
    response: Response,
    region: str = Query(..., description="Region name"),
):
    """Return SRLG memberships for spans in a region.

    TOPOLOGY-VIS-SPEC §3 — lazy-loaded when SRLG overlay is toggled on.
    BUG-QA-080: X-PRI-Data-Source is 'live' or 'unavailable' (never silent).
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            srlgs = csql.get_srlgs_by_region(region)
            if srlgs is not None:
                response.headers[DATA_SOURCE_HEADER] = "live"
                return srlgs
        except Exception:
            logger.warning("Live SRLGs failed for %s", region, exc_info=True)
    logger.error("SRLGs unavailable for region %s (live query failed or warehouse down)", region)
    response.headers[DATA_SOURCE_HEADER] = "unavailable"
    return []


@router.get(
    "/topology/hazards",
    response_model=list[HazardOverlayOut],
    operation_id="listTopologyHazards",
)
def list_topology_hazards(csql: Dependencies.CatalogSql):
    """Return active hazards for the topology overlay.

    TOPOLOGY-VIS-SPEC §4 — lazy-loaded when hazard overlay is toggled on.
    """
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            hazards = csql.get_hazard_overlay()
            if hazards is not None:
                return hazards
        except Exception:
            logger.warning("Live hazard overlay failed", exc_info=True)
    return []


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


# ---------------------------------------------------------------------------
# V4 KPIs (V4-KPI-COPY-SPEC §0/§1) — gated by PRI_V4_KPIS, default off.
# ---------------------------------------------------------------------------


@router.get(
    "/config/features",
    response_model=FeatureFlagsOut,
    operation_id="getFeatureFlags",
)
def get_feature_flags(config: Dependencies.Config):
    """UI feature flags. v4_kpis=False keeps the PRI-DEMO-FREEZE-v3 UI."""
    return {"v4_kpis": bool(getattr(config, "v4_kpis", False))}


@router.get(
    "/actions/mrc-protected",
    response_model=MrcProtectedOut,
    operation_id="getMrcProtected",
)
def get_mrc_protected(config: Dependencies.Config, csql: Dependencies.CatalogSql):
    """MRC Protected: MRC of distinct services with >=1 completed proactive action.

    404 when PRI_V4_KPIS is off. 503 when the measure is unavailable or null:
    no mock fallback, because the UI must hide the card rather than show $0 or a fake value.
    """
    if not getattr(config, "v4_kpis", False):
        raise HTTPException(status_code=404, detail="Not found")
    if hasattr(csql, "is_available") and csql.is_available:
        try:
            result = csql.get_mrc_protected()
            if result is not None:
                return result
        except Exception:
            logger.warning("MRC Protected query failed", exc_info=True)
    raise HTTPException(status_code=503, detail="MRC Protected unavailable")


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
