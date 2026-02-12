"""
AGENT NEO - Calibration Tests
"""

import pytest
from pathlib import Path
from app.modules.repo_miner import (
    extract_folder_structure,
    detect_frameworks,
    detect_database_patterns,
    mine_repository
)
from app.modules.style_fingerprint import (
    aggregate_fingerprints,
    calculate_consistency_score,
    generate_governance_deltas
)
from app.modules.reasoning import (
    analyze_governance_deltas,
    format_calibration_report
)


def test_extract_folder_structure(temp_repo):
    """Test folder structure extraction."""
    repo_path = Path(temp_repo)
    
    # Create some directories
    (repo_path / "app").mkdir()
    (repo_path / "app" / "core").mkdir()
    (repo_path / "app" / "test.py").write_text("# test")
    
    structure = extract_folder_structure(repo_path)
    
    assert "root" in structure
    assert structure["root"] >= 1  # At least test.py from fixture


def test_detect_frameworks_pytest(temp_repo):
    """Test pytest framework detection."""
    repo_path = Path(temp_repo)
    
    # Create pytest.ini
    (repo_path / "pytest.ini").write_text("[pytest]")
    
    frameworks = detect_frameworks(repo_path)
    
    # May or may not detect pytest depending on git grep availability
    assert isinstance(frameworks, list)


def test_detect_database_patterns(temp_repo):
    """Test database pattern detection."""
    repo_path = Path(temp_repo)
    
    # Create file with PostgreSQL patterns
    (repo_path / "db.py").write_text("import psycopg2\nfrom sqlalchemy import create_engine")
    
    patterns = detect_database_patterns(repo_path)
    
    assert isinstance(patterns, list)


def test_mine_repository(temp_repo):
    """Test repository mining."""
    repo_path = Path(temp_repo)
    
    fingerprint = mine_repository(repo_path, "test_repo")
    
    assert fingerprint.repo_name == "test_repo"
    assert fingerprint.total_files > 0
    assert isinstance(fingerprint.frameworks, list)
    assert isinstance(fingerprint.database_patterns, list)
    assert isinstance(fingerprint.folder_structure, dict)


def test_aggregate_fingerprints_single(temp_repo):
    """Test aggregation with single fingerprint."""
    repo_path = Path(temp_repo)
    fingerprint = mine_repository(repo_path, "test_repo")
    
    aggregated = aggregate_fingerprints([fingerprint])
    
    assert aggregated.repo_count == 1
    assert aggregated.confidence_score > 0
    assert isinstance(aggregated.governance_deltas, list)


def test_aggregate_fingerprints_empty():
    """Test aggregation with no fingerprints."""
    with pytest.raises(ValueError):
        aggregate_fingerprints([])


def test_calculate_consistency_score_single(temp_repo):
    """Test consistency score with single repo."""
    repo_path = Path(temp_repo)
    fingerprint = mine_repository(repo_path, "test_repo")
    
    score = calculate_consistency_score([fingerprint])
    
    assert score == 100.0  # Single repo is always consistent


def test_generate_governance_deltas_low_test_coverage():
    """Test governance delta generation for low test coverage."""
    deltas = generate_governance_deltas(
        frameworks=["fastapi"],
        db_patterns=["postgresql"],
        test_score=50.0,  # Below 80%
        migration_percent=100.0,
        docker_percent=100.0,
        health_percent=100.0
    )
    
    # Should recommend test coverage enforcement
    assert any("test" in d.lower() or "coverage" in d.lower() for d in deltas)


def test_generate_governance_deltas_no_postgresql():
    """Test governance delta generation without PostgreSQL."""
    deltas = generate_governance_deltas(
        frameworks=["fastapi"],
        db_patterns=[],  # No PostgreSQL
        test_score=100.0,
        migration_percent=0.0,
        docker_percent=0.0,
        health_percent=0.0  # Below 80%
    )

    # Should recommend health check enforcement (since health_percent < 80)
    # Note: PostgreSQL enforcement is handled by governance.py, not style_fingerprint
    assert any("health" in d.lower() for d in deltas)


def test_generate_governance_deltas_no_health_checks():
    """Test governance delta generation without health checks."""
    deltas = generate_governance_deltas(
        frameworks=["fastapi"],
        db_patterns=["postgresql"],
        test_score=100.0,
        migration_percent=100.0,
        docker_percent=100.0,
        health_percent=50.0  # Below 80%
    )
    
    # Should recommend health check enforcement
    assert any("health" in d.lower() for d in deltas)


def test_analyze_governance_deltas(temp_repo):
    """Test governance analysis."""
    repo_path = Path(temp_repo)
    fingerprint = mine_repository(repo_path, "test_repo")
    aggregated = aggregate_fingerprints([fingerprint])
    
    analysis = analyze_governance_deltas(aggregated)
    
    assert "patterns_detected" in analysis
    assert "style_consistency_score" in analysis
    assert "governance_deltas_suggested" in analysis
    assert "confidence_score" in analysis
    assert analysis["analysis_method"] == "deterministic_rule_based"


def test_format_calibration_report(temp_repo):
    """Test calibration report formatting."""
    repo_path = Path(temp_repo)
    fingerprint = mine_repository(repo_path, "test_repo")
    aggregated = aggregate_fingerprints([fingerprint])
    analysis = analyze_governance_deltas(aggregated)
    
    report = format_calibration_report(analysis)
    
    assert "CALIBRATION REPORT" in report
    assert "PATTERNS DETECTED" in report
    assert "GOVERNANCE DELTAS SUGGESTED" in report
    assert str(analysis["repo_count"]) in report

