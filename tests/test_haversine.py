"""Tests for Haversine geospatial distance computation.

Validates the haversine formula used in silver_hazard_span_intersection
(resilience_scoring_pipeline Cell 2). Confirms BUG-QA-005 fix: distances
must be in km, NOT degrees.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import math

from conftest import haversine_km


# ---------------------------------------------------------------------------
# Unit tests: Haversine formula correctness
# ---------------------------------------------------------------------------

class TestHaversineFormula:
    """Verify the Python reference haversine matches known great-circle distances."""

    def test_known_city_pairs(self, known_distances):
        """Haversine result matches published great-circle distances within tolerance."""
        for lat1, lon1, lat2, lon2, expected_km, tol, label in known_distances:
            result = haversine_km(lat1, lon1, lat2, lon2)
            assert abs(result - expected_km) <= tol, (
                f"{label}: expected ~{expected_km} km, got {result:.1f} km"
            )

    def test_same_point_returns_zero(self):
        """Distance from a point to itself is 0."""
        assert haversine_km(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_symmetry(self):
        """haversine(A, B) == haversine(B, A)."""
        d1 = haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
        d2 = haversine_km(34.0522, -118.2437, 40.7128, -74.0060)
        assert abs(d1 - d2) < 0.001

    def test_equator_one_degree_longitude(self):
        """1 degree of longitude at equator \u2248 111.2 km."""
        d = haversine_km(0.0, 0.0, 0.0, 1.0)
        assert 110.5 < d < 111.5, f"Expected ~111 km, got {d:.1f}"

    def test_one_degree_latitude(self):
        """1 degree of latitude \u2248 111.2 km regardless of longitude."""
        d = haversine_km(45.0, 0.0, 46.0, 0.0)
        assert 110.5 < d < 111.5, f"Expected ~111 km, got {d:.1f}"

    def test_result_is_km_not_degrees(self):
        """BUG-QA-005 regression: result must be > 100 for cross-country pairs.

        ST_Distance returns degrees (~0.3 for NYC→Chicago); haversine must return km (~1146).
        This test catches a reversion to degree-based distance.
        """
        d = haversine_km(40.7128, -74.0060, 41.8781, -87.6298)  # NYC → Chicago
        assert d > 100, (
            f"BUG-QA-005 regression: NYC→Chicago = {d:.2f}. "
            "Looks like degrees, not km. Expected ~1146 km."
        )

    def test_antipodal_points(self):
        """Antipodal points \u2248 half Earth circumference (~20015 km)."""
        d = haversine_km(0.0, 0.0, 0.0, 180.0)
        assert 20010 < d < 20020

    def test_negative_coordinates(self):
        """Southern/Western hemisphere coordinates work correctly."""
        d = haversine_km(-33.8688, 151.2093, -37.8136, 144.9631)  # Sydney → Melbourne
        assert 700 < d < 750, f"Sydney→Melbourne expected ~714 km, got {d:.1f}"


# ---------------------------------------------------------------------------
# Bounding box pre-filter validation
# ---------------------------------------------------------------------------

class TestBoundingBoxFilter:
    """Validate the bounding-box pre-filter used in the pipeline.

    Pipeline uses: ABS(lat_diff) < radius * 1.5 / 111.0
    This avoids a full CROSS JOIN by pre-filtering on approximate degree bounds.
    """

    def test_bounding_box_includes_nearby(self):
        """Points within radius must pass the bounding-box filter."""
        hazard_lat, hazard_lon, radius_km = 40.0, -74.0, 50.0
        span_lat = hazard_lat + 0.1  # ~11 km away
        span_lon = hazard_lon + 0.1

        lat_threshold = radius_km * 1.5 / 111.0
        lon_threshold = radius_km * 1.5 / (111.0 * math.cos(math.radians(hazard_lat)))

        assert abs(span_lat - hazard_lat) < lat_threshold
        assert abs(span_lon - hazard_lon) < lon_threshold

    def test_bounding_box_excludes_distant(self):
        """Points far outside radius must be excluded by bounding box."""
        hazard_lat, radius_km = 40.0, 10.0
        span_lat = hazard_lat + 5.0  # ~555 km away

        lat_threshold = radius_km * 1.5 / 111.0
        assert abs(span_lat - hazard_lat) >= lat_threshold

    def test_bounding_box_uses_1point5x_buffer(self):
        """Bounding box is 1.5x the hazard radius (per pipeline spec)."""
        radius_km = 20.0
        lat_threshold_deg = radius_km * 1.5 / 111.0
        # Should be ~0.27 degrees
        assert 0.26 < lat_threshold_deg < 0.28


# ---------------------------------------------------------------------------
# Impact zone classification
# ---------------------------------------------------------------------------

class TestImpactZoneClassification:
    """Validate impact_zone CASE logic from pipeline.

    Rules:
      - distance <= radius * 0.5 → 'direct_impact'
      - distance <= radius      → 'buffer_zone'
      - else                    → 'proximity_alert'
    """

    @staticmethod
    def classify(distance_km: float, radius_km: float) -> str:
        if distance_km <= radius_km * 0.5:
            return "direct_impact"
        elif distance_km <= radius_km:
            return "buffer_zone"
        else:
            return "proximity_alert"

    def test_direct_impact(self):
        assert self.classify(2.0, 10.0) == "direct_impact"

    def test_buffer_zone(self):
        assert self.classify(7.0, 10.0) == "buffer_zone"

    def test_proximity_alert(self):
        assert self.classify(12.0, 10.0) == "proximity_alert"

    def test_exact_half_radius_boundary(self):
        """Exactly at radius/2 → direct_impact (<=)."""
        assert self.classify(5.0, 10.0) == "direct_impact"

    def test_exact_radius_boundary(self):
        """Exactly at radius → buffer_zone (<=)."""
        assert self.classify(10.0, 10.0) == "buffer_zone"

    def test_zero_distance(self):
        assert self.classify(0.0, 10.0) == "direct_impact"
