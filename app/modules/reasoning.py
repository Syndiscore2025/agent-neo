"""
AGENT NEO - Reasoning Module
Structured governance analysis using deterministic reasoning.
"""

import json
import logging
from typing import Dict, Any, List
from dataclasses import asdict

from app.modules.style_fingerprint import AggregatedFingerprint

logger = logging.getLogger(__name__)


def analyze_governance_deltas(fingerprint: AggregatedFingerprint) -> Dict[str, Any]:
    """
    Analyze aggregated fingerprint and generate structured governance recommendations.
    
    Uses deterministic logic (no LLM) to ensure consistent, rule-based analysis.
    
    Args:
        fingerprint: Aggregated fingerprint from multiple repos
        
    Returns:
        Structured governance analysis
    """
    logger.info("Analyzing governance deltas with deterministic reasoning")
    
    # Convert to dict for analysis
    fp_dict = asdict(fingerprint)
    
    # Analyze patterns
    patterns_detected = _detect_patterns(fingerprint)
    
    # Calculate style consistency
    style_consistency = _calculate_style_consistency(fingerprint)
    
    # Generate governance recommendations
    governance_recommendations = _generate_recommendations(fingerprint)
    
    # Calculate overall confidence
    confidence = fingerprint.confidence_score
    
    return {
        "patterns_detected": patterns_detected,
        "style_consistency_score": style_consistency,
        "governance_deltas_suggested": governance_recommendations,
        "confidence_score": confidence,
        "analysis_method": "deterministic_rule_based",
        "repo_count": fingerprint.repo_count
    }


def _detect_patterns(fp: AggregatedFingerprint) -> Dict[str, Any]:
    """Detect key patterns from fingerprint."""
    return {
        "frameworks": {
            "common": fp.common_frameworks,
            "count": len(fp.common_frameworks)
        },
        "database": {
            "patterns": fp.common_database_patterns,
            "postgresql_usage": "postgresql" in fp.common_database_patterns,
            "migration_coverage": f"{fp.migration_usage_percent:.0f}%"
        },
        "testing": {
            "coverage": f"{fp.test_coverage_score:.0f}%",
            "meets_80_percent": fp.test_coverage_score >= 80
        },
        "infrastructure": {
            "docker_usage": f"{fp.docker_usage_percent:.0f}%",
            "health_checks": f"{fp.health_check_usage_percent:.0f}%"
        },
        "environment": {
            "patterns": fp.common_env_patterns,
            "has_template": "env_template_exists" in fp.common_env_patterns
        },
        "logging": {
            "patterns": fp.common_logging_patterns,
            "structured": "structured_logging" in fp.common_logging_patterns
        }
    }


def _calculate_style_consistency(fp: AggregatedFingerprint) -> float:
    """Calculate overall style consistency score."""
    return fp.consistency_score


