"""
AGENT NEO - Test Runner
Run tests and capture results.
"""

import subprocess
import time
import os
from typing import Optional
from pathlib import Path
from app.core.contracts import TestResult


def run_tests(
    repo_path: str,
    test_command: Optional[str] = None,
    timeout: int = 300
) -> TestResult:
    """
    Run test suite and capture results.
    
    Args:
        repo_path: Path to repository
        test_command: Custom test command (default: auto-detect)
        timeout: Timeout in seconds
        
    Returns:
        TestResult object
    """
    if test_command is None:
        test_command = _detect_test_command(repo_path)
    
    if not test_command:
        # No tests configured - pass by default
        return TestResult(
            passed=True,
            output="No test command configured",
            duration_seconds=0.0
        )
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            test_command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True
        )
        
        duration = time.time() - start_time
        output = result.stdout + "\n" + result.stderr
        
        # Truncate output to last 50 lines
        output_lines = output.split('\n')
        if len(output_lines) > 50:
            output = '\n'.join(output_lines[-50:])
        
        passed = result.returncode == 0
        
        # Try to extract coverage if available
        coverage = _extract_coverage(output)
        
        return TestResult(
            passed=passed,
            output=output,
            duration_seconds=duration,
            coverage_percent=coverage
        )
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return TestResult(
            passed=False,
            output=f"Tests timed out after {timeout} seconds",
            duration_seconds=duration
        )
    except Exception as e:
        duration = time.time() - start_time
        return TestResult(
            passed=False,
            output=f"Test execution failed: {str(e)}",
            duration_seconds=duration
        )


def _detect_test_command(repo_path: str) -> Optional[str]:
    """
    Auto-detect test command based on repository structure.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Test command string or None
    """
    repo = Path(repo_path)
    
    # Check for pytest
    if (repo / "pytest.ini").exists() or (repo / "pyproject.toml").exists():
        # Check if pytest is available
        try:
            subprocess.run(
                ['pytest', '--version'],
                capture_output=True,
                timeout=5
            )
            return "pytest --tb=short -v"
        except:
            pass
    
    # Check for package.json (Node.js)
    if (repo / "package.json").exists():
        return "npm test"
    
    # Check for Cargo.toml (Rust)
    if (repo / "Cargo.toml").exists():
        return "cargo test"
    
    # Check for go.mod (Go)
    if (repo / "go.mod").exists():
        return "go test ./..."
    
    # Check for Makefile with test target
    if (repo / "Makefile").exists():
        makefile_content = (repo / "Makefile").read_text()
        if "test:" in makefile_content:
            return "make test"
    
    # No test command detected
    return None


def _extract_coverage(output: str) -> Optional[float]:
    """
    Extract coverage percentage from test output.
    
    Args:
        output: Test output string
        
    Returns:
        Coverage percentage or None
    """
    import re
    
    # Try to find pytest-cov format: "TOTAL ... 85%"
    match = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', output)
    if match:
        return float(match.group(1))
    
    # Try to find coverage.py format: "TOTAL ... 85.5%"
    match = re.search(r'TOTAL\s+.*?(\d+(?:\.\d+)?)%', output)
    if match:
        return float(match.group(1))
    
    return None


def validate_coverage(coverage_percent: Optional[float], min_coverage: float = 80.0) -> bool:
    """
    Validate coverage meets minimum threshold.
    
    Args:
        coverage_percent: Coverage percentage
        min_coverage: Minimum required coverage
        
    Returns:
        True if coverage meets threshold
    """
    if coverage_percent is None:
        # If coverage not available, assume it passes
        return True
    
    return coverage_percent >= min_coverage

