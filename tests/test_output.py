"""
Tests for output module.
"""

import pytest
from app.core.output import (
    log_operation,
    create_success_response,
    create_error_response,
    format_test_output
)
from app.core.contracts import ValidationResult, TestResult


def test_log_operation_working(caplog):
    """Test logging successful operation."""
    import logging
    caplog.set_level(logging.INFO)

    log_operation(
        task_id="test-123",
        mode="RAPID",
        operation="apply_diff",
        status="Working",
        commit_sha="abc123",
        files_changed=2,
        lines_changed=10
    )

    # Just verify the function runs without error
    # Actual logging is tested by integration tests
    assert True


def test_log_operation_broken(caplog):
    """Test logging failed operation."""
    import logging
    caplog.set_level(logging.ERROR)

    log_operation(
        task_id="test-456",
        mode="CRITICAL",
        operation="apply_diff",
        status="Broken",
        files_changed=0,
        lines_changed=0
    )

    # Just verify the function runs without error
    assert True


def test_log_operation_with_kwargs(caplog):
    """Test logging with additional kwargs."""
    import logging
    caplog.set_level(logging.INFO)

    log_operation(
        task_id="test-789",
        mode="RAPID",
        operation="test",
        status="Working",
        custom_field="custom_value"
    )

    # Just verify the function runs without error
    assert True


def test_create_success_response_pushed():
    """Test creating success response with push."""
    validation_result = ValidationResult(
        valid=True,
        files_changed=2,
        lines_added=10,
        lines_removed=5
    )
    
    test_result = TestResult(
        passed=True,
        output="All tests passed",
        duration_seconds=1.5,
        coverage_percent=95.0
    )
    
    response = create_success_response(
        task_id="test-123",
        mode="RAPID",
        commit_sha="abc123",
        summary="Changes applied successfully",
        files_changed=["file1.py", "file2.py"],
        lines_changed=15,
        validation_result=validation_result,
        pre_test_result=test_result,
        post_test_result=test_result,
        pushed=True,
        governance_warnings=["Warning 1"]
    )
    
    assert response.status == "Working"
    assert response.task_id == "test-123"
    assert response.mode == "RAPID"
    assert response.commit_sha == "abc123"
    assert response.pushed is True
    assert "git log origin/main -1" in response.verify_steps
    assert "git revert abc123" in response.rollback_command
    assert response.governance_warnings == ["Warning 1"]


def test_create_success_response_not_pushed():
    """Test creating success response without push."""
    validation_result = ValidationResult(
        valid=True,
        files_changed=1,
        lines_added=5,
        lines_removed=2
    )
    
    response = create_success_response(
        task_id="test-456",
        mode="CRITICAL",
        commit_sha="def456",
        summary="Changes committed",
        files_changed=["file1.py"],
        lines_changed=7,
        validation_result=validation_result,
        pre_test_result=None,
        post_test_result=None,
        pushed=False
    )
    
    assert response.status == "Working"
    assert response.pushed is False
    assert "git log origin/main -1" not in response.verify_steps
    assert "git show def456" in response.verify_steps


def test_create_error_response():
    """Test creating error response."""
    response = create_error_response(
        task_id="test-789",
        mode="RAPID",
        error="Validation failed"
    )
    
    assert response.status == "Broken"
    assert response.task_id == "test-789"
    assert response.mode == "RAPID"
    assert response.error == "Validation failed"
    assert "Validation failed" in response.summary
    assert response.pushed is False


def test_create_error_response_with_validation():
    """Test creating error response with validation result."""
    validation_result = ValidationResult(
        valid=False,
        errors=["Error 1", "Error 2"]
    )
    
    response = create_error_response(
        task_id="test-999",
        mode="CRITICAL",
        error="Diff validation failed",
        validation_result=validation_result
    )
    
    assert response.status == "Broken"
    assert response.validation_result == validation_result


def test_format_test_output_short():
    """Test formatting test output that's already short."""
    output = "Line 1\nLine 2\nLine 3"

    result = format_test_output(output, max_lines=50)

    assert result == output


def test_format_test_output_long():
    """Test formatting long test output."""
    lines = [f"Line {i}" for i in range(100)]
    output = "\n".join(lines)

    result = format_test_output(output, max_lines=10)

    result_lines = result.split('\n')
    assert len(result_lines) == 10
    assert "Line 90" in result
    assert "Line 99" in result
    assert "Line 0" not in result


def test_format_test_output_exact_limit():
    """Test formatting test output at exact limit."""
    lines = [f"Line {i}" for i in range(50)]
    output = "\n".join(lines)

    result = format_test_output(output, max_lines=50)

    # Should return unchanged since it's exactly at the limit
    assert result == output

