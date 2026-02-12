"""
Tests for Reasoning Engine Module
"""

import pytest
from app.modules.reasoning_engine import (
    ReasoningResult,
    analyze_calibration_summary,
    validate_reasoning_output,
    validate_governance_delta,
    filter_calibration_deltas,
    is_tightening_rule,
    requires_user_confirmation,
    _determine_philosophy,
    _identify_strengths,
    _identify_weaknesses,
    _generate_recommendations,
    _check_over_restriction,
    _calculate_confidence
)


class TestReasoningResult:
    """Tests for ReasoningResult dataclass."""
    
    def test_to_dict(self):
        result = ReasoningResult(
            architectural_philosophy=["Enterprise-first"],
            confidence_score=0.8
        )
        d = result.to_dict()
        assert d["architectural_philosophy"] == ["Enterprise-first"]
        assert d["confidence_score"] == 0.8


class TestAnalyzeCalibrationSummary:
    """Tests for calibration summary analysis."""
    
    def test_analyze_empty_summary(self):
        summary = {"aggregated_metrics": {}, "enterprise_signals": {}}
        result = analyze_calibration_summary(summary)
        assert isinstance(result, ReasoningResult)
    
    def test_analyze_enterprise_ready(self):
        summary = {
            "aggregated_metrics": {
                "enterprise_readiness_score": 0.8,
                "postgresql_compliance_score": 0.9,
                "health_check_coverage": 0.9,
                "logging_consistency": 0.9,
                "test_coverage_consistency": 0.7,
                "consistent_patterns": ["postgresql_usage", "health_endpoints"],
                "summary_metrics": {"docker_adoption": 90}
            },
            "enterprise_signals": {
                "postgresql_compliant": True,
                "health_checks_standard": True,
                "logging_standard": True,
                "testing_standard": True
            },
            "repo_count": 5
        }
        result = analyze_calibration_summary(summary)
        assert len(result.detected_strengths) > 0
        assert result.confidence_score > 0.5


class TestValidateGovernanceDelta:
    """Tests for governance delta validation."""
    
    def test_block_weaken_postgresql(self):
        delta = {"action": "remove", "target": "postgresql_required"}
        is_valid, error = validate_governance_delta(delta)
        assert is_valid is False
        assert "BLOCKED" in error
    
    def test_block_allow_sqlite(self):
        delta = {"action": "allow", "target": "sqlite_database"}
        is_valid, error = validate_governance_delta(delta)
        assert is_valid is False
        assert "BLOCKED" in error
    
    def test_block_reduce_coverage(self):
        delta = {"action": "reduce", "target": "test_coverage", "value": 50}
        is_valid, error = validate_governance_delta(delta)
        assert is_valid is False
    
    def test_allow_tightening(self):
        delta = {"action": "enforce", "target": "strict_typing"}
        is_valid, error = validate_governance_delta(delta)
        assert is_valid is True
        assert error is None


class TestFilterCalibrationDeltas:
    """Tests for delta filtering."""
    
    def test_filter_mixed_deltas(self):
        deltas = [
            {"action": "enforce", "target": "type_checking"},
            {"action": "remove", "target": "postgresql_required"},
            {"action": "add", "target": "code_review_required"}
        ]
        approved, rejected = filter_calibration_deltas(deltas)
        assert len(approved) == 2
        assert len(rejected) == 1
    
    def test_all_approved(self):
        deltas = [
            {"action": "enforce", "target": "linting"},
            {"action": "add", "target": "documentation"}
        ]
        approved, rejected = filter_calibration_deltas(deltas)
        assert len(approved) == 2
        assert len(rejected) == 0


class TestIsTighteningRule:
    """Tests for tightening rule detection."""
    
    def test_add_is_tightening(self):
        assert is_tightening_rule({"action": "add"}) is True
    
    def test_enforce_is_tightening(self):
        assert is_tightening_rule({"action": "enforce"}) is True
    
    def test_remove_not_tightening(self):
        assert is_tightening_rule({"action": "remove"}) is False


class TestRequiresUserConfirmation:
    """Tests for user confirmation requirement."""
    
    def test_remove_requires_confirmation(self):
        assert requires_user_confirmation({"action": "remove", "target": "rule"}) is True
    
    def test_database_change_requires_confirmation(self):
        assert requires_user_confirmation({"action": "update", "target": "database_config"}) is True
    
    def test_security_change_requires_confirmation(self):
        assert requires_user_confirmation({"action": "update", "target": "security_rules"}) is True
    
    def test_simple_add_no_confirmation(self):
        assert requires_user_confirmation({"action": "add", "target": "linting_rule"}) is False


class TestValidateReasoningOutput:
    """Tests for output validation."""
    
    def test_valid_output(self):
        result = ReasoningResult(confidence_score=0.8)
        errors = validate_reasoning_output(result)
        assert errors == []
    
    def test_invalid_confidence(self):
        result = ReasoningResult(confidence_score=1.5)
        errors = validate_reasoning_output(result)
        assert len(errors) > 0


class TestConfidenceCalculation:
    """Tests for confidence score calculation."""
    
    def test_single_repo_low_confidence(self):
        summary = {"repo_count": 1}
        assert _calculate_confidence(summary) == 0.3
    
    def test_few_repos_moderate_confidence(self):
        summary = {"repo_count": 3}
        assert _calculate_confidence(summary) == 0.6
    
    def test_many_repos_high_confidence(self):
        summary = {"repo_count": 15}
        assert _calculate_confidence(summary) == 0.9

