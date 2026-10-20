# Databricks notebook source
# MAGIC %md
# MAGIC # Resilience Scoring Pipeline
# MAGIC Bronze → Silver (SID-aligned) → Gold (resilience scores)
# MAGIC
# MAGIC This is the DAB-managed entrypoint. The full pipeline logic lives in the
# MAGIC workspace notebook at:
# MAGIC `pipeline/resilience_scoring_pipeline`
# MAGIC
# MAGIC When migrating to Git-based development, replace this stub with the
# MAGIC exported notebook content.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# Configuration from DAB variables
catalog = spark.conf.get("resilience.catalog", "cdm_tmforum")
schema = spark.conf.get("resilience.schema", "provable_resilience_intelligence")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze: Raw table ingestion

# COMMAND ----------

@dlt.table(
    name="bronze_geographic_site",
    comment="Raw geographic site data for resilience scoring"
)
def bronze_geographic_site():
    return spark.table(f"{catalog}.{schema}.geographic_site")

@dlt.table(
    name="bronze_physical_resource_span",
    comment="Raw physical resource spans"
)
def bronze_physical_resource_span():
    return spark.table(f"{catalog}.{schema}.physical_resource_span")

@dlt.table(
    name="bronze_shared_risk_group",
    comment="Raw shared risk groups (SRLGs)"
)
def bronze_shared_risk_group():
    return spark.table(f"{catalog}.{schema}.shared_risk_group")

@dlt.table(
    name="bronze_service_inventory",
    comment="Raw customer-facing service inventory"
)
def bronze_service_inventory():
    return spark.table(f"{catalog}.{schema}.service_inventory")
