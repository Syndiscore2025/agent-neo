"""
Tests for diff_generator module.
"""

import pytest
from app.modules.diff_generator import (
    generate_unified_diff,
    generate_multi_file_diff,
    apply_line_changes,
    validate_diff_format,
    extract_changed_files,
    count_diff_changes
)


def test_generate_unified_diff_simple():
    """Test generating a simple unified diff."""
    original = "line 1\nline 2\nline 3\n"
    modified = "line 1\nline 2 modified\nline 3\n"
    
    diff = generate_unified_diff("test.txt", original, modified)

    assert "--- a/test.txt" in diff
    assert "+++ b/test.txt" in diff
    assert "-line 2" in diff
    assert "+line 2 modified" in diff

    # Headers must be on their own lines (regression: glued headers)
    lines = diff.splitlines()
    assert lines[0] == "--- a/test.txt"
    assert lines[1] == "+++ b/test.txt"
    assert lines[2].startswith("@@")


def test_generate_unified_diff_addition():
    """Test diff with line addition."""
    original = "line 1\nline 2\n"
    modified = "line 1\nline 2\nline 3\n"
    
    diff = generate_unified_diff("test.txt", original, modified)
    
    assert "+line 3" in diff


def test_generate_unified_diff_deletion():
    """Test diff with line deletion."""
    original = "line 1\nline 2\nline 3\n"
    modified = "line 1\nline 3\n"
    
    diff = generate_unified_diff("test.txt", original, modified)
    
    assert "-line 2" in diff


def test_generate_unified_diff_no_changes():
    """Test diff with no changes."""
    original = "line 1\nline 2\n"
    modified = "line 1\nline 2\n"
    
    diff = generate_unified_diff("test.txt", original, modified)
    
    assert diff == ""


def test_generate_unified_diff_custom_context():
    """Test diff with custom context lines."""
    original = "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"
    modified = "1\n2\n3\n4\n5 modified\n6\n7\n8\n9\n10\n"
    
    diff = generate_unified_diff("test.txt", original, modified, context_lines=1)
    
    assert "@@" in diff
    assert "+5 modified" in diff


def test_generate_multi_file_diff():
    """Test generating diff for multiple files."""
    changes = [
        ("file1.txt", "old1\n", "new1\n"),
        ("file2.txt", "old2\n", "new2\n")
    ]
    
    diff = generate_multi_file_diff(changes)
    
    assert "--- a/file1.txt" in diff
    assert "--- a/file2.txt" in diff
    assert "+new1" in diff
    assert "+new2" in diff


def test_generate_multi_file_diff_empty():
    """Test multi-file diff with no changes."""
    changes = []
    
    diff = generate_multi_file_diff(changes)
    
    assert diff == ""


def test_generate_multi_file_diff_some_unchanged():
    """Test multi-file diff with some unchanged files."""
    changes = [
        ("file1.txt", "same\n", "same\n"),
        ("file2.txt", "old\n", "new\n")
    ]
    
    diff = generate_multi_file_diff(changes)
    
    assert "file1.txt" not in diff
    assert "file2.txt" in diff


def test_apply_line_changes_insert():
    """Test inserting lines."""
    original = "line 1\nline 2\nline 3\n"
    
    result = apply_line_changes(original, 2, ["inserted\n"], delete_count=0)
    
    assert result == "line 1\ninserted\nline 2\nline 3\n"


def test_apply_line_changes_delete():
    """Test deleting lines."""
    original = "line 1\nline 2\nline 3\n"
    
    result = apply_line_changes(original, 2, [], delete_count=1)
    
    assert result == "line 1\nline 3\n"


def test_apply_line_changes_replace():
    """Test replacing lines."""
    original = "line 1\nline 2\nline 3\n"
    
    result = apply_line_changes(original, 2, ["replaced\n"], delete_count=1)
    
    assert result == "line 1\nreplaced\nline 3\n"


def test_apply_line_changes_multiple_insert():
    """Test inserting multiple lines."""
    original = "line 1\nline 3\n"
    
    result = apply_line_changes(original, 2, ["line 2a\n", "line 2b\n"], delete_count=0)
    
    assert result == "line 1\nline 2a\nline 2b\nline 3\n"


def test_apply_line_changes_auto_newline():
    """Test auto-adding newlines."""
    original = "line 1\nline 2\n"
    
    result = apply_line_changes(original, 2, ["inserted"], delete_count=0)
    
    assert result == "line 1\ninserted\nline 2\n"


def test_validate_diff_format_valid():
    """Test validating a valid diff."""
    diff = """--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
 line 1
-line 2
+line 2 modified
 line 3"""
    
    assert validate_diff_format(diff) is True


def test_validate_diff_format_invalid_no_headers():
    """Test validating diff without headers."""
    diff = "+line 1\n-line 2"

    assert validate_diff_format(diff) is False


def test_validate_diff_format_invalid_no_hunks():
    """Test validating diff without hunk headers."""
    diff = "--- a/test.txt\n+++ b/test.txt\n+line 1"

    assert validate_diff_format(diff) is False


def test_extract_changed_files_single():
    """Test extracting single changed file."""
    diff = """--- a/test.txt
+++ b/test.txt
@@ -1 +1 @@
-old
+new"""

    files = extract_changed_files(diff)

    assert files == ["test.txt"]


def test_extract_changed_files_multiple():
    """Test extracting multiple changed files."""
    diff = """--- a/file1.txt
+++ b/file1.txt
@@ -1 +1 @@
-old
+new
--- a/file2.txt
+++ b/file2.txt
@@ -1 +1 @@
-old
+new"""

    files = extract_changed_files(diff)

    assert files == ["file1.txt", "file2.txt"]


def test_extract_changed_files_empty():
    """Test extracting files from empty diff."""
    diff = ""

    files = extract_changed_files(diff)

    assert files == []


def test_count_diff_changes_additions():
    """Test counting additions."""
    diff = """--- a/test.txt
+++ b/test.txt
@@ -1 +1,3 @@
 line 1
+line 2
+line 3"""

    additions, deletions = count_diff_changes(diff)

    assert additions == 2
    assert deletions == 0


def test_count_diff_changes_deletions():
    """Test counting deletions."""
    diff = """--- a/test.txt
+++ b/test.txt
@@ -1,3 +1 @@
 line 1
-line 2
-line 3"""

    additions, deletions = count_diff_changes(diff)

    assert additions == 0
    assert deletions == 2


def test_count_diff_changes_mixed():
    """Test counting mixed changes."""
    diff = """--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
 line 1
-line 2
+line 2 modified
 line 3
+line 4"""

    additions, deletions = count_diff_changes(diff)

    assert additions == 2
    assert deletions == 1


def test_count_diff_changes_empty():
    """Test counting changes in empty diff."""
    diff = ""

    additions, deletions = count_diff_changes(diff)

    assert additions == 0
    assert deletions == 0

