"""Unity Catalog SQL service for live resilience scorecard data.

Queries gold tables via Databricks SDK Statement Execution API:
  - resilience_score_snapshot (8K scores)
  - service_inventory (service metadata)
  - customer (enterprise customer info)
  - geographic_site (A/Z endpoint cities for service names)
  - proactive_action (10.8K actions)

Falls back gracefully if the warehouse is unavailable or tables are missing.
Branding: Lakelink Fiber (never Lumen).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import (
    ColumnInfoTypeName,
    StatementParameterListItem,
    StatementState,
)

if TYPE_CHECKING:
    from ..core import AppConfig

logger = logging.getLogger("resilience_scorecard.catalog_sql")

# ---------------------------------------------------------------------------
# Rating helpers (match mock_data.py exactly)
# ---------------------------------------------------------------------------

_RATING_MAP = [
    (85, 100, "A"),
    (70, 85, "B"),
    (55, 70, "C"),
    (40, 55, "D"),
    (0, 40, "F"),
]


def _score_to_rating(score: float) -> str:
    for lo, hi, rating in _RATING_MAP:
        if lo <= score < hi:
            return rating
    return "A" if score >= 85 else "F"


def _risk_level(score: float) -> str:
    if score < 40:
        return "critical"
    if score < 60:
        return "high"
    if score < 75:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# SQL Queries
# ---------------------------------------------------------------------------

_SCORES_SQL = """
SELECT
  r.service_id,
  CASE
    WHEN ga.city IS NOT NULL AND gz.city IS NOT NULL
    THEN CONCAT(ga.city, '\u2013', gz.city, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
    ELSE CONCAT(r.service_id, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
  END AS service_name,
  s.customer_id,
  c.customer_name,
  ROUND(r.overall_score, 1)            AS resilience_score,
  ROUND(r.path_diversity_score, 1)     AS physical_redundancy_score,
  ROUND(r.telemetry_health_score, 1)   AS network_health_score,
  ROUND(r.hazard_exposure_score, 1)    AS environmental_risk_score,
  r.srlg_count,
  r.active_alarms                      AS single_point_failures,
  r.score_time                         AS snapshot_timestamp,
  ROUND(r.revenue_at_risk_usd, 2)      AS revenue_at_risk_usd
FROM resilience_score_snapshot r
JOIN service_inventory s        ON r.service_id = s.service_id
JOIN customer c                 ON s.customer_id = c.customer_id
LEFT JOIN geographic_site ga    ON s.site_a_id   = ga.site_id
LEFT JOIN geographic_site gz    ON s.site_z_id   = gz.site_id
ORDER BY r.overall_score ASC
"""

_SUMMARY_SQL = """
SELECT
  COUNT(*)                                           AS total_services,
  ROUND(AVG(r.overall_score), 1)                     AS avg_resilience_score,
  SUM(CASE WHEN r.overall_score <  40 THEN 1 ELSE 0 END) AS critical_count,
  SUM(CASE WHEN r.overall_score >= 40 AND r.overall_score < 60 THEN 1 ELSE 0 END) AS high_risk_count,
  SUM(CASE WHEN r.overall_score >= 60 AND r.overall_score < 75 THEN 1 ELSE 0 END) AS medium_risk_count,
  SUM(CASE WHEN r.overall_score >= 75 THEN 1 ELSE 0 END)  AS low_risk_count,
  CAST(SUM(r.active_alarms) AS BIGINT)               AS total_single_point_failures,
  (SELECT CAST(COUNT(DISTINCT srlg_id) AS INT) FROM shared_risk_group) AS total_srlg_groups,
  ROUND(SUM(r.revenue_at_risk_usd), 2)               AS total_revenue_at_risk_usd
FROM resilience_score_snapshot r
"""

_RISK_DISTRIBUTION_SQL = """
SELECT
  'Physical Redundancy' AS category,
  SUM(CASE WHEN r.path_diversity_score < 60 THEN 1 ELSE 0 END)   AS at_risk_count,
  COUNT(*)                                                         AS total
FROM resilience_score_snapshot r
UNION ALL
SELECT
  'Network Health',
  SUM(CASE WHEN r.telemetry_health_score < 60 THEN 1 ELSE 0 END),
  COUNT(*)
FROM resilience_score_snapshot r
UNION ALL
SELECT
  'Environmental Risk',
  SUM(CASE WHEN r.hazard_exposure_score < 60 THEN 1 ELSE 0 END),
  COUNT(*)
FROM resilience_score_snapshot r
"""

_HAZARD_LIST_SQL = """
SELECT
  h.hazard_id,
  h.hazard_type,
  COALESCE(h.description, CONCAT(UPPER(REPLACE(h.hazard_type, '_', ' ')), ' near ', ROUND(h.latitude, 2), ', ', ROUND(h.longitude, 2))) AS name,
  COALESCE(h.severity, 'medium') AS severity,
  CONCAT(ROUND(h.latitude, 2), '\u00b0N, ', ROUND(ABS(h.longitude), 2), '\u00b0W') AS location,
  COALESCE(hz_cnt.spans_affected, 0) AS spans_affected,
  CASE WHEN h.event_end IS NULL THEN TRUE ELSE FALSE END AS is_active,
  COALESCE(h.created_at, h.event_start) AS last_update
FROM geographic_hazard_event h
LEFT JOIN (
  SELECT hazard_id, CAST(COUNT(DISTINCT span_id) AS INT) AS spans_affected
  FROM hazard_span_proximity
  WHERE distance_km < 25
  GROUP BY hazard_id
) hz_cnt ON hz_cnt.hazard_id = h.hazard_id
WHERE h.event_end IS NULL
ORDER BY
  CASE COALESCE(h.severity, 'medium')
    WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
  COALESCE(h.created_at, h.event_start) DESC
LIMIT 200
"""

_HAZARD_SUMMARY_SQL = """
SELECT
  (SELECT COUNT(*) FROM geographic_hazard_event WHERE event_end IS NULL) AS active_hazards,
  (SELECT COUNT(DISTINCT p.span_id)
   FROM hazard_span_proximity p
   JOIN geographic_hazard_event h ON p.hazard_id = h.hazard_id
   WHERE h.event_end IS NULL AND p.distance_km < 5) AS spans_at_risk,
  (SELECT COUNT(DISTINCT sp.service_id)
   FROM hazard_span_proximity p
   JOIN geographic_hazard_event h ON p.hazard_id = h.hazard_id
   JOIN service_path sp ON p.span_id = sp.span_id
   WHERE h.event_end IS NULL AND p.distance_km < 5) AS services_impacted,
  (SELECT COALESCE(ROUND(SUM(si.mrc_usd * 12), 2), 0)
   FROM service_inventory si
   WHERE si.service_id IN (
     SELECT DISTINCT sp.service_id
     FROM hazard_span_proximity p
     JOIN geographic_hazard_event h ON p.hazard_id = h.hazard_id
     JOIN service_path sp ON p.span_id = sp.span_id
     WHERE h.event_end IS NULL AND p.distance_km < 5
   )) AS revenue_exposed_usd
"""

_PRODUCT_OFFERINGS_SQL = """
SELECT
  product_offering_id,
  service_type,
  product_name,
  product_category,
  network_technology,
  technology_domain,
  sla_tier_default,
  bandwidth_options,
  is_diverse_eligible,
  mrc_range_usd
FROM product_offering
ORDER BY product_category, service_type
"""

_PRODUCT_OFFERINGS_SQL = """
SELECT
  product_offering_id,
  service_type,
  product_name,
  product_category,
  network_technology,
  technology_domain,
  sla_tier_default,
  bandwidth_options,
  is_diverse_eligible,
  mrc_range_usd
FROM product_offering
ORDER BY product_category, service_type
"""

_CROSSWALK_SQL = """
SELECT
  hazard_type,
  proximity_band,
  CAST(COUNT(*) AS INT) AS intersection_count,
  CAST(COUNT(DISTINCT span_id) AS INT) AS distinct_spans,
  ROUND(AVG(affected_service_cnt), 1) AS avg_services_per_span,
  ROUND(AVG(distance_km), 2) AS avg_distance_km
FROM hazard_span_intersection
GROUP BY hazard_type, proximity_band
ORDER BY hazard_type,
  CASE proximity_band
    WHEN 'direct_impact' THEN 1
    WHEN 'near_field' THEN 2
    WHEN 'buffer_zone' THEN 3
  END
"""

_CROSSWALK_SUMMARY_SQL = """
SELECT
  CAST(COUNT(*) AS INT) AS total_intersections,
  CAST(COUNT(DISTINCT span_id) AS INT) AS distinct_spans_exposed,
  (SELECT CAST(COUNT(*) AS INT) FROM physical_resource_span) AS total_spans,
  CAST(SUM(CASE WHEN proximity_band = 'direct_impact' THEN 1 ELSE 0 END) AS INT) AS direct_impact_count,
  CAST(SUM(CASE WHEN proximity_band = 'near_field' THEN 1 ELSE 0 END) AS INT) AS near_field_count,
  CAST(SUM(CASE WHEN proximity_band = 'buffer_zone' THEN 1 ELSE 0 END) AS INT) AS buffer_zone_count,
  CAST(COUNT(DISTINCT hazard_type) AS INT) AS hazard_types
FROM hazard_span_intersection
"""

# ---------------------------------------------------------------------------
# Topology SQL (TOPOLOGY-VIS-SPEC §10, §13)
# ---------------------------------------------------------------------------

_TOPOLOGY_REGIONS_SQL = """
SELECT
  s.region,
  CAST(COUNT(*) AS INT) AS site_count,
  CAST(SUM(CASE WHEN s.tier = 'tier_1' THEN 1 ELSE 0 END) AS INT) AS tier_1_count,
  CAST(SUM(CASE WHEN s.tier = 'tier_2' THEN 1 ELSE 0 END) AS INT) AS tier_2_count,
  CAST(SUM(CASE WHEN s.tier = 'tier_3' THEN 1 ELSE 0 END) AS INT) AS tier_3_count,
  CAST(SUM(CASE WHEN s.site_type = 'central_office' THEN 1 ELSE 0 END) AS INT) AS co_count,
  CAST(SUM(CASE WHEN s.site_type = 'data_center' THEN 1 ELSE 0 END) AS INT) AS dc_count,
  COALESCE(rc.conduit_count, 0) AS conduit_count,
  COALESCE(rs.span_count, 0) AS span_count
FROM geographic_site s
LEFT JOIN (
  SELECT sa.region, CAST(COUNT(DISTINCT c.conduit_id) AS INT) AS conduit_count
  FROM physical_resource_conduit c
  JOIN geographic_site sa ON c.site_a_id = sa.site_id
  WHERE c.is_active = TRUE
  GROUP BY sa.region
) rc ON rc.region = s.region
LEFT JOIN (
  SELECT sa.region, CAST(COUNT(DISTINCT sp.span_id) AS INT) AS span_count
  FROM physical_resource_span sp
  JOIN geographic_site sa ON sp.site_a_id = sa.site_id
  WHERE sp.is_active = TRUE
  GROUP BY sa.region
) rs ON rs.region = s.region
WHERE s.is_active = TRUE
GROUP BY s.region, rc.conduit_count, rs.span_count
ORDER BY s.region
"""

_TOPOLOGY_SITES_SQL = """
SELECT
  s.site_id,
  s.site_name,
  s.site_type,
  s.clli_code,
  s.latitude,
  s.longitude,
  s.city,
  s.state,
  s.region,
  s.tier,
  CAST(COALESCE(ca.cnt, 0) + COALESCE(cz.cnt, 0) AS INT) AS conduit_count
FROM geographic_site s
LEFT JOIN (
  SELECT site_a_id AS sid, COUNT(*) AS cnt
  FROM physical_resource_conduit WHERE is_active = TRUE
  GROUP BY site_a_id
) ca ON ca.sid = s.site_id
LEFT JOIN (
  SELECT site_z_id AS sid, COUNT(*) AS cnt
  FROM physical_resource_conduit WHERE is_active = TRUE
  GROUP BY site_z_id
) cz ON cz.sid = s.site_id
WHERE s.is_active = TRUE AND s.region = :region
  AND s.tier IN ('tier_1', 'tier_2')
ORDER BY s.tier, s.site_name
"""

_TOPOLOGY_CONDUITS_SQL = """
SELECT
  c.conduit_id,
  c.conduit_name,
  c.corridor,
  c.conduit_type,
  ROUND(c.length_km, 1) AS length_km,
  c.site_a_id,
  c.site_z_id,
  CAST(COALESCE(sp_cnt.cnt, 0) AS INT) AS span_count
FROM physical_resource_conduit c
JOIN geographic_site sa ON c.site_a_id = sa.site_id
JOIN geographic_site sz ON c.site_z_id = sz.site_id
LEFT JOIN (
  SELECT conduit_id, COUNT(*) AS cnt
  FROM physical_resource_span WHERE is_active = TRUE
  GROUP BY conduit_id
) sp_cnt ON sp_cnt.conduit_id = c.conduit_id
WHERE c.is_active = TRUE
  AND (sa.region = :region OR sz.region = :region)
  AND sa.tier IN ('tier_1', 'tier_2')
  AND sz.tier IN ('tier_1', 'tier_2')
ORDER BY c.length_km DESC
"""

# P35-APP-CONDUIT-COVERAGE-BADGE: v4 shadow conduit table (READ-ONLY).
# span_coverage_class / segmented_km / coverage_pct landed in DE S35 (v21); B2 (v29) replaced
# BB_ONLY with BB_SEGMENTED (92 CDT-BBR-* conduits). BB_ONLY kept in the allow-list for compat.
# The v3 FROZEN physical_resource_conduit used by /topology is untouched.
_CONDUIT_COVERAGE_TABLE = "physical_resource_conduit_v4_candidate"

# P36-APP-V4-MRC-PROTECTED-KPI: v4 candidate metric view (renamed by @data-analyst at cutover,
# P30-DA-GENIE-MRC-PROTECTED-CUTOVER; update this constant then).
_MRC_PROTECTED_VIEW = "mv_mrc_protected_v4_candidate"
_MRC_PROTECTED_SQL = f"""
SELECT
  MEASURE(`MRC Protected USD`)  AS mrc_protected_usd,
  MEASURE(`Services Protected`) AS services_protected,
  MEASURE(`MRC Protected Share`) AS mrc_share,
  MEASURE(`Total MRC USD`)      AS total_mrc_usd,
  MEASURE(`Total Services`)     AS total_services
FROM {_MRC_PROTECTED_VIEW}
"""
_CONDUIT_COVERAGE_CLASSES = ("REAL_SEGMENTED", "BB_SEGMENTED", "BB_ONLY", "INVENTORY_ONLY")

_CONDUIT_COVERAGE_SQL = f"""
SELECT
  c.conduit_id,
  c.conduit_name,
  c.corridor,
  c.conduit_type,
  c.owner,
  sa.region,
  ROUND(c.length_km, 1)    AS length_km,
  c.span_coverage_class,
  ROUND(c.segmented_km, 1) AS segmented_km,
  c.coverage_pct,
  c.site_a_id,
  c.site_z_id,
  sa.latitude  AS lat_a,
  sa.longitude AS lon_a,
  sz.latitude  AS lat_z,
  sz.longitude AS lon_z
FROM {_CONDUIT_COVERAGE_TABLE} c
LEFT JOIN geographic_site sa ON c.site_a_id = sa.site_id
LEFT JOIN geographic_site sz ON c.site_z_id = sz.site_id
WHERE c.is_active = TRUE {{where}}
ORDER BY c.length_km DESC
"""

_CONDUIT_COVERAGE_SUMMARY_SQL = f"""
SELECT
  span_coverage_class,
  CAST(COUNT(*) AS INT)          AS conduit_count,
  ROUND(SUM(length_km), 1)       AS length_km,
  ROUND(SUM(segmented_km), 1)    AS segmented_km
FROM {_CONDUIT_COVERAGE_TABLE}
WHERE is_active = TRUE
GROUP BY span_coverage_class
"""

# ---------------------------------------------------------------------------
# Path Trace + SRLG + Hazard Overlay SQL (TOPOLOGY-VIS-SPEC §2, §3, §4)
# ---------------------------------------------------------------------------

_SERVICE_PATH_TRACE_SQL = """
SELECT
  sp.service_id,
  sp.hop_index,
  sp.span_id,
  sp.path_type,
  prs.conduit_id,
  prs.site_a_id AS span_site_a_id,
  prs.site_z_id AS span_site_z_id,
  ROUND(prs.length_km, 1) AS span_length_km,
  prs.fiber_type,
  prs.strand_count,
  prc.conduit_type,
  ROUND(prc.length_km, 1) AS conduit_length_km,
  prc.corridor,
  sa.site_name AS site_a_name,
  sz.site_name AS site_z_name,
  sa.region AS site_a_region,
  sz.region AS site_z_region
FROM service_path sp
JOIN physical_resource_span prs ON sp.span_id = prs.span_id
LEFT JOIN physical_resource_conduit prc ON prs.conduit_id = prc.conduit_id
LEFT JOIN geographic_site sa ON prs.site_a_id = sa.site_id
LEFT JOIN geographic_site sz ON prs.site_z_id = sz.site_id
WHERE sp.service_id = :service_id
ORDER BY sp.path_type, sp.hop_index
"""

_SERVICE_DIVERSITY_SQL = """
SELECT
  si.service_id,
  si.path_diversity_status,
  COUNT(DISTINCT CASE WHEN sp.path_type = 'working' THEN sp.span_id END) AS working_hops,
  COUNT(DISTINCT CASE WHEN sp.path_type = 'protect' THEN sp.span_id END) AS protect_hops,
  COUNT(DISTINCT CASE WHEN sp.path_type = 'working' THEN prs.conduit_id END) AS working_conduits,
  COUNT(DISTINCT CASE WHEN sp.path_type = 'protect' THEN prs.conduit_id END) AS protect_conduits,
  (
    SELECT COUNT(DISTINCT srg.srlg_id)
    FROM shared_risk_group srg
    JOIN service_path sp2 ON srg.span_id = sp2.span_id
    WHERE sp2.service_id = si.service_id AND sp2.path_type = 'working'
    AND srg.srlg_id IN (
      SELECT srg2.srlg_id FROM shared_risk_group srg2
      JOIN service_path sp3 ON srg2.span_id = sp3.span_id
      WHERE sp3.service_id = si.service_id AND sp3.path_type = 'protect'
    )
  ) AS shared_srlg_count
FROM service_inventory si
LEFT JOIN service_path sp ON si.service_id = sp.service_id
LEFT JOIN physical_resource_span prs ON sp.span_id = prs.span_id
WHERE si.service_id = :service_id
GROUP BY si.service_id, si.path_diversity_status
"""

_SRLG_BY_REGION_SQL = """
SELECT
  srg.srlg_id,
  srg.srlg_type,
  srg.severity,
  srg.span_id,
  srg.description,
  prs.site_a_id,
  prs.site_z_id,
  prs.conduit_id,
  ROUND(prs.length_km, 1) AS span_length_km,
  sa.site_name AS site_a_name,
  sz.site_name AS site_z_name
FROM shared_risk_group srg
JOIN physical_resource_span prs ON srg.span_id = prs.span_id AND prs.is_active = TRUE
JOIN geographic_site sa ON prs.site_a_id = sa.site_id
JOIN geographic_site sz ON prs.site_z_id = sz.site_id
WHERE (sa.region = :region OR sz.region = :region)
  AND sa.tier IN ('tier_1', 'tier_2')
  AND sz.tier IN ('tier_1', 'tier_2')
ORDER BY
  CASE srg.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
  srg.srlg_type
LIMIT 500
"""

_HAZARD_OVERLAY_SQL = """
SELECT
  h.hazard_id,
  h.hazard_type,
  COALESCE(h.description, CONCAT(UPPER(REPLACE(h.hazard_type, '_', ' ')), ' near ', ROUND(h.latitude, 2), ', ', ROUND(h.longitude, 2))) AS name,
  COALESCE(h.severity, 'medium') AS severity,
  h.latitude,
  h.longitude,
  h.event_start,
  COALESCE(hsp.direct_count, 0) AS direct_impact_spans,
  COALESCE(hsp.near_count, 0) AS near_impact_spans,
  COALESCE(hsp.advisory_count, 0) AS advisory_spans
FROM geographic_hazard_event h
LEFT JOIN (
  SELECT
    p.hazard_id,
    CAST(SUM(CASE WHEN p.distance_km < 5 THEN 1 ELSE 0 END) AS INT) AS direct_count,
    CAST(SUM(CASE WHEN p.distance_km >= 5 AND p.distance_km < 25 THEN 1 ELSE 0 END) AS INT) AS near_count,
    CAST(SUM(CASE WHEN p.distance_km >= 25 AND p.distance_km < 100 THEN 1 ELSE 0 END) AS INT) AS advisory_count
  FROM hazard_span_proximity p
  GROUP BY p.hazard_id
) hsp ON hsp.hazard_id = h.hazard_id
WHERE h.event_end IS NULL
ORDER BY
  CASE COALESCE(h.severity, 'medium') WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END
LIMIT 100
"""

_ACTIONS_SQL = """
SELECT
  a.action_id,
  a.action_type,
  a.service_id,
  CASE
    WHEN ga.city IS NOT NULL AND gz.city IS NOT NULL
    THEN CONCAT(ga.city, '\u2013', gz.city, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
    ELSE CONCAT(a.service_id, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
  END AS service_name,
  a.trigger_reason     AS risk_trigger,
  a.priority,
  a.status,
  a.assigned_to,
  a.trigger_reason     AS description,
  a.resolution_notes,
  a.created_at,
  COALESCE(a.resolved_at, a.created_at) AS updated_at,
  -- Hazard context (HAZARD-VIS-SPEC §5) via span_id → nearest active hazard
  hz.hazard_type,
  hz.description       AS hazard_name,
  hz.severity          AS hazard_severity,
  hz_cnt.spans_affected AS hazard_spans_affected,
  hz.latitude          AS hazard_latitude,
  hz.longitude         AS hazard_longitude,
  hz.created_at        AS hazard_last_update
FROM proactive_action a
JOIN service_inventory s       ON a.service_id = s.service_id
LEFT JOIN geographic_site ga   ON s.site_a_id  = ga.site_id
LEFT JOIN geographic_site gz   ON s.site_z_id  = gz.site_id
LEFT JOIN (
  SELECT p.span_id, p.hazard_id,
         ROW_NUMBER() OVER (PARTITION BY p.span_id ORDER BY p.distance_km) AS rn
  FROM hazard_span_proximity p
  JOIN geographic_hazard_event h ON p.hazard_id = h.hazard_id
  WHERE h.event_end IS NULL AND p.distance_km < 25
) nearest_hz ON nearest_hz.span_id = a.span_id AND nearest_hz.rn = 1
LEFT JOIN geographic_hazard_event hz ON nearest_hz.hazard_id = hz.hazard_id
LEFT JOIN (
  SELECT hazard_id, CAST(COUNT(DISTINCT span_id) AS INT) AS spans_affected
  FROM hazard_span_proximity
  WHERE distance_km < 25
  GROUP BY hazard_id
) hz_cnt ON hz_cnt.hazard_id = nearest_hz.hazard_id
ORDER BY
  CASE a.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
  a.created_at DESC
"""


# ---------------------------------------------------------------------------
# CatalogSqlService
# ---------------------------------------------------------------------------

class CatalogSqlService:
    """Reads resilience scorecard data from Unity Catalog gold tables."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._w: WorkspaceClient | None = None
        self._available = False
        self._init()

    def _init(self) -> None:
        try:
            self._w = WorkspaceClient()
            # Quick connectivity test — query row count
            result = self._execute(
                "SELECT COUNT(*) AS cnt FROM resilience_score_snapshot"
            )
            if result and result[0]["cnt"] > 0:
                self._available = True
                logger.info(
                    "CatalogSqlService ready — %d scores in gold tables",
                    result[0]["cnt"],
                )
            else:
                logger.warning("Gold tables empty — falling back to mock")
        except Exception:
            logger.warning(
                "CatalogSqlService init failed — falling back to mock",
                exc_info=True,
            )

    @property
    def is_available(self) -> bool:
        return self._available

    def _execute(
        self,
        sql: str,
        row_limit: int = 12000,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Execute SQL via Statement Execution API and return rows as dicts.

        BUG-QA-077: user-supplied values MUST be passed in ``params`` and referenced as
        ``:name`` markers in the SQL. Never interpolate them into the statement text.
        """
        if self._w is None:
            return None
        try:
            parameters = (
                [StatementParameterListItem(name=k, value=v, type="STRING") for k, v in params.items()]
                if params
                else None
            )
            resp = self._w.statement_execution.execute_statement(
                warehouse_id=self._config.warehouse_id,
                statement=sql,
                catalog=self._config.catalog,
                schema=self._config.schema_name,
                wait_timeout="50s",
                row_limit=row_limit,
                parameters=parameters,
            )
            if resp.status and resp.status.state == StatementState.SUCCEEDED:
                cols = [c.name for c in resp.manifest.schema.columns]
                rows = []
                if resp.result and resp.result.data_array:
                    for raw_row in resp.result.data_array:
                        row = {}
                        for i, col in enumerate(cols):
                            val = raw_row[i]
                            # Parse numeric types — API returns all values as strings
                            col_type = resp.manifest.schema.columns[i].type_name
                            if val is not None and col_type in (
                                ColumnInfoTypeName.INT,
                                ColumnInfoTypeName.LONG,
                                ColumnInfoTypeName.SHORT,
                            ):
                                row[col] = int(val)
                            elif val is not None and col_type in (
                                ColumnInfoTypeName.DOUBLE,
                                ColumnInfoTypeName.FLOAT,
                                ColumnInfoTypeName.DECIMAL,
                            ):
                                row[col] = float(val)
                            else:
                                row[col] = val
                        rows.append(row)
                return rows
            else:
                logger.warning(
                    "Statement failed: %s",
                    resp.status.error if resp.status else "unknown",
                )
                return None
        except Exception:
            logger.warning("SQL execution failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Scorecard endpoints
    # ------------------------------------------------------------------

    def list_scores(
        self,
        min_score: float | None = None,
        max_score: float | None = None,
        customer_id: str | None = None,
    ) -> list[dict] | None:
        """Return all resilience scores with service/customer info."""
        rows = self._execute(_SCORES_SQL)
        if rows is None:
            return None

        # Enrich with computed fields
        for r in rows:
            score = r.get("resilience_score", 0) or 0
            r["path_diversity_rating"] = _score_to_rating(score)

        # Apply filters
        if min_score is not None:
            rows = [r for r in rows if (r.get("resilience_score") or 0) >= min_score]
        if max_score is not None:
            rows = [r for r in rows if (r.get("resilience_score") or 0) <= max_score]
        if customer_id:
            rows = [r for r in rows if r.get("customer_id") == customer_id]

        return rows

    def get_summary(self) -> dict | None:
        """Return aggregate summary from all services."""
        rows = self._execute(_SUMMARY_SQL)
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        return {
            "total_services": int(row.get("total_services", 0)),
            "avg_resilience_score": float(row.get("avg_resilience_score", 0)),
            "critical_count": int(row.get("critical_count", 0)),
            "high_risk_count": int(row.get("high_risk_count", 0)),
            "medium_risk_count": int(row.get("medium_risk_count", 0)),
            "low_risk_count": int(row.get("low_risk_count", 0)),
            "total_single_point_failures": int(row.get("total_single_point_failures", 0)),
            "total_srlg_groups": int(row.get("total_srlg_groups", 0)),
            "total_revenue_at_risk_usd": float(row.get("total_revenue_at_risk_usd", 0) or 0),
        }

    def get_risk_distribution(self) -> list[dict] | None:
        """Return risk breakdown by category."""
        rows = self._execute(_RISK_DISTRIBUTION_SQL)
        if rows is None:
            return None
        result = []
        for row in rows:
            total = max(int(row.get("total", 1)), 1)
            at_risk = int(row.get("at_risk_count", 0))
            result.append({
                "category": row["category"],
                "count": at_risk,
                "percentage": round(at_risk / total * 100, 1),
            })
        return result

    def get_service_score(self, service_id: str) -> dict | None:
        """Get resilience score for a single service."""
        sql = f"""
            SELECT
              r.service_id,
              CASE
                WHEN ga.city IS NOT NULL AND gz.city IS NOT NULL
                THEN CONCAT(ga.city, '\u2013', gz.city, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
                ELSE CONCAT(r.service_id, ' ', UPPER(REPLACE(s.service_type, '_', ' ')), ' ', s.bandwidth)
              END AS service_name,
              s.customer_id,
              c.customer_name,
              ROUND(r.overall_score, 1)            AS resilience_score,
              ROUND(r.path_diversity_score, 1)     AS physical_redundancy_score,
              ROUND(r.telemetry_health_score, 1)   AS network_health_score,
              ROUND(r.hazard_exposure_score, 1)    AS environmental_risk_score,
              r.srlg_count,
              r.active_alarms                      AS single_point_failures,
              r.score_time                         AS snapshot_timestamp,
              ROUND(r.revenue_at_risk_usd, 2)      AS revenue_at_risk_usd
            FROM resilience_score_snapshot r
            JOIN service_inventory s        ON r.service_id = s.service_id
            JOIN customer c                 ON s.customer_id = c.customer_id
            LEFT JOIN geographic_site ga    ON s.site_a_id   = ga.site_id
            LEFT JOIN geographic_site gz    ON s.site_z_id   = gz.site_id
            WHERE r.service_id = :service_id
        """
        rows = self._execute(sql, params={"service_id": service_id})
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        score = row.get("resilience_score", 0) or 0
        row["path_diversity_rating"] = _score_to_rating(score)
        return row

    def get_hazard_list(self) -> list[dict] | None:
        """Return active hazard events for the hazard summary table."""
        rows = self._execute(_HAZARD_LIST_SQL)
        if rows is None:
            return None
        # Ensure boolean for is_active
        for r in rows:
            r["is_active"] = bool(r.get("is_active", False))
            r["spans_affected"] = int(r.get("spans_affected", 0))
        return rows

    def get_hazard_summary(self) -> dict | None:
        """Return hazard KPI summary: active hazards, spans at risk, services impacted, revenue exposed."""
        rows = self._execute(_HAZARD_SUMMARY_SQL)
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        return {
            "active_hazards": int(row.get("active_hazards", 0)),
            "spans_at_risk": int(row.get("spans_at_risk", 0)),
            "services_impacted": int(row.get("services_impacted", 0)),
            "revenue_exposed_usd": float(row.get("revenue_exposed_usd", 0) or 0),
        }

    # ------------------------------------------------------------------
    # Product Offerings (P10-APP-PRODUCT-VIEW-PREP)
    # P20-APP-LINT-CLEANUP: Removed F811 duplicate (was lines 697+710)
    # ------------------------------------------------------------------

    def list_product_offerings(self) -> list[dict] | None:
        """Return Lakelink Fiber product offerings from UC."""
        rows = self._execute(_PRODUCT_OFFERINGS_SQL)
        if rows is None:
            return None
        for r in rows:
            r["is_diverse_eligible"] = bool(r.get("is_diverse_eligible", False))
        return rows

    # ------------------------------------------------------------------
    # Hazard × Span Crosswalk (P10-APP-HAZARD-XWALK-VIEW)
    # ------------------------------------------------------------------

    def get_crosswalk(self, hazard_type: str | None = None) -> list[dict] | None:
        """Return hazard×span crosswalk aggregated by type × proximity band."""
        if hazard_type:
            sql = f"""
                SELECT
                  hazard_type,
                  proximity_band,
                  CAST(COUNT(*) AS INT) AS intersection_count,
                  CAST(COUNT(DISTINCT span_id) AS INT) AS distinct_spans,
                  ROUND(AVG(affected_service_cnt), 1) AS avg_services_per_span,
                  ROUND(AVG(distance_km), 2) AS avg_distance_km
                FROM hazard_span_intersection
                WHERE hazard_type = :hazard_type
                GROUP BY hazard_type, proximity_band
                ORDER BY CASE proximity_band
                    WHEN 'direct_impact' THEN 1
                    WHEN 'near_field' THEN 2
                    WHEN 'buffer_zone' THEN 3
                  END
            """
            return self._execute(sql, params={"hazard_type": hazard_type})
        return self._execute(_CROSSWALK_SQL)

    def get_crosswalk_summary(self) -> dict | None:
        """Return KPI summary for the hazard crosswalk view."""
        rows = self._execute(_CROSSWALK_SUMMARY_SQL)
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        total_spans = max(int(row.get("total_spans", 1)), 1)
        distinct_exposed = int(row.get("distinct_spans_exposed", 0))
        return {
            "total_intersections": int(row.get("total_intersections", 0)),
            "distinct_spans_exposed": distinct_exposed,
            "total_spans": total_spans,
            "exposure_pct": round(distinct_exposed / total_spans * 100, 1),
            "hazard_types": int(row.get("hazard_types", 0)),
            "direct_impact_count": int(row.get("direct_impact_count", 0)),
            "near_field_count": int(row.get("near_field_count", 0)),
            "buffer_zone_count": int(row.get("buffer_zone_count", 0)),
        }

    def list_actions(
        self,
        status_filter: str | None = None,
        priority_filter: str | None = None,
    ) -> list[dict] | None:
        """Return proactive actions from UC gold table."""
        rows = self._execute(_ACTIONS_SQL)
        if rows is None:
            return None

        # BUG-DW-030: No normalization needed — UI now uses 'cancelled' to match UC data

        # Apply filters
        if status_filter:
            rows = [r for r in rows if r.get("status") == status_filter]
        if priority_filter:
            rows = [r for r in rows if r.get("priority") == priority_filter]

        return rows

    # ------------------------------------------------------------------
    # Topology endpoints (TOPOLOGY-VIS-SPEC §10, §13)
    # ------------------------------------------------------------------

    def get_topology_regions(self) -> list[dict] | None:
        """Return region-level topology summary (4 rows)."""
        rows = self._execute(_TOPOLOGY_REGIONS_SQL)
        if rows is None:
            return None
        for r in rows:
            r["site_count"] = int(r.get("site_count", 0))
            r["tier_1_count"] = int(r.get("tier_1_count", 0))
            r["tier_2_count"] = int(r.get("tier_2_count", 0))
            r["tier_3_count"] = int(r.get("tier_3_count", 0))
            r["co_count"] = int(r.get("co_count", 0))
            r["dc_count"] = int(r.get("dc_count", 0))
            r["conduit_count"] = int(r.get("conduit_count", 0))
            r["span_count"] = int(r.get("span_count", 0))
        return rows

    def get_topology_sites(self, region: str) -> list[dict] | None:
        """Return tier_1+tier_2 sites in a region for drill-in view."""
        rows = self._execute(_TOPOLOGY_SITES_SQL, params={"region": region})
        if rows is None:
            return None
        for r in rows:
            r["conduit_count"] = int(r.get("conduit_count", 0))
            r["latitude"] = float(r.get("latitude", 0))
            r["longitude"] = float(r.get("longitude", 0))
        return rows

    def get_topology_conduits(self, region: str) -> list[dict] | None:
        """Return conduits between tier_1+tier_2 sites in a region."""
        rows = self._execute(_TOPOLOGY_CONDUITS_SQL, params={"region": region})
        if rows is None:
            return None
        for r in rows:
            r["span_count"] = int(r.get("span_count", 0))
            r["length_km"] = float(r.get("length_km", 0))
        return rows

    # ------------------------------------------------------------------
    # Conduit coverage (P35-APP-CONDUIT-COVERAGE-BADGE) — v4 shadow, read-only
    # ------------------------------------------------------------------

    def list_conduit_coverage(
        self,
        coverage_class: str | None = "REAL_SEGMENTED",
        region: str | None = None,
    ) -> list[dict] | None:
        """Return conduits with span_coverage_class. coverage_class=None means all classes.

        coverage_class is allow-listed; both values are bound as statement parameters
        (BUG-QA-077). Only fixed clause text is spliced into {where}.
        """
        clauses: list[str] = []
        params: dict[str, str] = {}
        if coverage_class is not None:
            if coverage_class not in _CONDUIT_COVERAGE_CLASSES:
                raise ValueError(f"invalid coverage_class: {coverage_class}")
            clauses.append("AND c.span_coverage_class = :coverage_class")
            params["coverage_class"] = coverage_class
        if region:
            clauses.append("AND sa.region = :region")
            params["region"] = region
        sql = _CONDUIT_COVERAGE_SQL.replace("{where}", " ".join(clauses))
        rows = self._execute(sql, row_limit=5000, params=params or None)
        if rows is None:
            return None
        for r in rows:
            for k in ("length_km", "segmented_km", "coverage_pct"):
                r[k] = float(r.get(k) or 0)
            for k in ("lat_a", "lon_a", "lat_z", "lon_z"):
                r[k] = float(r[k]) if r.get(k) is not None else None
        return rows

    def get_conduit_coverage_summary(self) -> dict | None:
        """Per-class conduit counts for the coverage legend."""
        rows = self._execute(_CONDUIT_COVERAGE_SUMMARY_SQL)
        if rows is None:
            return None
        # Classes present in the data, in known order; unknown future classes go last.
        order = {c: i for i, c in enumerate(_CONDUIT_COVERAGE_CLASSES)}
        rows = sorted(
            (r for r in rows if r.get("span_coverage_class")),
            key=lambda r: (order.get(r["span_coverage_class"], len(order)), r["span_coverage_class"]),
        )
        classes = [
            {
                "span_coverage_class": r["span_coverage_class"],
                "conduit_count": int(r.get("conduit_count") or 0),
                "length_km": float(r.get("length_km") or 0),
                "segmented_km": float(r.get("segmented_km") or 0),
            }
            for r in rows
        ]
        return {
            "total_conduits": sum(c["conduit_count"] for c in classes),
            "classes": classes,
            "source_table": _CONDUIT_COVERAGE_TABLE,
        }

    # ------------------------------------------------------------------
    # Path trace + SRLG + Hazard overlay (TOPOLOGY-VIS-SPEC §2, §3, §4)
    # ------------------------------------------------------------------

    def get_service_path_trace(self, service_id: str) -> list[dict] | None:
        """Return hop-by-hop path for a service (working + protect)."""
        rows = self._execute(_SERVICE_PATH_TRACE_SQL, row_limit=500, params={"service_id": service_id})
        if rows is None:
            return None
        for r in rows:
            r["hop_index"] = int(r.get("hop_index", 0))
            r["span_length_km"] = float(r.get("span_length_km", 0) or 0)
            r["conduit_length_km"] = float(r.get("conduit_length_km", 0) or 0)
            r["strand_count"] = int(r.get("strand_count", 0) or 0)
        return rows

    def get_service_diversity(self, service_id: str) -> dict | None:
        """Return diversity status for a service."""
        rows = self._execute(_SERVICE_DIVERSITY_SQL, params={"service_id": service_id})
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        return {
            "service_id": row.get("service_id"),
            "diversity_status": row.get("path_diversity_status", "unknown"),
            "working_hops": int(row.get("working_hops", 0) or 0),
            "protect_hops": int(row.get("protect_hops", 0) or 0),
            "working_conduits": int(row.get("working_conduits", 0) or 0),
            "protect_conduits": int(row.get("protect_conduits", 0) or 0),
            "shared_srlg_count": int(row.get("shared_srlg_count", 0) or 0),
        }

    def get_srlgs_by_region(self, region: str) -> list[dict] | None:
        """Return SRLG memberships for spans in a region."""
        rows = self._execute(_SRLG_BY_REGION_SQL, row_limit=500, params={"region": region})
        if rows is None:
            return None
        for r in rows:
            r["span_length_km"] = float(r.get("span_length_km", 0) or 0)
        return rows

    def get_hazard_overlay(self) -> list[dict] | None:
        """Return active hazards for the topology overlay."""
        rows = self._execute(_HAZARD_OVERLAY_SQL)
        if rows is None:
            return None
        for r in rows:
            r["latitude"] = float(r.get("latitude", 0) or 0)
            r["longitude"] = float(r.get("longitude", 0) or 0)
            r["direct_impact_spans"] = int(r.get("direct_impact_spans", 0) or 0)
            r["near_impact_spans"] = int(r.get("near_impact_spans", 0) or 0)
            r["advisory_spans"] = int(r.get("advisory_spans", 0) or 0)
        return rows

    def get_action_summary(self) -> dict | None:
        """Aggregate action queue counts from UC."""
        sql = """
            SELECT
              COUNT(*)                                                AS total_actions,
              SUM(CASE WHEN status = 'pending'     THEN 1 ELSE 0 END) AS pending_count,
              SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_count,
              SUM(CASE WHEN status = 'completed'   THEN 1 ELSE 0 END) AS completed_count,
              SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count,
              SUM(CASE WHEN status = 'pending' AND priority = 'critical' THEN 1 ELSE 0 END) AS critical_pending
            FROM proactive_action
        """
        rows = self._execute(sql)
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        return {
            "total_actions": int(row.get("total_actions", 0)),
            "pending_count": int(row.get("pending_count", 0)),
            "in_progress_count": int(row.get("in_progress_count", 0)),
            "completed_count": int(row.get("completed_count", 0)),
            "cancelled_count": int(row.get("cancelled_count", 0)),
            "critical_pending": int(row.get("critical_pending", 0)),
        }

    def get_mrc_protected(self) -> dict | None:
        """MRC Protected KPI from the v4 metric view (P36-APP-V4-MRC-PROTECTED-KPI).

        Deduplicated per service inside the metric view; never sum per action.
        Returns None on null/zero so the UI hides the card instead of showing $0.
        """
        rows = self._execute(_MRC_PROTECTED_SQL)
        if not rows:
            return None
        row = rows[0]
        keys = ("mrc_protected_usd", "services_protected", "mrc_share", "total_mrc_usd", "total_services")
        if any(row.get(k) is None for k in keys):
            return None
        mrc = float(row["mrc_protected_usd"])
        services = int(row["services_protected"])
        if mrc <= 0 or services <= 0:
            return None
        return {
            "mrc_protected_usd": mrc,
            "services_protected": services,
            "mrc_share": float(row["mrc_share"]),
            "total_mrc_usd": float(row["total_mrc_usd"]),
            "total_services": int(row["total_services"]),
            "source": _MRC_PROTECTED_VIEW,
        }
