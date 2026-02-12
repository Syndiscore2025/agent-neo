"""
AGENT NEO - Style Fingerprint Aggregator
Aggregates patterns across multiple repositories for calibration.
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
from collections import Counter

from app.modules.repo_miner import RepoFingerprint

logger = logging.getLogger(__name__)


@dataclass
class AggregatedFingerprint:
    """Aggregated patterns across multiple repositories."""
    repo_count: int
    common_frameworks: List[str]
    common_database_patterns: List[str]
    common_env_patterns: List[str]
    common_logging_patterns: List[str]
    test_coverage_score: float  # 0-100
    migration_usage_percent: float
    docker_usage_percent: float
    health_check_usage_percent: float
    consistency_score: float  # 0-100
    governance_deltas: List[str]
    confidence_score: float  # 0-100


def aggregate_fingerprints(fingerprints: List[RepoFingerprint]) -> AggregatedFingerprint:
    """
    Aggregate multiple repository fingerprints into unified patterns.
    
    Args:
        fingerprints: List of repository fingerprints
        
    Returns:
        AggregatedFingerprint with common patterns
    """
    if not fingerprints:
        raise ValueError("No fingerprints provided")
    
    repo_count = len(fingerprints)
    logger.info(f"Aggregating {repo_count} repository fingerprints")
    
    # Aggregate frameworks
    all_frameworks = []
    for fp in fingerprints:
        all_frameworks.extend(fp.frameworks)
    framework_counts = Counter(all_frameworks)
    # Common = used in >50% of repos
    common_frameworks = [fw for fw, count in framework_counts.items() if count >= repo_count * 0.5]
    
    # Aggregate database patterns
    all_db_patterns = []
    for fp in fingerprints:
        all_db_patterns.extend(fp.database_patterns)
    db_counts = Counter(all_db_patterns)
    common_database_patterns = [p for p, count in db_counts.items() if count >= repo_count * 0.5]
    
    # Aggregate env patterns
    all_env_patterns = []
    for fp in fingerprints:
        all_env_patterns.extend(fp.env_var_patterns)
    env_counts = Counter(all_env_patterns)
    common_env_patterns = [p for p, count in env_counts.items() if count >= repo_count * 0.5]
    
    # Aggregate logging patterns
    all_logging_patterns = []
    for fp in fingerprints:
        all_logging_patterns.extend(fp.logging_patterns)
    logging_counts = Counter(all_logging_patterns)
    common_logging_patterns = [p for p, count in logging_counts.items() if count >= repo_count * 0.5]
    
    # Calculate test coverage score
    repos_with_tests = sum(1 for fp in fingerprints if fp.test_structure.get('has_tests', False))
    test_coverage_score = (repos_with_tests / repo_count) * 100
    
    # Calculate migration usage
    repos_with_migrations = sum(1 for fp in fingerprints if fp.migration_usage is not None)
    migration_usage_percent = (repos_with_migrations / repo_count) * 100
    
    # Calculate Docker usage
    repos_with_docker = sum(1 for fp in fingerprints if fp.docker_usage)
    docker_usage_percent = (repos_with_docker / repo_count) * 100
    
    # Calculate health check usage
    repos_with_health = sum(1 for fp in fingerprints if fp.health_check_patterns)
    health_check_usage_percent = (repos_with_health / repo_count) * 100
    
    # Calculate consistency score
    consistency_score = calculate_consistency_score(fingerprints)
    
    # Generate governance deltas
    governance_deltas = generate_governance_deltas(
        common_frameworks,
        common_database_patterns,
        test_coverage_score,
        migration_usage_percent,
        docker_usage_percent,
        health_check_usage_percent
    )
    
    # Calculate confidence score
    confidence_score = calculate_confidence_score(
        repo_count,
        consistency_score,
        test_coverage_score
    )
    
    return AggregatedFingerprint(
        repo_count=repo_count,
        common_frameworks=common_frameworks,
        common_database_patterns=common_database_patterns,
        common_env_patterns=common_env_patterns,
        common_logging_patterns=common_logging_patterns,
        test_coverage_score=test_coverage_score,
        migration_usage_percent=migration_usage_percent,
        docker_usage_percent=docker_usage_percent,
        health_check_usage_percent=health_check_usage_percent,
        consistency_score=consistency_score,
        governance_deltas=governance_deltas,
        confidence_score=confidence_score
    )


def calculate_consistency_score(fingerprints: List[RepoFingerprint]) -> float:
    """
    Calculate consistency score across repositories.
    Higher score = more consistent patterns.
    """
    if len(fingerprints) < 2:
        return 100.0
    
    # Check consistency across multiple dimensions
    scores = []
    
    # Framework consistency
    all_frameworks = [set(fp.frameworks) for fp in fingerprints]
    if all_frameworks:
        framework_overlap = len(set.intersection(*all_frameworks)) if len(all_frameworks) > 1 else 0
        framework_score = (framework_overlap / max(len(fw) for fw in all_frameworks)) * 100 if all_frameworks else 0
        scores.append(framework_score)
    
    # Database pattern consistency
    all_db = [set(fp.database_patterns) for fp in fingerprints]
    if all_db:
        db_overlap = len(set.intersection(*all_db)) if len(all_db) > 1 else 0
        db_score = (db_overlap / max(len(db) for db in all_db)) * 100 if all_db else 0
        scores.append(db_score)
    
    return sum(scores) / len(scores) if scores else 50.0


def generate_governance_deltas(
    frameworks: List[str],
    db_patterns: List[str],
    test_score: float,
    migration_percent: float,
    docker_percent: float,
    health_percent: float
) -> List[str]:
    """Generate governance improvement suggestions."""
    deltas = []
    
    # Test enforcement
    if test_score < 80:
        deltas.append(f"ENFORCE: Test coverage requirement (current: {test_score:.0f}%, target: 80%)")
    
    # Migration enforcement
    if migration_percent < 80 and 'postgresql' in db_patterns:
        deltas.append(f"ENFORCE: Migration system for all DB projects (current: {migration_percent:.0f}%)")
    
    # Docker standardization
    if docker_percent > 50 and docker_percent < 100:
        deltas.append(f"STANDARDIZE: Docker usage across all projects (current: {docker_percent:.0f}%)")
    
    # Health check enforcement
    if health_percent < 80:
        deltas.append(f"ENFORCE: Health check endpoints (current: {health_percent:.0f}%, target: 100%)")
    
    return deltas


def calculate_confidence_score(repo_count: int, consistency: float, test_coverage: float) -> float:
    """Calculate confidence in calibration results."""
    # More repos = higher confidence
    repo_score = min(repo_count * 20, 100)  # Max at 5 repos
    
    # Higher consistency = higher confidence
    consistency_weight = 0.4
    repo_weight = 0.3
    test_weight = 0.3
    
    confidence = (
        consistency * consistency_weight +
        repo_score * repo_weight +
        test_coverage * test_weight
    )
    
    return min(confidence, 100.0)

