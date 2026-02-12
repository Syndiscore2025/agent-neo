"""
AGENT NEO - Reasoning Engine Module

Deterministic governance reasoning engine for calibration.
Rules: temperature=0, strict JSON output, no prose, enterprise-first.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json

logger = logging.getLogger(__name__)


@dataclass
class ReasoningResult:
    """Result from the reasoning engine."""
    architectural_philosophy: List[str] = field(default_factory=list)
    detected_strengths: List[str] = field(default_factory=list)
    detected_weaknesses: List[str] = field(default_factory=list)
    hardening_recommendations: List[Dict] = field(default_factory=list)
    over_restriction_flags: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "architectural_philosophy": self.architectural_philosophy,
            "detected_strengths": self.detected_strengths,
            "detected_weaknesses": self.detected_weaknesses,
            "hardening_recommendations": self.hardening_recommendations,
            "over_restriction_flags": self.over_restriction_flags,
            "confidence_score": self.confidence_score
        }


# Enterprise governance rules
ENTERPRISE_RULES = {
    "postgresql_required": {
        "threshold": 0.5,
        "metric": "postgresql_compliance_score",
        "recommendation": "Enforce PostgreSQL as mandatory database",
        "confidence": 0.95
    },
    "health_endpoints_required": {
        "threshold": 0.5,
        "metric": "health_check_coverage",
        "recommendation": "Add /health/live and /health/ready endpoints",
        "confidence": 0.90
    },
    "structured_logging_required": {
        "threshold": 0.5,
        "metric": "logging_consistency",
        "recommendation": "Implement structured JSON logging",
        "confidence": 0.85
    },
    "test_coverage_required": {
        "threshold": 0.3,
        "metric": "test_coverage_consistency",
        "recommendation": "Establish 80% minimum test coverage",
        "confidence": 0.90
    },
    "ci_pipeline_required": {
        "threshold": 0.5,
        "metric_path": ["summary_metrics", "ci_adoption"],
        "threshold_pct": 50,
        "recommendation": "Add CI/CD pipeline for all repositories",
        "confidence": 0.85
    }
}


def analyze_calibration_summary(summary: dict) -> ReasoningResult:
    """
    Analyze calibration summary and generate governance recommendations.
    
    This is a deterministic analysis - no LLM, no hallucination.
    Temperature = 0 conceptually (deterministic).
    
    Args:
        summary: Calibration summary from generate_calibration_summary()
        
    Returns:
        ReasoningResult with recommendations
    """
    result = ReasoningResult()
    
    aggregated = summary.get("aggregated_metrics", {})
    enterprise_signals = summary.get("enterprise_signals", {})
    
    # Determine architectural philosophy
    result.architectural_philosophy = _determine_philosophy(aggregated, summary)
    
    # Identify strengths
    result.detected_strengths = _identify_strengths(aggregated, enterprise_signals)
    
    # Identify weaknesses
    result.detected_weaknesses = _identify_weaknesses(aggregated, enterprise_signals)
    
    # Generate hardening recommendations
    result.hardening_recommendations = _generate_recommendations(aggregated)
    
    # Check for over-restriction
    result.over_restriction_flags = _check_over_restriction(aggregated)
    
    # Calculate confidence score
    result.confidence_score = _calculate_confidence(summary)
    
    return result


def _determine_philosophy(aggregated: dict, summary: dict) -> List[str]:
    """Determine architectural philosophy from patterns."""
    philosophy = []
    
    enterprise_score = aggregated.get("enterprise_readiness_score", 0)
    if enterprise_score >= 0.7:
        philosophy.append("Enterprise-first production architecture")
    elif enterprise_score >= 0.4:
        philosophy.append("Mixed enterprise/development architecture")
    else:
        philosophy.append("Development-focused architecture")
    
    # PostgreSQL stance
    pg_score = aggregated.get("postgresql_compliance_score", 0)
    if pg_score >= 0.8:
        philosophy.append("PostgreSQL-first database strategy")
    elif pg_score >= 0.3:
        philosophy.append("Mixed database strategy (PostgreSQL partial)")
    else:
        philosophy.append("Non-PostgreSQL database patterns detected")
    
    # Testing stance
    if aggregated.get("test_coverage_consistency", 0) >= 0.5:
        philosophy.append("Test-driven development practices")
    
    # Containerization
    docker_adoption = aggregated.get("summary_metrics", {}).get("docker_adoption", 0)
    if docker_adoption >= 80:
        philosophy.append("Container-first deployment strategy")
    
    return philosophy


def _identify_strengths(aggregated: dict, signals: dict) -> List[str]:
    """Identify organizational strengths."""
    strengths = []
    
    if signals.get("postgresql_compliant"):
        strengths.append("Consistent PostgreSQL adoption")
    if signals.get("health_checks_standard"):
        strengths.append("Standardized health check endpoints")
    if signals.get("logging_standard"):
        strengths.append("Consistent structured logging")
    if signals.get("testing_standard"):
        strengths.append("Established testing practices")
    
    consistent = aggregated.get("consistent_patterns", [])
    for pattern in consistent:
        strengths.append(f"Consistent: {pattern}")

    return strengths


def _identify_weaknesses(aggregated: dict, signals: dict) -> List[str]:
    """Identify organizational weaknesses."""
    weaknesses = []

    if not signals.get("postgresql_compliant"):
        weaknesses.append("PostgreSQL not standardized across repos")
    if not signals.get("health_checks_standard"):
        weaknesses.append("Health endpoints missing in some repos")
    if not signals.get("logging_standard"):
        weaknesses.append("Inconsistent logging practices")
    if not signals.get("testing_standard"):
        weaknesses.append("Test coverage varies significantly")

    # Check weakness clusters
    for cluster in aggregated.get("weakness_clusters", []):
        weaknesses.append(f"{cluster['severity'].upper()}: {cluster['pattern']} ({cluster['adoption_rate']*100:.0f}% adoption)")

    # Check inconsistent patterns
    for pattern in aggregated.get("inconsistent_patterns", []):
        weaknesses.append(f"Inconsistent: {pattern}")

    return weaknesses


def _generate_recommendations(aggregated: dict) -> List[Dict]:
    """Generate hardening recommendations based on metrics."""
    recommendations = []

    for rule_name, rule in ENTERPRISE_RULES.items():
        metric_value = None

        if "metric" in rule:
            metric_value = aggregated.get(rule["metric"], 0)
        elif "metric_path" in rule:
            # Navigate nested path
            value = aggregated
            for key in rule["metric_path"]:
                value = value.get(key, {}) if isinstance(value, dict) else 0
            # Ensure value is numeric before division
            if isinstance(value, (int, float)):
                metric_value = value / 100 if rule.get("threshold_pct") else value
            else:
                metric_value = 0

        if metric_value is not None and metric_value < rule["threshold"]:
            recommendations.append({
                "rule": rule["recommendation"],
                "confidence": rule["confidence"],
                "current_metric": round(metric_value, 2),
                "target_metric": rule["threshold"],
                "priority": "high" if metric_value < rule["threshold"] / 2 else "medium"
            })

    # Sort by priority and confidence
    recommendations.sort(key=lambda x: (-x["confidence"], x["priority"] == "high"))

    return recommendations


def _check_over_restriction(aggregated: dict) -> List[str]:
    """Check for potential over-restriction issues."""
    flags = []

    # Check if enforcement might be too strict
    enterprise_score = aggregated.get("enterprise_readiness_score", 0)

    if enterprise_score < 0.3:
        flags.append("Very low enterprise readiness - gradual enforcement recommended")

    # Check for dramatic changes required
    pg_score = aggregated.get("postgresql_compliance_score", 0)
    if pg_score < 0.1:
        flags.append("PostgreSQL adoption very low - migration path needed")

    consistency = aggregated.get("consistency_score", 0)
    if consistency < 0.3:
        flags.append("High drift across repos - incremental standardization recommended")

    return flags


def _calculate_confidence(summary: dict) -> float:
    """Calculate overall confidence score."""
    repo_count = summary.get("repo_count", 0)

    if repo_count < 2:
        return 0.3  # Low confidence with single repo
    elif repo_count < 5:
        return 0.6  # Moderate confidence
    elif repo_count < 10:
        return 0.8  # Good confidence
    else:
        return 0.9  # High confidence


def validate_reasoning_output(result: ReasoningResult) -> List[str]:
    """Validate reasoning output is valid JSON-compatible."""
    errors = []

    try:
        # Ensure serializable
        json.dumps(result.to_dict())
    except Exception as e:
        errors.append(f"Result not JSON serializable: {e}")

    # Validate confidence score
    if not 0 <= result.confidence_score <= 1:
        errors.append("Confidence score must be between 0 and 1")

    # Validate recommendations have required fields
    for rec in result.hardening_recommendations:
        if "rule" not in rec or "confidence" not in rec:
            errors.append("Recommendation missing required fields")

    return errors


# ============================================
# ENTERPRISE-ONLY ENFORCEMENT
# ============================================

# Rules that cannot be weakened by calibration
PROTECTED_RULES = {
    "postgresql_required": "PostgreSQL is mandatory - cannot weaken to allow SQLite",
    "health_endpoints_required": "Health endpoints are mandatory - cannot remove",
    "structured_logging_required": "Structured logging is mandatory - cannot disable",
    "test_enforcement_required": "Test enforcement is mandatory - cannot reduce coverage below 80%",
    "no_force_push": "Force push is prohibited - cannot enable",
    "no_sql_injection": "Parameterized queries mandatory - cannot allow string formatting"
}


def validate_governance_delta(delta: dict) -> tuple:
    """
    Validate a governance delta against enterprise rules.

    Returns:
        (is_valid, error_message)
    """
    action = delta.get("action", "").lower()
    target = delta.get("target", "").lower()

    # Check if attempting to weaken protected rules
    for rule_key, rule_desc in PROTECTED_RULES.items():
        if rule_key in target or target in rule_key:
            if action in ("remove", "disable", "weaken", "reduce", "lower"):
                return False, f"BLOCKED: {rule_desc}"

    # Check for specific dangerous patterns
    if "sqlite" in target and action in ("allow", "enable", "add"):
        return False, "BLOCKED: Cannot allow SQLite - PostgreSQL is mandatory"

    if "coverage" in target:
        try:
            value = delta.get("value", 80)
            if isinstance(value, (int, float)) and value < 80:
                return False, "BLOCKED: Cannot reduce test coverage below 80%"
        except (TypeError, ValueError):
            pass

    return True, None


def filter_calibration_deltas(deltas: list) -> tuple:
    """
    Filter calibration deltas to only allow enterprise-compliant changes.

    Returns:
        (approved_deltas, rejected_deltas)
    """
    approved = []
    rejected = []

    for delta in deltas:
        is_valid, error = validate_governance_delta(delta)
        if is_valid:
            approved.append(delta)
        else:
            rejected.append({
                "delta": delta,
                "reason": error
            })

    return approved, rejected


def is_tightening_rule(delta: dict) -> bool:
    """Check if a delta is tightening (making more strict) a rule."""
    action = delta.get("action", "").lower()
    return action in ("add", "enable", "enforce", "require", "increase", "tighten")


def requires_user_confirmation(delta: dict) -> bool:
    """
    Check if a delta requires explicit user confirmation.

    Loosening rules (even allowed ones) require confirmation.
    """
    action = delta.get("action", "").lower()

    # Loosening actions always require confirmation
    if action in ("remove", "disable", "reduce", "lower", "loosen", "relax"):
        return True

    # Changes to critical systems require confirmation
    target = delta.get("target", "").lower()
    critical_targets = ["database", "auth", "security", "production", "deploy"]

    for critical in critical_targets:
        if critical in target:
            return True

    return False

