"""Lakebase Postgres client for proactive action queue state management.

The action queue lives in Lakebase so that state persists across app restarts
and is shared across the scorecard UI and the resilience agent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

import psycopg
from databricks.sdk import WorkspaceClient

if TYPE_CHECKING:
    from ..core import AppConfig

logger = logging.getLogger("resilience_scorecard.lakebase")

# ---------------------------------------------------------------------------
# DDL — run once to bootstrap the proactive_actions table in Lakebase
# ---------------------------------------------------------------------------

PROACTIVE_ACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS proactive_actions (
    action_id       TEXT PRIMARY KEY,
    action_type     TEXT NOT NULL,          -- reroute | dispatch | notify
    service_id      TEXT NOT NULL,
    service_name    TEXT NOT NULL,
    risk_trigger    TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'medium',  -- critical | high | medium | low
    status          TEXT NOT NULL DEFAULT 'pending', -- pending | in_progress | completed | dismissed
    assigned_to     TEXT,
    description     TEXT NOT NULL,
    resolution_notes TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proactive_actions_status ON proactive_actions(status);
CREATE INDEX IF NOT EXISTS idx_proactive_actions_priority ON proactive_actions(priority);
"""


class LakebaseActionClient:
    """Manages the proactive action queue in Lakebase Postgres."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._conn: psycopg.Connection | None = None
        self._connect()
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Establish connection to Lakebase Postgres."""
        try:
            w = WorkspaceClient()
            user = w.current_user.me().user_name
            token = w.postgres.generate_database_credential(
                endpoint=self._config.lakebase_endpoint
            ).token
            self._conn = psycopg.connect(
                host=self._config.lakebase_host,
                dbname="databricks_postgres",
                user=user,
                password=token,
                sslmode="require",
            )
            logger.info("Connected to Lakebase at %s", self._config.lakebase_host)
        except Exception:
            logger.warning("Lakebase connection failed — action queue will use mock data", exc_info=True)
            self._conn = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and not self._conn.closed

    def _ensure_connection(self) -> psycopg.Connection:
        if not self.is_connected:
            self._connect()
        if not self.is_connected:
            raise RuntimeError("Cannot connect to Lakebase")
        return self._conn  # type: ignore[return-value]

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Lakebase connection closed")

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        if not self.is_connected:
            return
        try:
            conn = self._ensure_connection()
            with conn.cursor() as cur:
                cur.execute(PROACTIVE_ACTIONS_DDL)
            conn.commit()
            logger.info("Proactive actions table ensured")
        except Exception:
            logger.warning("Failed to ensure proactive_actions table", exc_info=True)

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def list_actions(
        self, status_filter: str | None = None, priority_filter: str | None = None
    ) -> list[dict]:
        """Fetch actions from Lakebase, optionally filtered."""
        conn = self._ensure_connection()
        sql = "SELECT * FROM proactive_actions WHERE 1=1"
        params: list = []
        if status_filter:
            sql += " AND status = %s"
            params.append(status_filter)
        if priority_filter:
            sql += " AND priority = %s"
            params.append(priority_filter)
        sql += " ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, created_at DESC"

        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc.name for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_action(self, action_id: str) -> dict | None:
        conn = self._ensure_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM proactive_actions WHERE action_id = %s", [action_id])
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc.name for desc in cur.description]
            return dict(zip(cols, row))

    def create_action(self, action: dict) -> dict:
        """Insert a new proactive action."""
        conn = self._ensure_connection()
        action_id = action.get("action_id", f"ACT-{uuid4().hex[:8].upper()}")
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO proactive_actions
                    (action_id, action_type, service_id, service_name, risk_trigger,
                     priority, status, assigned_to, description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                [
                    action_id, action["action_type"], action["service_id"],
                    action["service_name"], action["risk_trigger"],
                    action.get("priority", "medium"), "pending",
                    action.get("assigned_to"), action["description"], now, now,
                ],
            )
            cols = [desc.name for desc in cur.description]
            row = cur.fetchone()
        conn.commit()
        return dict(zip(cols, row))

    def update_action_status(
        self, action_id: str, status: str,
        resolution_notes: str | None = None, assigned_to: str | None = None,
    ) -> dict | None:
        """Update an action's status in Lakebase."""
        conn = self._ensure_connection()
        now = datetime.now(timezone.utc)
        parts = ["status = %s", "updated_at = %s"]
        params: list = [status, now]
        if resolution_notes is not None:
            parts.append("resolution_notes = %s")
            params.append(resolution_notes)
        if assigned_to is not None:
            parts.append("assigned_to = %s")
            params.append(assigned_to)
        params.append(action_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE proactive_actions SET {', '.join(parts)} WHERE action_id = %s RETURNING *",
                params,
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc.name for desc in cur.description]
        conn.commit()
        return dict(zip(cols, row))

    def get_queue_summary(self) -> dict:
        """Aggregate counts for the action queue."""
        conn = self._ensure_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_actions,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress_count,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
                    COUNT(*) FILTER (WHERE status = 'dismissed') AS dismissed_count,
                    COUNT(*) FILTER (WHERE status = 'pending' AND priority = 'critical') AS critical_pending
                FROM proactive_actions
            """)
            cols = [desc.name for desc in cur.description]
            row = cur.fetchone()
        return dict(zip(cols, row))
