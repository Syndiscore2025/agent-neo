"""
Tests for contracts module (Pydantic models).
"""

import pytest
from pydantic import ValidationError
from app.core.contracts import (
    TaskRequest,
    DiffMetadata
)


def test_task_request_valid():
    """Test creating valid TaskRequest."""
    request = TaskRequest(
        task_id="test-123",
        description="Add new feature",
        diff=None,
        force=False
    )
    
    assert request.task_id == "test-123"
    assert request.description == "Add new feature"
    assert request.diff is None
    assert request.force is False


def test_task_request_empty_task_id():
    """Test TaskRequest with empty task_id."""
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(
            task_id="",
            description="Add new feature",
            diff=None
        )
    
    assert "task_id cannot be empty" in str(exc_info.value)


def test_task_request_whitespace_task_id():
    """Test TaskRequest with whitespace-only task_id."""
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(
            task_id="   ",
            description="Add new feature",
            diff=None
        )
    
    assert "task_id cannot be empty" in str(exc_info.value)


def test_task_request_empty_description():
    """Test TaskRequest with empty description."""
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(
            task_id="test-123",
            description="",
            diff=None
        )
    
    assert "description cannot be empty" in str(exc_info.value)


def test_task_request_whitespace_description():
    """Test TaskRequest with whitespace-only description."""
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(
            task_id="test-123",
            description="   ",
            diff=None
        )
    
    assert "description cannot be empty" in str(exc_info.value)


def test_task_request_strips_whitespace():
    """Test that TaskRequest strips whitespace from fields."""
    request = TaskRequest(
        task_id="  test-123  ",
        description="  Add new feature  ",
        diff=None
    )
    
    assert request.task_id == "test-123"
    assert request.description == "Add new feature"


def test_diff_metadata_total_changes():
    """Test DiffMetadata total_changes property."""
    metadata = DiffMetadata(
        files_changed=2,
        lines_added=10,
        lines_removed=5,
        total_lines_changed=15,
        file_paths=["file1.py", "file2.py"],
        is_valid_unified_diff=True
    )
    
    assert metadata.total_changes == 15
    assert metadata.lines_added + metadata.lines_removed == 15


def test_diff_metadata_total_changes_zero():
    """Test DiffMetadata total_changes with no changes."""
    metadata = DiffMetadata(
        files_changed=0,
        lines_added=0,
        lines_removed=0,
        total_lines_changed=0,
        file_paths=[],
        is_valid_unified_diff=True
    )
    
    assert metadata.total_changes == 0


def test_diff_metadata_total_changes_additions_only():
    """Test DiffMetadata total_changes with only additions."""
    metadata = DiffMetadata(
        files_changed=1,
        lines_added=20,
        lines_removed=0,
        total_lines_changed=20,
        file_paths=["new_file.py"],
        is_valid_unified_diff=True
    )
    
    assert metadata.total_changes == 20


def test_diff_metadata_total_changes_deletions_only():
    """Test DiffMetadata total_changes with only deletions."""
    metadata = DiffMetadata(
        files_changed=1,
        lines_added=0,
        lines_removed=15,
        total_lines_changed=15,
        file_paths=["old_file.py"],
        is_valid_unified_diff=True
    )
    
    assert metadata.total_changes == 15

