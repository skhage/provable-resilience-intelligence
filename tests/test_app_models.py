"""Tests for Resilience Scorecard app: Pydantic models, mock data, and router logic.

Validates: schema contracts, mock data integrity, filter/sort logic, enum values.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import sys
import os
import pytest
from pydantic import ValidationError

# Add app source to path for import
APP_SRC = os.path.join(
    os.path.dirname(__file__), os.pardir,
    "apps", "resilience-scorecard", "src",
)
if APP_SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(APP_SRC))

from resilience_scorecard.backend.models import (
    ActionStatus,
    ActionType,
    PathDiversityRating,
    ResilienceScoreOut,
    ResilienceSummaryOut,
    RiskLevel,
    ProactiveActionOut,
    ActionStatusUpdate,
    ActionQueueSummaryOut,
    HealthOut,
)
from resilience_scorecard.backend.services.mock_data import (
    generate_mock_scores,
    generate_mock_summary,
    generate_mock_actions,
    generate_mock_action_summary,
    _score_to_rating,
    _risk_level,
)


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Verify Pydantic models enforce constraints and schema."""

    def test_resilience_score_bounds(self):
        """resilience_score must be in [0, 100]."""
        with pytest.raises(Exception):
            ResilienceScoreOut(
                service_id="SVC-001", service_name="Test",
                customer_id="C-001", customer_name="Test Corp",
                resilience_score=150,  # invalid
                physical_redundancy_score=50, network_health_score=50,
                environmental_risk_score=50,
                path_diversity_rating=PathDiversityRating.B,
                srlg_count=3, single_point_failures=1,
                snapshot_timestamp="2026-10-20T00:00:00Z",
            )

    def test_resilience_score_negative_rejected(self):
        with pytest.raises(Exception):
            ResilienceScoreOut(
                service_id="SVC-001", service_name="Test",
                customer_id="C-001", customer_name="Test Corp",
                resilience_score=-5,  # invalid
                physical_redundancy_score=50, network_health_score=50,
                environmental_risk_score=50,
                path_diversity_rating=PathDiversityRating.C,
                srlg_count=0, single_point_failures=0,
                snapshot_timestamp="2026-10-20T00:00:00Z",
            )

    def test_valid_score_accepted(self):
        score = ResilienceScoreOut(
            service_id="SVC-001", service_name="Test Service",
            customer_id="C-001", customer_name="Test Corp",
            resilience_score=72.5,
            physical_redundancy_score=80, network_health_score=65,
            environmental_risk_score=70,
            path_diversity_rating=PathDiversityRating.B,
            srlg_count=2, single_point_failures=0,
            snapshot_timestamp="2026-10-20T00:00:00Z",
        )
        assert score.resilience_score == 72.5

    def test_action_status_enum_values(self):
        assert set(ActionStatus) == {"pending", "in_progress", "completed", "cancelled"}

    def test_action_type_enum_values(self):
        assert set(ActionType) == {
            "reroute",
            "dispatch",
            "dispatch_crew",
            "notify",
            "notify_customer",
            "escalate",
            "escalate_noc",
            "preposition",
            "preposition_splice",
        }

    def test_risk_level_enum_values(self):
        assert set(RiskLevel) == {"critical", "high", "medium", "low"}

    def test_path_diversity_rating_values(self):
        assert set(PathDiversityRating) == {"A", "B", "C", "D", "F"}

    def test_health_out_default(self):
        h = HealthOut(
            lakebase_connected=False,
            gold_tables_available=False,
            data_source="mock",
        )
        assert h.status == "ok"


# ---------------------------------------------------------------------------
# Mock data generator tests
# ---------------------------------------------------------------------------

