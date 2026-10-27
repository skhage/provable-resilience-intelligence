"""Core configuration, dependency injection, and app factory for Resilience Scorecard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field

logger = logging.getLogger("resilience_scorecard")


# ---------------------------------------------------------------------------
# AppConfig — populated from env vars prefixed RESILIENCE_SCORECARD_
# ---------------------------------------------------------------------------

class AppConfig(BaseSettings):
    model_config = {"env_prefix": "RESILIENCE_SCORECARD_"}

    app_name: str = Field(default="resilience-scorecard")
    lakebase_host: str = Field(default="ep-summer-hill-d2s98kn6.database.us-east-1.cloud.databricks.com")
    lakebase_endpoint: str = Field(
        default="projects/telco-provable-resilience-intelligence-project/branches/production/endpoints/primary"
    )
    catalog: str = Field(default="cdm_tmforum")
    schema_name: str = Field(default="provable_resilience_intelligence", alias="schema")
    warehouse_id: str = Field(default="9cd919d96b11bf1c")  # Apps & Agents Warehouse (serverless)
    # V4-KPI-COPY-SPEC §0: one flag gates every v4 UI change. Default off = PRI-DEMO-FREEZE-v3 UI.
    # Read from PRI_V4_KPIS (spec name); RESILIENCE_SCORECARD_V4_KPIS accepted for prefix consistency.
    v4_kpis: bool = Field(
        default=False,
        validation_alias=AliasChoices("PRI_V4_KPIS", "RESILIENCE_SCORECARD_V4_KPIS"),
    )
    # P36-APP-V4-BB-SRLG-DISCLOSURE (V4-KPI-COPY-SPEC §2): auto = derive from the SRLG table
    # the app reads (any BB-*/BBS-* span rows -> complete). partial/complete force the UI state.
    bb_srlg_coverage: str = Field(
        default="auto",
        validation_alias=AliasChoices("PRI_BB_SRLG_COVERAGE", "RESILIENCE_SCORECARD_BB_SRLG_COVERAGE"),
    )
    # P41-APP-V4-INTERIM-BADGE (V4-KPI-COPY-SPEC §6.2): auto = read report_status from
    # kpi_delta_attribution_v4_candidate (FINAL only when every row is FINAL). INTERIM/FINAL force it.
    v4_report_status: str = Field(
        default="auto",
        validation_alias=AliasChoices("PRI_V4_REPORT_STATUS", "RESILIENCE_SCORECARD_V4_REPORT_STATUS"),
    )


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


def _get_lakebase_client(request: Request):
    """Return the LakebaseActionClient from app state."""
    return request.app.state.lakebase_client


def _get_catalog_sql(request: Request):
    """Return the CatalogSqlService from app state."""
    return request.app.state.catalog_sql


class Dependencies:
    Config = Annotated[AppConfig, Depends(_get_config)]
    LakebaseClient = Annotated[object, Depends(_get_lakebase_client)]  # typed loosely to avoid circular import
    CatalogSql = Annotated[object, Depends(_get_catalog_sql)]


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_router(prefix: str = "/api", **kwargs) -> APIRouter:
    return APIRouter(prefix=prefix, **kwargs)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(routers: list[APIRouter], lifespan=None) -> FastAPI:
    @asynccontextmanager
    async def default_lifespan(app: FastAPI):
        config = AppConfig()
        app.state.config = config
        logger.info("Resilience Scorecard starting — Lakelink Fiber")

        # Initialize Lakebase action client
        from .services.lakebase import LakebaseActionClient
        lb_client = LakebaseActionClient(config)
        app.state.lakebase_client = lb_client
        logger.info("Lakebase action client initialized (host=%s)", config.lakebase_host)

        # Initialize Unity Catalog SQL service for live scorecard data
        from .services.catalog_sql import CatalogSqlService
        catalog_sql = CatalogSqlService(config)
        app.state.catalog_sql = catalog_sql
        logger.info(
            "CatalogSqlService initialized (available=%s, warehouse=%s)",
            catalog_sql.is_available, config.warehouse_id,
        )

        if lifespan:
            async with lifespan(app):
                yield
        else:
            yield

        # Cleanup
        lb_client.close()
        logger.info("Resilience Scorecard shutdown complete")

    app = FastAPI(
        title="Lakelink Fiber — Provable Resilience Intelligence",
        description="Resilience scorecard and proactive action queue for enterprise services.",
        version="0.1.0",
        lifespan=default_lifespan,
    )

    for router in routers:
        app.include_router(router)

    _mount_frontend(app)

    return app


# ---------------------------------------------------------------------------
# Frontend (P24-APP-BUILD-SCAFFOLD)
# Vite builds ui/ into src/resilience_scorecard/__dist__ during `npm run build`
# (run automatically by Databricks Apps because package.json is at the app root).
# Must be registered AFTER the API routers so /api/* keeps precedence.
# ---------------------------------------------------------------------------

DIST_DIR = Path(__file__).resolve().parent.parent / "__dist__"


def _mount_frontend(app: FastAPI) -> None:
    index_html = DIST_DIR / "index.html"
    if not index_html.is_file():
        logger.warning("Frontend build not found at %s; serving API only", DIST_DIR)
        return

    assets_dir = DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    dist_root = DIST_DIR.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Unknown API routes must 404 as JSON, not fall through to the SPA.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if full_path:
            candidate = (dist_root / full_path).resolve()
            # Path-traversal guard: only serve files inside __dist__.
            if candidate.is_file() and dist_root in candidate.parents:
                return FileResponse(candidate)
        # Client-side routes (/actions, /hazards, /topology?service=...) get index.html.
        return FileResponse(index_html)

    logger.info("Frontend mounted from %s", DIST_DIR)
