"""Core configuration, dependency injection, and app factory for Resilience Scorecard."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, APIRouter, Request
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings
from pydantic import Field

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
    warehouse_id: str = Field(default="7b65956f30d66feb")  # Serverless Starter Warehouse


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

    return app
