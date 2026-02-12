"""
Tests for Fingerprint Aggregator Module
"""

import pytest
from app.modules.fingerprint_aggregator import (
    AggregatedMetrics,
    aggregate_fingerprints,
    _calculate_consistency,
    generate_calibration_summary,
    _get_action_priority
)


class TestAggregatedMetrics:
    """Tests for AggregatedMetrics dataclass."""
    
    def test_to_dict(self):
        metrics = AggregatedMetrics(
            consistency_score=0.8,
            enterprise_readiness_score=0.7
        )
        d = metrics.to_dict()
        assert d["consistency_score"] == 0.8
        assert d["enterprise_readiness_score"] == 0.7


class TestCalculateConsistency:
    """Tests for consistency calculation."""
    
    def test_all_true(self):
        values = [True, True, True, True]
        assert _calculate_consistency(values) == 1.0
    
    def test_all_false(self):
        values = [False, False, False, False]
        assert _calculate_consistency(values) == 1.0
    
    def test_half_and_half(self):
        values = [True, True, False, False]
        assert _calculate_consistency(values) == 0.0
    
    def test_mostly_true(self):
        values = [True, True, True, False]
        consistency = _calculate_consistency(values)
        assert 0.4 < consistency < 0.6
    
    def test_empty(self):
        assert _calculate_consistency([]) == 0.0


class TestAggregateFingerprints:
    """Tests for fingerprint aggregation."""
    
    def test_empty_fingerprints(self):
        result = aggregate_fingerprints([])
        assert isinstance(result, AggregatedMetrics)
        assert result.consistency_score == 0.0
    
    def test_single_fingerprint(self):
        fingerprints = [{
            "postgresql_detected": True,
            "health_endpoints_detected": True,
            "structured_logging_detected": True,
            "docker_present": True,
            "ci_present": True,
            "test_folder_present": True,
            "env_var_usage": True,
            "migration_tool": "alembic",
            "test_to_code_ratio": 0.5,
            "frameworks_detected": ["fastapi"],
            "full_name": "owner/repo"
        }]
        result = aggregate_fingerprints(fingerprints)
        assert result.postgresql_compliance_score == 1.0
        assert result.health_check_coverage == 1.0
    
    def test_mixed_fingerprints(self):
        fingerprints = [
            {
                "postgresql_detected": True,
                "health_endpoints_detected": True,
                "structured_logging_detected": True,
                "docker_present": True,
                "ci_present": True,
                "test_folder_present": True,
                "env_var_usage": True,
                "migration_tool": "alembic",
                "test_to_code_ratio": 0.5,
                "frameworks_detected": ["fastapi"],
                "full_name": "owner/repo1"
            },
            {
                "postgresql_detected": False,
                "health_endpoints_detected": False,
                "structured_logging_detected": False,
                "docker_present": False,
                "ci_present": False,
                "test_folder_present": False,
                "env_var_usage": False,
                "migration_tool": None,
                "test_to_code_ratio": 0.0,
                "frameworks_detected": [],
                "full_name": "owner/repo2"
            }
        ]
        result = aggregate_fingerprints(fingerprints)
        assert result.postgresql_compliance_score == 0.5
        assert result.consistency_score < 0.5  # High inconsistency
        assert result.drift_score > 0.5
    
    def test_weakness_clusters(self):
        fingerprints = [{
            "postgresql_detected": False,
            "health_endpoints_detected": False,
            "structured_logging_detected": False,
            "docker_present": False,
            "ci_present": False,
            "test_folder_present": False,
            "env_var_usage": False,
            "migration_tool": None,
            "test_to_code_ratio": 0.0,
            "frameworks_detected": [],
            "full_name": "owner/repo"
        }]
        result = aggregate_fingerprints(fingerprints)
        assert len(result.weakness_clusters) > 0
        assert any(c["severity"] == "critical" for c in result.weakness_clusters)
    
    def test_risk_hotspots(self):
        fingerprints = [{
            "postgresql_detected": False,
            "health_endpoints_detected": False,
            "structured_logging_detected": False,
            "docker_present": False,
            "ci_present": False,
            "test_folder_present": False,
            "env_var_usage": False,
            "migration_tool": None,
            "test_to_code_ratio": 0.0,
            "frameworks_detected": [],
            "full_name": "owner/repo"
        }]
        result = aggregate_fingerprints(fingerprints)
        assert len(result.risk_hotspots) > 0


class TestCalibrationSummary:
    """Tests for calibration summary generation."""
    
    def test_generate_summary(self):
        fingerprints = [{"full_name": "owner/repo"}]
        aggregated = AggregatedMetrics(
            enterprise_readiness_score=0.8,
            postgresql_compliance_score=0.9,
            health_check_coverage=0.9,
            logging_consistency=0.9,
            test_coverage_consistency=0.6
        )
        summary = generate_calibration_summary(fingerprints, aggregated)
        assert summary["repo_count"] == 1
        assert "enterprise_signals" in summary
        assert summary["enterprise_signals"]["postgresql_compliant"] is True

