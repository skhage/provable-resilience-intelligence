"""Tests for composite resilience scoring and SRLG diversity logic.

Validates gold_resilience_score (Cell 4) and silver_srlg_diversity_analysis
(Cell 3) of resilience_scoring_pipeline.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import json
import math
import os
import re

import pytest

from .scoring_reference import SLA_BOOST, composite_score, revenue_at_risk, sql_round


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

    def test_score_bounded_0_100_all_tiers(self):
        """Boosted score never exceeds the 100 cap for any tier."""
        import random
        random.seed(183)
        for tier in SLA_BOOST:
            for _ in range(500):
                d, h, t = (random.uniform(0, 100) for _ in range(3))
                assert 0.0 <= composite_score(d, h, t, tier) <= 100.0


# ---------------------------------------------------------------------------
# SLA boost + cap tests (BUG-QA-183)
# ---------------------------------------------------------------------------

class TestSlaBoostAndCap:
    """overall = LEAST(100, base + boost); boost +5 premium_plus / +2 premium / 0 standard."""

    def test_boost_values(self):
        assert SLA_BOOST == {"premium_plus": 5.0, "premium": 2.0, "standard": 0.0}

    def test_premium_plus_near_cap(self):
        """Base 97 + 5 = 102 -> capped at 100."""
        assert composite_score(97, 97, 97) == 97.0
        assert composite_score(97, 97, 97, "premium_plus") == 100.0

    def test_premium_plus_below_cap(self):
        assert composite_score(50, 50, 50, "premium_plus") == 55.0

    def test_premium_adds_two(self):
        assert composite_score(50, 50, 50, "premium") == 52.0
        assert composite_score(99, 99, 99, "premium") == 100.0  # 101 -> cap

    def test_standard_adds_zero(self):
        assert composite_score(50, 50, 50, "standard") == 50.0
        assert composite_score(50, 50, 50) == 50.0  # default tier

    def test_null_tier_treated_as_standard(self):
        """Pipeline uses COALESCE(si.sla_tier, 'standard')."""
        assert composite_score(50, 50, 50, None) == 50.0

    def test_perfect_score_not_inflated(self):
        for tier in SLA_BOOST:
            assert composite_score(100, 100, 100, tier) == 100.0

    def test_boost_applies_at_zero(self):
        assert composite_score(0, 0, 0, "premium_plus") == 5.0
        assert composite_score(0, 0, 0, "premium") == 2.0


# ---------------------------------------------------------------------------
# Checks against real pipeline output and pipeline SQL (BUG-QA-183)
# ---------------------------------------------------------------------------

class TestAgainstPipelineOutput:
    """Compare the reference formulas to real resilience_score_snapshot rows.

    These are not local copies: expected values come from the governed table
    (see scoring_reference.SNAPSHOT_SAMPLE for provenance).
    """

    def test_sample_covers_all_tiers_and_cap(self, snapshot_sample):
        tiers = {r[1] for r in snapshot_sample}
        assert tiers == set(SLA_BOOST)
        capped = [r for r in snapshot_sample if r[7] == 100.0 and 0.4 * r[3] + 0.3 * r[4] + 0.3 * r[5] < 100.0]
        assert {r[1] for r in capped} == {"premium", "premium_plus"}

    def test_overall_score_matches_snapshot(self, snapshot_sample):
        for sid, tier, _mrc, d, h, t, _n, overall, _rar in snapshot_sample:
            got = composite_score(d, h, t, tier)
            assert abs(got - overall) < 1e-9, f"{sid} ({tier}): {got} != snapshot {overall}"

    def test_plain_40_30_30_fails_for_boosted_tiers(self, snapshot_sample):
        """Regression guard: the old unboosted formula must NOT reproduce premium rows."""
        boosted = [r for r in snapshot_sample if r[1] != "standard"]
        mismatches = [r for r in boosted if abs(composite_score(r[3], r[4], r[5]) - r[7]) > 0.01]
        assert len(mismatches) == len(boosted)

    def test_revenue_at_risk_uses_boosted_score(self, snapshot_sample):
        for sid, tier, mrc, d, h, t, _n, _overall, rar in snapshot_sample:
            got = revenue_at_risk(mrc, composite_score(d, h, t, tier))
            assert abs(got - rar) < 1e-9, f"{sid}: RaR {got} != snapshot {rar}"

    def test_sql_round_is_half_up(self):
        """SVC-00013 base 34.605 must round to 34.61 like Spark (Python round gives 34.6)."""
        assert sql_round(34.605) == 34.61
        assert composite_score(84.6, 0.04, 2.51, "premium_plus") == 39.61

    def test_hazard_v2_half_life_matches_snapshot(self, snapshot_sample):
        """V2 hazard = ROUND(100 * EXP(-n * LN(2) / 20), 2) (DEC-PRI-HAZARD-HL20-V3)."""
        for sid, _tier, _mrc, _d, h, _t, n, _o, _r in snapshot_sample:
            got = round(100.0 * math.exp(-n * math.log(2) / 20.0), 2)
            assert abs(got - h) <= 0.01, f"{sid}: hazard {got} != snapshot {h} (n={n})"


_PIPELINE_NAMES = (
    "resilience_scoring_pipeline.py",
    "resilience_scoring_pipeline.ipynb",  # workspace/Git export format (BUG-QA-184)
    "resilience_scoring_pipeline",
)


def _read_source(path):
    """Return pipeline source text; for .ipynb join all cell sources."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.endswith(".ipynb") or raw.lstrip().startswith("{"):
        try:
            nb = json.loads(raw)
        except ValueError:
            return raw
        cells = []
        for cell in nb.get("cells", []):
            s = cell.get("source", "")
            cells.append("".join(s) if isinstance(s, list) else s)
        return "\n".join(cells)
    return raw


def _pipeline_source():
    # The DAB entrypoint bundle/pipeline/resilience_scoring_pipeline.py is a stub with no
    # scoring SQL, so only pipelines/ is searched.
    root = os.path.join(os.path.dirname(__file__), os.pardir, "pipelines")
    for name in _PIPELINE_NAMES:
        p = os.path.abspath(os.path.join(root, name))
        if os.path.isfile(p):
            try:
                s = _read_source(p)
            except OSError:
                continue
            if s and s.strip():
                return s
    return None


class TestPipelineSqlContract:
    """Read the pipeline source so a formula change there breaks these tests."""

    @pytest.fixture
    def src(self):
        s = _pipeline_source()
        if not s:
            msg = "pipelines/resilience_scoring_pipeline(.py|.ipynb) source not readable here"
            if os.environ.get("CI"):
                pytest.fail(msg + " (CI set: SQL drift guard must run, not skip)")
            pytest.skip(msg)
        return s

    def test_sla_boost_case_matches_reference(self, src):
        m = re.search(
            r"WHEN\s+'premium_plus'\s+THEN\s+([\d.]+)\s+WHEN\s+'premium'\s+THEN\s+([\d.]+)\s+ELSE\s+([\d.]+)",
            src,
        )
        assert m, "SLA boost CASE not found in pipeline SQL"
        assert tuple(float(x) for x in m.groups()) == (
            SLA_BOOST["premium_plus"], SLA_BOOST["premium"], SLA_BOOST["standard"])

    def test_overall_is_capped_weighted_sum_plus_boost(self, src):
        flat = re.sub(r"\s+", " ", src)
        assert re.search(
            r"LEAST\(100\.0, ROUND\(ROUND\(0\.4 \* path_diversity_score \+ 0\.3 \* hazard_exposure_score "
            r"\+ 0\.3 \* telemetry_health_score, 2\) \+ sla_boost, 2\)\)",
            flat,
        ), "overall_score expression drifted from scoring_reference.composite_score"

    def test_revenue_at_risk_expression(self, src):
        flat = re.sub(r"\s+", " ", src)
        assert "ROUND(mrc_usd * (1 - overall_score / 100.0), 2) AS revenue_at_risk_usd" in flat


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
    """Revenue at risk = MRC * (1 - overall_score / 100), overall_score = boosted V2 score."""

    revenue_at_risk = staticmethod(revenue_at_risk)

    def test_premium_plus_boost_reduces_risk(self):
        """Same components, premium_plus tier -> +5 score -> lower RaR."""
        std = self.revenue_at_risk(10000, composite_score(50, 50, 50, "standard"))
        pp = self.revenue_at_risk(10000, composite_score(50, 50, 50, "premium_plus"))
        assert std == 5000.0
        assert pp == 4500.0

    def test_capped_score_zero_risk(self):
        assert self.revenue_at_risk(10000, composite_score(97, 97, 97, "premium_plus")) == 0.0

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
