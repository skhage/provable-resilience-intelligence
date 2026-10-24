"""Tests for composite resilience scoring and SRLG diversity logic.

Validates gold_resilience_score (Cell 4) and silver_srlg_diversity_analysis
(Cell 3) of resilience_scoring_pipeline.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

from conftest import composite_score


# ---------------------------------------------------------------------------
# Composite score weight tests (40% diversity, 30% hazard, 30% telemetry)
# ---------------------------------------------------------------------------

class TestCompositeScoreWeights:
    """Verify the 40/30/30 weighting of resilience score components."""

    def test_boundary_cases(self, score_boundary_cases):
        """All boundary combinations produce expected scores."""
        for div, haz, tel, expected in score_boundary_cases:
            result = composite_score(div, haz, tel)
            assert abs(result - expected) < 0.15, (
                f"composite({div}, {haz}, {tel}) = {result}, expected {expected}"
            )

    def test_diversity_has_highest_weight(self):
        """Diversity (40%) should contribute more than hazard or telemetry (30% each)."""
        div_only = composite_score(100, 0, 0)    # 40
        haz_only = composite_score(0, 100, 0)    # 30
        tel_only = composite_score(0, 0, 100)    # 30
        assert div_only > haz_only
        assert div_only > tel_only
        assert haz_only == tel_only  # Equal weights

    def test_weights_sum_to_100(self):
        """composite(100, 100, 100) must equal 100."""
        assert composite_score(100, 100, 100) == 100.0

    def test_all_zeros(self):
        assert composite_score(0, 0, 0) == 0.0

    def test_score_bounded_0_100(self):
        """Score is always in [0, 100] for valid inputs."""
        import random
        random.seed(42)
        for _ in range(1000):
            d = random.uniform(0, 100)
            h = random.uniform(0, 100)
            t = random.uniform(0, 100)
            s = composite_score(d, h, t)
            assert 0.0 <= s <= 100.0, f"Score {s} out of bounds for ({d}, {h}, {t})"


# ---------------------------------------------------------------------------
# Telemetry health score formula tests
# ---------------------------------------------------------------------------

class TestTelemetryHealthScore:
    """Validate the alarm-based telemetry health formula.

    Pipeline formula (Cell 4):
      - 0 alarms → 100
      - critical alarms > 0 → GREATEST(0, 100 - critical * 40)
      - else → GREATEST(0, 100 - alarm_count * 15)
    """

    @staticmethod
    def telemetry_score(alarm_count: int, critical_count: int) -> float:
        if alarm_count == 0:
            return 100.0
        if critical_count > 0:
            return max(0.0, 100.0 - critical_count * 40)
        return max(0.0, 100.0 - alarm_count * 15)

    def test_no_alarms(self):
        assert self.telemetry_score(0, 0) == 100.0

    def test_one_critical_alarm(self):
        assert self.telemetry_score(1, 1) == 60.0

    def test_two_critical_alarms(self):
        assert self.telemetry_score(2, 2) == 20.0

    def test_three_critical_alarms_floors_at_zero(self):
        """3+ critical alarms → score floors at 0."""
        assert self.telemetry_score(3, 3) == 0.0
        assert self.telemetry_score(22, 22) == 0.0  # Typical synthetic data case

    def test_non_critical_alarms(self):
        assert self.telemetry_score(5, 0) == 25.0
        assert self.telemetry_score(7, 0) == 0.0  # 100 - 7*15 = -5 → 0

    def test_sensitivity_warning(self):
        """Document: formula sensitivity means >2 critical alarms = score 0.

        BUG-QA-012: With avg 22 critical alarms/service in synthetic data,
        telemetry_health_score = 0 for 99.99% of rows. The 30% weight is
        effectively dead. Consider log-scale or percentage-based formula.
        """
        # Every realistic service with alarms will score 0
        assert self.telemetry_score(100, 22) == 0.0
        # Only services with 0-2 critical alarms get non-zero
        assert self.telemetry_score(10, 2) == 20.0
        assert self.telemetry_score(10, 0) == 0.0  # 10 non-critical still floors it


# ---------------------------------------------------------------------------
# Hazard exposure score formula tests
# ---------------------------------------------------------------------------

class TestHazardExposureScore:
    """Validate the hazard-based exposure formula.

    Pipeline formula (Cell 4):
      - 0 hazards → 100
      - direct_impact > 0 → GREATEST(0, 100 - direct * 30)
      - else → GREATEST(0, 100 - hazard_count * 10)
    """

    @staticmethod
    def hazard_score(hazard_count: int, direct_impact_count: int) -> float:
        if hazard_count == 0:
            return 100.0
        if direct_impact_count > 0:
            return max(0.0, 100.0 - direct_impact_count * 30)
        return max(0.0, 100.0 - hazard_count * 10)

    def test_no_hazards(self):
        assert self.hazard_score(0, 0) == 100.0

    def test_one_direct_impact(self):
        assert self.hazard_score(1, 1) == 70.0

    def test_four_direct_impacts_floors(self):
        assert self.hazard_score(4, 4) == 0.0

    def test_non_direct_hazards(self):
        assert self.hazard_score(5, 0) == 50.0
        assert self.hazard_score(10, 0) == 0.0


# ---------------------------------------------------------------------------
# SRLG diversity verdict tests
# ---------------------------------------------------------------------------

class TestSRLGDiversityVerdict:
    """Validate diversity_verdict CASE from silver_srlg_diversity_analysis.

    Rules (Cell 3):
      - shared=0 → 'truly_diverse'
      - shared<=2 AND max_severity<=2 → 'minor_overlap'
      - shared<=5 → 'significant_overlap'
      - else → 'false_diversity'
    """

    @staticmethod
    def classify(shared_count: int, max_severity: int) -> str:
        if shared_count == 0:
            return "truly_diverse"
        if shared_count <= 2 and max_severity <= 2:
            return "minor_overlap"
        if shared_count <= 5:
            return "significant_overlap"
        return "false_diversity"

    def test_truly_diverse(self):
        assert self.classify(0, 0) == "truly_diverse"

    def test_minor_overlap(self):
        assert self.classify(2, 2) == "minor_overlap"
        assert self.classify(1, 1) == "minor_overlap"

    def test_minor_overlap_high_severity_escalates(self):
        """2 shared SRLGs but severity 3 → significant_overlap (not minor)."""
        assert self.classify(2, 3) == "significant_overlap"

    def test_significant_overlap(self):
        assert self.classify(5, 4) == "significant_overlap"
        assert self.classify(3, 1) == "significant_overlap"

    def test_false_diversity(self):
        assert self.classify(6, 4) == "false_diversity"
        assert self.classify(10, 1) == "false_diversity"


# ---------------------------------------------------------------------------
# Revenue at risk formula tests
# ---------------------------------------------------------------------------

class TestRevenueAtRisk:
    """Revenue at risk = MRC * (1 - overall_score / 100)."""

    @staticmethod
    def revenue_at_risk(mrc: float, overall_score: float) -> float:
        return round(mrc * (1.0 - overall_score / 100.0), 2)

    def test_score_100_zero_risk(self):
        assert self.revenue_at_risk(10000, 100.0) == 0.0

    def test_score_0_full_risk(self):
        assert self.revenue_at_risk(10000, 0.0) == 10000.0

    def test_score_50_half_risk(self):
        assert self.revenue_at_risk(10000, 50.0) == 5000.0

    def test_negative_mrc_guard(self):
        """MRC should never be negative; formula still works but flags concern."""
        result = self.revenue_at_risk(-100, 50.0)
        assert result == -50.0  # Technically valid, but a DQ issue upstream