def _generate_recommendations(fp: AggregatedFingerprint) -> List[Dict[str, Any]]:
    """Generate structured governance recommendations."""
    recommendations = []
    
    # Test coverage enforcement
    if fp.test_coverage_score < 80:
        recommendations.append({
            "category": "testing",
            "priority": "critical",
            "current_state": f"{fp.test_coverage_score:.0f}% repos have tests",
            "target_state": "100% repos with ≥80% test coverage",
            "action": "ENFORCE: Test suite requirement with 80% coverage minimum",
            "rationale": "Enterprise beta standard requires comprehensive testing"
        })
    
    # PostgreSQL enforcement
    if "postgresql" not in fp.common_database_patterns and fp.repo_count > 0:
        recommendations.append({
            "category": "database",
            "priority": "critical",
            "current_state": "PostgreSQL not consistently used",
            "target_state": "PostgreSQL for all database needs",
            "action": "ENFORCE: PostgreSQL-only database policy",
            "rationale": "Enterprise standard prohibits SQLite and in-memory databases"
        })
    
    # Migration system enforcement
    if fp.migration_usage_percent < 80 and "postgresql" in fp.common_database_patterns:
        recommendations.append({
            "category": "database",
            "priority": "high",
            "current_state": f"{fp.migration_usage_percent:.0f}% repos use migrations",
            "target_state": "100% database projects use migration system",
            "action": "ENFORCE: Alembic or equivalent migration system",
            "rationale": "Production databases require versioned schema management"
        })
    
    # Health check enforcement
    if fp.health_check_usage_percent < 80:
        recommendations.append({
            "category": "infrastructure",
            "priority": "high",
            "current_state": f"{fp.health_check_usage_percent:.0f}% repos have health checks",
            "target_state": "100% services with /health/live and /health/ready",
            "action": "ENFORCE: Health check endpoints for all services",
            "rationale": "Production readiness requires liveness and readiness probes"
        })
    
    # Docker standardization
    if fp.docker_usage_percent > 50 and fp.docker_usage_percent < 100:
        recommendations.append({
            "category": "infrastructure",
            "priority": "medium",
            "current_state": f"{fp.docker_usage_percent:.0f}% repos use Docker",
            "target_state": "100% services containerized",
            "action": "STANDARDIZE: Docker/docker-compose for all services",
            "rationale": "Consistent deployment strategy across all projects"
        })
    
    # Structured logging
    if "structured_logging" not in fp.common_logging_patterns:
        recommendations.append({
            "category": "observability",
            "priority": "medium",
            "current_state": "Structured logging not consistently used",
            "target_state": "JSON structured logging across all services",
            "action": "ENFORCE: Structured JSON logging with standard fields",
            "rationale": "Enterprise observability requires parseable log formats"
        })
    
    # Environment variable templates
    if "env_template_exists" not in fp.common_env_patterns:
        recommendations.append({
            "category": "configuration",
            "priority": "low",
            "current_state": "Environment templates not consistently provided",
            "target_state": ".env.example in all projects",
            "action": "STANDARDIZE: .env.example template files",
            "rationale": "Secure configuration management and onboarding"
        })
    
    return recommendations


def format_calibration_report(analysis: Dict[str, Any]) -> str:
    """Format analysis into human-readable calibration report."""
    report_lines = [
        "=" * 60,
        "CALIBRATION REPORT",
        "=" * 60,
        "",
        f"Repositories Analyzed: {analysis['repo_count']}",
        f"Confidence Score: {analysis['confidence_score']:.1f}/100",
        f"Style Consistency: {analysis['style_consistency_score']:.1f}/100",
        "",
        "PATTERNS DETECTED:",
        "-" * 60,
    ]
    
    patterns = analysis['patterns_detected']
    
    # Frameworks
    if patterns['frameworks']['common']:
        report_lines.append(f"  Frameworks: {', '.join(patterns['frameworks']['common'])}")
    
    # Database
    report_lines.append(f"  PostgreSQL Usage: {'Yes' if patterns['database']['postgresql_usage'] else 'No'}")
    report_lines.append(f"  Migration Coverage: {patterns['database']['migration_coverage']}")
    
    # Testing
    report_lines.append(f"  Test Coverage: {patterns['testing']['coverage']}")
    
    # Infrastructure
    report_lines.append(f"  Docker Usage: {patterns['infrastructure']['docker_usage']}")
    report_lines.append(f"  Health Checks: {patterns['infrastructure']['health_checks']}")
    
    report_lines.extend(["", "GOVERNANCE DELTAS SUGGESTED:", "-" * 60])
    
    recommendations = analysis['governance_deltas_suggested']
    for i, rec in enumerate(recommendations, 1):
        report_lines.append(f"\n{i}. [{rec['priority'].upper()}] {rec['category'].upper()}")
        report_lines.append(f"   Current: {rec['current_state']}")
        report_lines.append(f"   Target:  {rec['target_state']}")
        report_lines.append(f"   Action:  {rec['action']}")
    
    report_lines.extend(["", "=" * 60])
    
    return "\n".join(report_lines)

