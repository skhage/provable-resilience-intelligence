"""Data quality assertions for Provable Resilience Intelligence tables.

Runs against live cdm_tmforum.provable_resilience_intelligence tables.
Requires Databricks Spark session (run via `pytest` on a cluster or
`databricks bundle run` with test task).

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import pytest

CATALOG = "cdm_tmforum"
SCHEMA = "provable_resilience_intelligence"
FQN = f"{CATALOG}.{SCHEMA}"

# Skip entire module if Spark is unavailable (local pytest run)
try:
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    SPARK_AVAILABLE = True
except Exception:
    SPARK_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SPARK_AVAILABLE, reason="Spark session not available"
)


def _count(table: str) -> int:
    return spark.sql(f"SELECT COUNT(*) as c FROM {FQN}.{table}").collect()[0]["c"]


def _query(sql: str):
    return spark.sql(sql).collect()


# ---------------------------------------------------------------------------
# Table population checks
# ---------------------------------------------------------------------------

class TestTablePopulation:
    """All 17 tables must be populated (non-empty)."""

    EXPECTED_TABLES = [
        "geographic_site", "geographic_address", "physical_resource_span",
        "physical_resource_conduit", "shared_risk_group", "customer",
        "service_inventory", "service_path", "geographic_hazard_event",
        "resilience_score_snapshot", "proactive_action",
        "resource_alarm", "resource_performance_measure",
    ]

    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_table_not_empty(self, table):
        count = _count(table)
        assert count > 0, f"{FQN}.{table} is empty (0 rows)"


# ---------------------------------------------------------------------------
# Score integrity
# ---------------------------------------------------------------------------

class TestScoreIntegrity:
    """Resilience scores must be bounded and formula-consistent."""

    def test_overall_score_bounded_0_100(self):
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.resilience_score_snapshot
            WHERE overall_score < 0 OR overall_score > 100
        """)
        assert rows[0]["c"] == 0, "overall_score out of [0, 100] range"

    def test_component_scores_bounded(self):
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.resilience_score_snapshot
            WHERE path_diversity_score < 0 OR path_diversity_score > 100
               OR hazard_exposure_score < 0 OR hazard_exposure_score > 100
               OR telemetry_health_score < 0 OR telemetry_health_score > 100
        """)
        assert rows[0]["c"] == 0, "Component score out of [0, 100] range"

    def test_composite_formula_drift(self):
        """Composite = div*0.4 + haz*0.3 + tel*0.3; max drift from rounding < 0.2."""
        rows = _query(f"""
            SELECT MAX(ABS(
                overall_score - (
                    path_diversity_score * 0.4 +
                    hazard_exposure_score * 0.3 +
                    telemetry_health_score * 0.3
                )
            )) as max_drift
            FROM {FQN}.resilience_score_snapshot
        """)
        assert rows[0]["max_drift"] < 0.2, (
            f"Composite formula drift {rows[0]['max_drift']:.3f} exceeds 0.2 tolerance"
        )

    def test_no_negative_revenue_at_risk(self):
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.resilience_score_snapshot
            WHERE revenue_at_risk_usd < 0
        """)
        assert rows[0]["c"] == 0, "Negative revenue_at_risk_usd found"


# ---------------------------------------------------------------------------
# FK integrity
# ---------------------------------------------------------------------------

class TestForeignKeyIntegrity:
    """Cross-table FK relationships should have zero orphans."""

    def test_score_service_fk(self):
        """Every score references a valid service_id."""
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.resilience_score_snapshot rs
            LEFT JOIN {FQN}.service_inventory si ON rs.service_id = si.service_id
            WHERE si.service_id IS NULL
        """)
        assert rows[0]["c"] == 0, "Orphan service_ids in resilience_score_snapshot"

    def test_action_service_fk(self):
        """Every proactive action references a valid service_id."""
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.proactive_action pa
            LEFT JOIN {FQN}.service_inventory si ON pa.service_id = si.service_id
            WHERE si.service_id IS NULL
        """)
        assert rows[0]["c"] == 0, "Orphan service_ids in proactive_action"

    def test_service_path_span_fk(self):
        """Service paths reference valid span_ids."""
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.service_path sp
            LEFT JOIN {FQN}.physical_resource_span prs ON sp.span_id = prs.span_id
            WHERE prs.span_id IS NULL
        """)
        assert rows[0]["c"] == 0, "Orphan span_ids in service_path"

    def test_alarm_span_fk(self):
        """Alarms with span_id reference valid spans (span_id is nullable for site alarms)."""
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.resource_alarm ra
            LEFT JOIN {FQN}.physical_resource_span prs ON ra.span_id = prs.span_id
            WHERE ra.span_id IS NOT NULL AND prs.span_id IS NULL
        """)
        assert rows[0]["c"] == 0, "Orphan span_ids in resource_alarm (excluding NULL)"


# ---------------------------------------------------------------------------
# SLA tier validation
# ---------------------------------------------------------------------------

class TestSLATiers:
    """SLA tiers must be standard, premium, premium_plus only."""

    def test_valid_sla_tiers(self, valid_sla_tiers):
        rows = _query(f"""
            SELECT DISTINCT sla_tier FROM {FQN}.service_inventory
        """)
        actual = {r["sla_tier"] for r in rows}
        assert actual.issubset(valid_sla_tiers), (
            f"Invalid SLA tiers: {actual - valid_sla_tiers}"
        )


# ---------------------------------------------------------------------------
# Geospatial data quality
# ---------------------------------------------------------------------------

class TestGeospatialQuality:
    """Geospatial columns must have valid coordinates and WKT."""

    def test_hazard_coordinates_in_range(self):
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.geographic_hazard_event
            WHERE latitude < -90 OR latitude > 90
               OR longitude < -180 OR longitude > 180
        """)
        assert rows[0]["c"] == 0, "Hazard coordinates out of WGS84 range"

    def test_span_geom_wkt_parseable(self):
        """Sample of span WKT geometries must be parseable by ST_GeomFromWKT."""
        rows = _query(f"""
            SELECT COUNT(*) as c FROM (
                SELECT ST_GeomFromWKT(geom_wkt) as geom
                FROM {FQN}.physical_resource_span
                WHERE geom_wkt IS NOT NULL
                LIMIT 100
            ) t WHERE geom IS NULL
        """)
        assert rows[0]["c"] == 0, "Unparseable WKT in physical_resource_span"

    def test_hazard_radius_positive(self):
        rows = _query(f"""
            SELECT COUNT(*) as c FROM {FQN}.geographic_hazard_event
            WHERE radius_km <= 0
        """)
        assert rows[0]["c"] == 0, "Hazard radius_km must be positive"