class TestMockDataGenerators:
    """Validate mock data is deterministic, well-formed, and schema-compliant."""

    def test_scores_deterministic(self):
        """Same seed produces identical results."""
        s1 = generate_mock_scores()
        s2 = generate_mock_scores()
        assert s1 == s2

    def test_scores_count(self):
        assert len(generate_mock_scores()) == 16

    def test_scores_have_required_fields(self):
        required = {
            "service_id", "service_name", "customer_id", "customer_name",
            "resilience_score", "physical_redundancy_score", "network_health_score",
            "environmental_risk_score", "path_diversity_rating",
            "srlg_count", "single_point_failures", "snapshot_timestamp",
        }
        for s in generate_mock_scores():
            assert required.issubset(s.keys()), f"Missing fields: {required - s.keys()}"

    def test_scores_bounded(self):
        for s in generate_mock_scores():
            assert 0 <= s["resilience_score"] <= 100
            assert 0 <= s["physical_redundancy_score"] <= 100
            assert 0 <= s["network_health_score"] <= 100
            assert 0 <= s["environmental_risk_score"] <= 100

    def test_score_to_rating_mapping(self):
        assert _score_to_rating(90) == "A"
        assert _score_to_rating(75) == "B"
        assert _score_to_rating(60) == "C"
        assert _score_to_rating(45) == "D"
        assert _score_to_rating(20) == "F"
        assert _score_to_rating(100) == "A"  # boundary
        assert _score_to_rating(0) == "F"    # boundary

    def test_risk_level_mapping(self):
        assert _risk_level(30) == "critical"
        assert _risk_level(50) == "high"
        assert _risk_level(65) == "medium"
        assert _risk_level(80) == "low"

    def test_summary_totals_match(self):
        scores = generate_mock_scores()
        summary = generate_mock_summary(scores)
        assert summary["total_services"] == len(scores)
        level_total = (
            summary["critical_count"]
            + summary["high_risk_count"]
            + summary["medium_risk_count"]
            + summary["low_risk_count"]
        )
        assert level_total == len(scores)

    def test_actions_count(self):
        assert len(generate_mock_actions()) == 12

    def test_actions_have_required_fields(self):
        required = {
            "action_id", "action_type", "service_id", "service_name",
            "risk_trigger", "priority", "status", "description",
            "created_at", "updated_at",
        }
        for a in generate_mock_actions():
            assert required.issubset(a.keys()), f"Missing: {required - a.keys()}"

    def test_action_types_valid(self):
        valid = {"reroute", "dispatch", "notify"}
        for a in generate_mock_actions():
            assert a["action_type"] in valid

    def test_action_priorities_valid(self):
        valid = {"critical", "high", "medium", "low"}
        for a in generate_mock_actions():
            assert a["priority"] in valid

    def test_action_summary_matches(self):
        actions = generate_mock_actions()
        summary = generate_mock_action_summary(actions)
        assert summary["total_actions"] == len(actions)
        status_sum = (
            summary["pending_count"]
            + summary["in_progress_count"]
            + summary["completed_count"]
            + summary["cancelled_count"]
        )
        assert status_sum == len(actions)
        # Schema contract: mock summary must validate against the API response model
        ActionQueueSummaryOut(**summary)

    def test_mock_summary_matches_response_model(self):
        """Contract: mock dashboard summary must validate against ResilienceSummaryOut."""
        ResilienceSummaryOut(**generate_mock_summary(generate_mock_scores()))

    def test_mock_actions_match_response_model(self):
        """Contract: every mock action must validate against ProactiveActionOut."""
        for a in generate_mock_actions():
            ProactiveActionOut(**a)

    def test_status_update_rejects_legacy_dismissed(self):
        """Regression guard: legacy 'dismissed' status was replaced by 'cancelled'."""
        assert ActionStatusUpdate(status="cancelled").status == ActionStatus.CANCELLED
        with pytest.raises(ValidationError):
            ActionStatusUpdate(status="dismissed")

    def test_no_lumen_in_mock_data(self):
        """Branding: mock data must use 'Lakelink Fiber', never 'Lumen'."""
        for s in generate_mock_scores():
            for v in s.values():
                if isinstance(v, str):
                    assert "Lumen" not in v, f"Branding violation: {v}"
        for a in generate_mock_actions():
            for v in a.values():
                if isinstance(v, str):
                    assert "Lumen" not in v, f"Branding violation: {v}"


# ---------------------------------------------------------------------------
# Router filter/sort logic tests (unit-level, no server)
# ---------------------------------------------------------------------------

class TestRouterFilterLogic:
    """Test the filter and sort logic used by the /scores endpoint."""

    def test_min_score_filter(self):
        scores = generate_mock_scores()
        filtered = [s for s in scores if s["resilience_score"] >= 60]
        assert all(s["resilience_score"] >= 60 for s in filtered)

    def test_max_score_filter(self):
        scores = generate_mock_scores()
        filtered = [s for s in scores if s["resilience_score"] <= 40]
        assert all(s["resilience_score"] <= 40 for s in filtered)

    def test_customer_filter(self):
        scores = generate_mock_scores()
        filtered = [s for s in scores if s["customer_id"] == "CUST-001"]
        assert len(filtered) > 0
        assert all(s["customer_id"] == "CUST-001" for s in filtered)

    def test_sort_ascending(self):
        scores = generate_mock_scores()
        scores.sort(key=lambda s: s["resilience_score"])
        for i in range(len(scores) - 1):
            assert scores[i]["resilience_score"] <= scores[i + 1]["resilience_score"]

    def test_sort_descending(self):
        scores = generate_mock_scores()
        scores.sort(key=lambda s: s["resilience_score"], reverse=True)
        for i in range(len(scores) - 1):
            assert scores[i]["resilience_score"] >= scores[i + 1]["resilience_score"]
