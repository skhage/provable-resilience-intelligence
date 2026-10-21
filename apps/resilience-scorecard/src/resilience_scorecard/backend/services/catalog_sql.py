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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import ColumnInfoTypeName, StatementState

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
  COALESCE(a.resolved_at, a.created_at) AS updated_at
FROM proactive_action a
JOIN service_inventory s       ON a.service_id = s.service_id
LEFT JOIN geographic_site ga   ON s.site_a_id  = ga.site_id
LEFT JOIN geographic_site gz   ON s.site_z_id  = gz.site_id
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

    def _execute(self, sql: str, row_limit: int = 12000) -> list[dict[str, Any]] | None:
        """Execute SQL via Statement Execution API and return rows as dicts."""
        if self._w is None:
            return None
        try:
            resp = self._w.statement_execution.execute_statement(
                warehouse_id=self._config.warehouse_id,
                statement=sql,
                catalog=self._config.catalog,
                schema=self._config.schema_name,
                wait_timeout="50s",
                row_limit=row_limit,
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
            WHERE r.service_id = '{service_id}'
        """
        rows = self._execute(sql)
        if rows is None or len(rows) == 0:
            return None
        row = rows[0]
        score = row.get("resilience_score", 0) or 0
        row["path_diversity_rating"] = _score_to_rating(score)
        return row

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
