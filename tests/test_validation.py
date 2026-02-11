"""
AGENT NEO - Validation Tests
"""

import pytest
from app.core.validation import (
    parse_diff_metadata,
    validate_diff,
    _calculate_deletion_percent
)


def test_parse_valid_diff(sample_diff):
    """Test parsing valid unified diff."""
    metadata = parse_diff_metadata(sample_diff)
    assert metadata.is_valid_unified_diff == True
    assert metadata.files_changed == 1
    assert metadata.lines_added == 2
    assert metadata.lines_removed == 1
    assert "test.py" in metadata.file_paths


def test_parse_invalid_diff(invalid_diff):
    """Test parsing invalid diff."""
    metadata = parse_diff_metadata(invalid_diff)
    assert metadata.is_valid_unified_diff == False


def test_parse_multi_file_diff(multi_file_diff):
    """Test parsing multi-file diff."""
    metadata = parse_diff_metadata(multi_file_diff)
    assert metadata.files_changed == 2
    assert "file1.py" in metadata.file_paths
    assert "file2.py" in metadata.file_paths


def test_validate_diff_rapid_mode_valid(sample_diff):
    """Test diff validation in RAPID mode with valid diff."""
    result = validate_diff(sample_diff, "RAPID")
    assert result.valid == True
    assert len(result.errors) == 0


def test_validate_diff_invalid_format(invalid_diff):
    """Test diff validation with invalid format."""
    result = validate_diff(invalid_diff, "RAPID")
    assert result.valid == False
    assert any("not a valid unified diff" in err.lower() for err in result.errors)


def test_validate_diff_too_many_lines_rapid(large_diff):
    """Test diff validation with too many lines in RAPID mode."""
    result = validate_diff(large_diff, "RAPID")
    assert result.valid == False
    assert any("too many lines" in err.lower() for err in result.errors)


def test_validate_diff_forbidden_pattern(forbidden_diff):
    """Test diff validation with forbidden patterns."""
    result = validate_diff(forbidden_diff, "RAPID")
    assert result.valid == False
    assert len(result.forbidden_patterns) > 0


def test_validate_diff_critical_mode_relaxed_limits(large_diff):
    """Test that CRITICAL mode has more relaxed limits."""
    # This diff would fail in RAPID but might pass in CRITICAL
    result_rapid = validate_diff(large_diff, "RAPID")
    result_critical = validate_diff(large_diff, "CRITICAL")
    
    # Both should fail for being too large, but CRITICAL has higher threshold
    assert result_rapid.valid == False
    # Large diff is 2000 lines, which exceeds RAPID (2000) but not CRITICAL (5000)


def test_validate_diff_dockerfile_rapid():
    """Test that Dockerfile changes are blocked in RAPID mode."""
    dockerfile_diff = """--- a/Dockerfile
+++ b/Dockerfile
@@ -1,2 +1,3 @@
 FROM python:3.11
+RUN apt-get update
 """
    result = validate_diff(dockerfile_diff, "RAPID")
    assert result.valid == False
    assert any("Dockerfile" in err for err in result.errors)


def test_calculate_deletion_percent():
    """Test deletion percentage calculation."""
    diff = """--- a/test.py
+++ b/test.py
@@ -1,10 +1,2 @@
-line1
-line2
-line3
-line4
-line5
-line6
-line7
-line8
+new1
+new2
"""
    percent = _calculate_deletion_percent(diff, "test.py")
    # 8 deletions, 2 additions = 80% deletion
    assert percent == 80.0


def test_validate_diff_high_deletion_percent():
    """Test that high deletion percentage is caught."""
    high_deletion_diff = """--- a/test.py
+++ b/test.py
@@ -1,10 +1,1 @@
-line1
-line2
-line3
-line4
-line5
-line6
-line7
-line8
-line9
+new1
"""
    result = validate_diff(high_deletion_diff, "RAPID")
    # Should fail because >40% deletion
    assert result.valid == False
    assert any("deletion" in err.lower() for err in result.errors)

