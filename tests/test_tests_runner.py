"""
Tests for tests_runner module.
"""

import pytest
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.modules.tests_runner import (
    run_tests,
    _detect_test_command,
    _extract_coverage,
    validate_coverage
)


def test_run_tests_success(temp_repo):
    """Test running tests successfully."""
    # Create a simple test command that succeeds
    result = run_tests(temp_repo, test_command="echo 'Tests passed'", timeout=10)
    
    assert result.passed is True
    assert "Tests passed" in result.output
    assert result.duration_seconds >= 0


def test_run_tests_failure(temp_repo):
    """Test running tests that fail."""
    # Use a command that fails
    if os.name == 'nt':  # Windows
        result = run_tests(temp_repo, test_command="exit 1", timeout=10)
    else:  # Unix
        result = run_tests(temp_repo, test_command="false", timeout=10)
    
    assert result.passed is False
    assert result.duration_seconds >= 0


def test_run_tests_no_command(temp_repo):
    """Test running tests with no command configured."""
    result = run_tests(temp_repo, test_command=None, timeout=10)
    
    assert result.passed is True
    assert "No test command configured" in result.output
    assert result.duration_seconds == 0.0


def test_run_tests_timeout(temp_repo):
    """Test test timeout."""
    # Mock subprocess to raise TimeoutExpired
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='test', timeout=1)

        result = run_tests(temp_repo, test_command="pytest", timeout=1)

        assert result.passed is False
        assert "timed out" in result.output.lower()


def test_run_tests_output_truncation(temp_repo):
    """Test that long output is truncated."""
    # Generate output with more than 50 lines
    if os.name == 'nt':  # Windows
        cmd = "for /L %i in (1,1,100) do @echo Line %i"
    else:  # Unix
        cmd = "for i in {1..100}; do echo Line $i; done"
    
    result = run_tests(temp_repo, test_command=cmd, timeout=10)
    
    # Output should be truncated to last 50 lines
    lines = result.output.split('\n')
    # Allow some variance for stderr/stdout merging
    assert len(lines) <= 60


def test_run_tests_with_coverage(temp_repo):
    """Test extracting coverage from output."""
    # Mock output with coverage
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Tests passed\nTOTAL 100 10 90%\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = run_tests(temp_repo, test_command="pytest", timeout=10)
        
        assert result.passed is True
        assert result.coverage_percent == 90.0


def test_run_tests_exception_handling(temp_repo):
    """Test handling of subprocess exceptions."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = Exception("Command not found")
        
        result = run_tests(temp_repo, test_command="nonexistent", timeout=10)
        
        assert result.passed is False
        assert "Test execution failed" in result.output


def test_detect_test_command_pytest(temp_repo):
    """Test detecting pytest command."""
    # Create pytest.ini
    pytest_ini = Path(temp_repo) / "pytest.ini"
    pytest_ini.write_text("[pytest]\n")

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        cmd = _detect_test_command(temp_repo)

        # Enterprise v2.0 includes coverage flags
        assert cmd == "pytest --tb=short -v --cov --cov-report=term-missing"


def test_detect_test_command_npm(temp_repo):
    """Test detecting npm test command."""
    # Create package.json
    package_json = Path(temp_repo) / "package.json"
    package_json.write_text('{"name": "test"}')
    
    cmd = _detect_test_command(temp_repo)
    
    assert cmd == "npm test"


def test_detect_test_command_cargo(temp_repo):
    """Test detecting cargo test command."""
    # Create Cargo.toml
    cargo_toml = Path(temp_repo) / "Cargo.toml"
    cargo_toml.write_text('[package]\nname = "test"')
    
    cmd = _detect_test_command(temp_repo)
    
    assert cmd == "cargo test"


def test_detect_test_command_go(temp_repo):
    """Test detecting go test command."""
    # Create go.mod
    go_mod = Path(temp_repo) / "go.mod"
    go_mod.write_text('module test')
    
    cmd = _detect_test_command(temp_repo)
    
    assert cmd == "go test ./..."


def test_detect_test_command_makefile(temp_repo):
    """Test detecting make test command."""
    # Create Makefile with test target
    makefile = Path(temp_repo) / "Makefile"
    makefile.write_text('test:\n\tpytest\n')
    
    cmd = _detect_test_command(temp_repo)
    
    assert cmd == "make test"


def test_detect_test_command_none(temp_repo):
    """Test when no test command is detected."""
    cmd = _detect_test_command(temp_repo)
    
    assert cmd is None


def test_detect_test_command_pytest_not_available(temp_repo):
    """Test pytest detection when pytest not available."""
    # Create pytest.ini but mock pytest not available
    pytest_ini = Path(temp_repo) / "pytest.ini"
    pytest_ini.write_text("[pytest]\n")

    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = Exception("pytest not found")

        cmd = _detect_test_command(temp_repo)

        # Should return None since pytest not available
        assert cmd is None


def test_extract_coverage_pytest_format():
    """Test extracting coverage from pytest-cov format."""
    output = "TOTAL 100 10 90%"

    coverage = _extract_coverage(output)

    assert coverage == 90.0


def test_extract_coverage_decimal_format():
    """Test extracting coverage with decimal."""
    output = "TOTAL 100 10 85.5%"

    coverage = _extract_coverage(output)

    assert coverage == 85.5


def test_extract_coverage_not_found():
    """Test when coverage not in output."""
    output = "Tests passed"

    coverage = _extract_coverage(output)

    assert coverage is None


def test_extract_coverage_complex_output():
    """Test extracting coverage from complex output."""
    output = """
    test_file.py::test_1 PASSED
    test_file.py::test_2 PASSED

    ---------- coverage: platform win32 ----------
    Name                Stmts   Miss  Cover
    ---------------------------------------
    app/module.py          50     10    80%
    TOTAL                 100     20    80%
    """

    coverage = _extract_coverage(output)

    assert coverage == 80.0


def test_validate_coverage_meets_threshold():
    """Test coverage validation when threshold is met."""
    assert validate_coverage(85.0, min_coverage=80.0) is True


def test_validate_coverage_below_threshold():
    """Test coverage validation when below threshold."""
    assert validate_coverage(75.0, min_coverage=80.0) is False


def test_validate_coverage_exact_threshold():
    """Test coverage validation at exact threshold."""
    assert validate_coverage(80.0, min_coverage=80.0) is True


def test_validate_coverage_none():
    """Test coverage validation when coverage is None."""
    # Enterprise v2.0: None coverage fails when enforcement is enabled
    assert validate_coverage(None, min_coverage=80.0) is False
    # But passes when enforcement is disabled
    assert validate_coverage(None, min_coverage=80.0, enforce_coverage=False) is True


def test_validate_coverage_custom_threshold():
    """Test coverage validation with custom threshold."""
    assert validate_coverage(95.0, min_coverage=90.0) is True
    assert validate_coverage(85.0, min_coverage=90.0) is False

