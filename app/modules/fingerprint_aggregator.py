"""
AGENT NEO - Fingerprint Aggregator Module

Aggregates fingerprints across multiple repositories to compute
consistency scores, drift analysis, and enterprise readiness metrics.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from collections import Counter
import statistics

logger = logging.getLogger(__name__)


@dataclass
class AggregatedMetrics:
    """Aggregated metrics from multiple repository fingerprints."""
    
    # Consistency scores (0-1)
    consistency_score: float = 0.0
    drift_score: float = 0.0
    enterprise_readiness_score: float = 0.0
    postgresql_compliance_score: float = 0.0
    test_coverage_consistency: float = 0.0
    health_check_coverage: float = 0.0
    logging_consistency: float = 0.0
    
    # Pattern analysis
    consistent_patterns: List[str] = field(default_factory=list)
    inconsistent_patterns: List[str] = field(default_factory=list)
    weakness_clusters: List[Dict] = field(default_factory=list)
    architectural_bias: List[str] = field(default_factory=list)
    risk_hotspots: List[Dict] = field(default_factory=list)
    
    # Summary metrics
    summary_metrics: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "consistency_score": self.consistency_score,
            "drift_score": self.drift_score,
            "enterprise_readiness_score": self.enterprise_readiness_score,
            "postgresql_compliance_score": self.postgresql_compliance_score,
            "test_coverage_consistency": self.test_coverage_consistency,
            "health_check_coverage": self.health_check_coverage,
            "logging_consistency": self.logging_consistency,
            "consistent_patterns": self.consistent_patterns,
            "inconsistent_patterns": self.inconsistent_patterns,
            "weakness_clusters": self.weakness_clusters,
            "architectural_bias": self.architectural_bias,
            "risk_hotspots": self.risk_hotspots,
            "summary_metrics": self.summary_metrics
        }


def aggregate_fingerprints(fingerprints: List[dict]) -> AggregatedMetrics:
    """
    Aggregate fingerprints from multiple repositories.
    
    Args:
        fingerprints: List of fingerprint dicts from extract_fingerprint()
        
    Returns:
        AggregatedMetrics with cross-repo analysis
    """
    if not fingerprints:
        return AggregatedMetrics()
    
    metrics = AggregatedMetrics()
    n = len(fingerprints)
    
    # Extract boolean patterns
    postgresql_usage = [f.get("postgresql_detected", False) for f in fingerprints]
    health_endpoints = [f.get("health_endpoints_detected", False) for f in fingerprints]
    structured_logging = [f.get("structured_logging_detected", False) for f in fingerprints]
    docker_usage = [f.get("docker_present", False) for f in fingerprints]
    ci_usage = [f.get("ci_present", False) for f in fingerprints]
    test_folders = [f.get("test_folder_present", False) for f in fingerprints]
    env_vars = [f.get("env_var_usage", False) for f in fingerprints]
    migrations = [f.get("migration_tool") is not None for f in fingerprints]
    
    # Calculate coverage percentages
    postgresql_pct = sum(postgresql_usage) / n
    health_pct = sum(health_endpoints) / n
    logging_pct = sum(structured_logging) / n
    docker_pct = sum(docker_usage) / n
    ci_pct = sum(ci_usage) / n
    test_pct = sum(test_folders) / n
    env_var_pct = sum(env_vars) / n
    migration_pct = sum(migrations) / n
    
    # Enterprise readiness score (weighted)
    metrics.enterprise_readiness_score = round(
        postgresql_pct * 0.15 +
        health_pct * 0.15 +
        logging_pct * 0.10 +
        test_pct * 0.20 +
        ci_pct * 0.15 +
        docker_pct * 0.10 +
        migration_pct * 0.10 +
        env_var_pct * 0.05,
        2
    )
    
    # PostgreSQL compliance
    metrics.postgresql_compliance_score = round(postgresql_pct, 2)
    
    # Health check coverage
    metrics.health_check_coverage = round(health_pct, 2)
    
    # Logging consistency
    metrics.logging_consistency = round(logging_pct, 2)
    
    # Test coverage consistency
    test_ratios = [f.get("test_to_code_ratio", 0) for f in fingerprints]
    if test_ratios:
        avg_ratio = statistics.mean(test_ratios)
        if avg_ratio > 0:
            stdev = statistics.stdev(test_ratios) if len(test_ratios) > 1 else 0
            metrics.test_coverage_consistency = round(max(0, 1 - (stdev / avg_ratio)), 2)
        else:
            metrics.test_coverage_consistency = 0.0
    
    # Overall consistency score
    pattern_consistencies = [
        _calculate_consistency(postgresql_usage),
        _calculate_consistency(health_endpoints),
        _calculate_consistency(structured_logging),
        _calculate_consistency(docker_usage),
        _calculate_consistency(ci_usage),
        _calculate_consistency(test_folders)
    ]
    metrics.consistency_score = round(statistics.mean(pattern_consistencies), 2)
    
    # Drift score (inverse of consistency)
    metrics.drift_score = round(1 - metrics.consistency_score, 2)
    
    # Identify consistent patterns (>80% adoption)
    if postgresql_pct >= 0.8:
        metrics.consistent_patterns.append("postgresql_usage")
    if health_pct >= 0.8:
        metrics.consistent_patterns.append("health_endpoints")
    if logging_pct >= 0.8:
        metrics.consistent_patterns.append("structured_logging")
    if docker_pct >= 0.8:
        metrics.consistent_patterns.append("docker_containerization")
    if ci_pct >= 0.8:
        metrics.consistent_patterns.append("ci_cd_pipeline")
    if test_pct >= 0.8:
        metrics.consistent_patterns.append("test_infrastructure")

    # Identify inconsistent patterns (<50% adoption, >20% adoption)
    if 0.2 < postgresql_pct < 0.5:
        metrics.inconsistent_patterns.append("postgresql_usage")
    if 0.2 < health_pct < 0.5:
        metrics.inconsistent_patterns.append("health_endpoints")
    if 0.2 < logging_pct < 0.5:
        metrics.inconsistent_patterns.append("structured_logging")
    if 0.2 < docker_pct < 0.5:
        metrics.inconsistent_patterns.append("docker_containerization")
    if 0.2 < ci_pct < 0.5:
        metrics.inconsistent_patterns.append("ci_cd_pipeline")
    if 0.2 < test_pct < 0.5:
        metrics.inconsistent_patterns.append("test_infrastructure")

    # Identify weakness clusters (<20% adoption)
    if postgresql_pct < 0.2:
        metrics.weakness_clusters.append({
            "pattern": "postgresql_usage",
            "adoption_rate": round(postgresql_pct, 2),
            "severity": "critical"
        })
    if health_pct < 0.2:
        metrics.weakness_clusters.append({
            "pattern": "health_endpoints",
            "adoption_rate": round(health_pct, 2),
            "severity": "high"
        })
    if test_pct < 0.2:
        metrics.weakness_clusters.append({
            "pattern": "test_infrastructure",
            "adoption_rate": round(test_pct, 2),
            "severity": "critical"
        })
    if ci_pct < 0.2:
        metrics.weakness_clusters.append({
            "pattern": "ci_cd_pipeline",
            "adoption_rate": round(ci_pct, 2),
            "severity": "high"
        })

    # Architectural bias
    frameworks = []
    for f in fingerprints:
        frameworks.extend(f.get("frameworks_detected", []))
    framework_counts = Counter(frameworks)
    if framework_counts:
        dominant = framework_counts.most_common(2)
        for fw, count in dominant:
            if count / n >= 0.3:
                metrics.architectural_bias.append(fw)

    # Risk hotspots (repos with multiple weaknesses)
    for f in fingerprints:
        weaknesses = []
        if not f.get("postgresql_detected"):
            weaknesses.append("no_postgresql")
        if not f.get("health_endpoints_detected"):
            weaknesses.append("no_health_endpoints")
        if not f.get("test_folder_present"):
            weaknesses.append("no_tests")
        if not f.get("ci_present"):
            weaknesses.append("no_ci")

        if len(weaknesses) >= 3:
            metrics.risk_hotspots.append({
                "repo": f.get("full_name", f.get("repo_name", "unknown")),
                "weaknesses": weaknesses,
                "risk_level": "high" if len(weaknesses) >= 4 else "medium"
            })

    # Summary metrics
    primary_languages = [f.get("primary_language") for f in fingerprints if f.get("primary_language")]
    lang_counts = Counter(primary_languages)

    metrics.summary_metrics = {
        "total_repos": n,
        "total_files": sum(f.get("total_files", 0) for f in fingerprints),
        "total_lines": sum(f.get("total_lines", 0) for f in fingerprints),
        "primary_languages": dict(lang_counts.most_common(5)),
        "avg_module_depth": round(
            statistics.mean([f.get("module_depth_avg", 0) for f in fingerprints]), 2
        ),
        "avg_test_ratio": round(
            statistics.mean([f.get("test_to_code_ratio", 0) for f in fingerprints]), 3
        ),
        "postgresql_adoption": round(postgresql_pct * 100, 1),
        "health_endpoint_adoption": round(health_pct * 100, 1),
        "ci_adoption": round(ci_pct * 100, 1),
        "docker_adoption": round(docker_pct * 100, 1)
    }

    return metrics


def _calculate_consistency(values: List[bool]) -> float:
    """Calculate consistency score for a boolean pattern."""
    if not values:
        return 0.0

    true_count = sum(values)
    n = len(values)

    # Consistency is high when all values are same (all True or all False)
    # Maximum inconsistency is at 50%
    ratio = true_count / n
    return abs(2 * ratio - 1)  # Returns 1 when all same, 0 when 50/50


def generate_calibration_summary(
    fingerprints: List[dict],
    aggregated: AggregatedMetrics
) -> dict:
    """
    Generate a summary for reasoning layer input.

    Args:
        fingerprints: Individual repo fingerprints
        aggregated: Aggregated metrics

    Returns:
        Summary dict suitable for reasoning engine
    """
    return {
        "repo_count": len(fingerprints),
        "aggregated_metrics": aggregated.to_dict(),
        "enterprise_signals": {
            "postgresql_compliant": aggregated.postgresql_compliance_score >= 0.8,
            "health_checks_standard": aggregated.health_check_coverage >= 0.8,
            "logging_standard": aggregated.logging_consistency >= 0.8,
            "testing_standard": aggregated.test_coverage_consistency >= 0.5,
            "overall_enterprise_ready": aggregated.enterprise_readiness_score >= 0.7
        },
        "action_priority": _get_action_priority(aggregated),
        "repos_analyzed": [f.get("full_name") for f in fingerprints]
    }


def _get_action_priority(aggregated: AggregatedMetrics) -> List[str]:
    """Determine priority actions based on aggregated metrics."""
    priorities = []

    if aggregated.postgresql_compliance_score < 0.5:
        priorities.append("enforce_postgresql")
    if aggregated.health_check_coverage < 0.5:
        priorities.append("add_health_endpoints")
    if aggregated.test_coverage_consistency < 0.3:
        priorities.append("standardize_testing")
    if aggregated.logging_consistency < 0.5:
        priorities.append("implement_structured_logging")
    if aggregated.enterprise_readiness_score < 0.5:
        priorities.append("enterprise_hardening")

    return priorities

