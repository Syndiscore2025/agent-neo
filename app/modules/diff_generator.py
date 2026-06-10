"""
AGENT NEO - Diff Generator
Generate minimal unified diffs.
"""

import difflib
from typing import List, Optional
from pathlib import Path


def generate_unified_diff(
    file_path: str,
    original_content: str,
    modified_content: str,
    context_lines: int = 3
) -> str:
    """
    Generate unified diff for a single file.
    
    Args:
        file_path: Path to file (for headers)
        original_content: Original file content
        modified_content: Modified file content
        context_lines: Number of context lines
        
    Returns:
        Unified diff string
    """
    original_lines = original_content.splitlines(keepends=True)
    modified_lines = modified_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f'a/{file_path}',
        tofile=f'b/{file_path}',
        lineterm='',
        n=context_lines
    )

    # Normalize: every diff line must end with a newline so headers
    # (---, +++, @@) are not glued to the following line.
    return ''.join(
        line if line.endswith('\n') else line + '\n'
        for line in diff
    )


def generate_file_deletion_diff(
    file_path: str,
    original_content: str,
    context_lines: int = 3
) -> str:
    """
    Generate a git-style unified diff for a whole-file deletion.

    Args:
        file_path: Path to the deleted file (for headers)
        original_content: Content of the file before deletion
        context_lines: Number of context lines

    Returns:
        Unified diff string with a /dev/null target
    """
    original_lines = original_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        [],
        fromfile=f'a/{file_path}',
        tofile='/dev/null',
        lineterm='',
        n=context_lines
    )

    return ''.join(
        line if line.endswith('\n') else line + '\n'
        for line in diff
    )


def generate_multi_file_diff(
    changes: List[tuple[str, str, str]],
    context_lines: int = 3
) -> str:
    """
    Generate unified diff for multiple files.
    
    Args:
        changes: List of (file_path, original_content, modified_content) tuples
        context_lines: Number of context lines
        
    Returns:
        Combined unified diff string
    """
    diffs = []

    for file_path, original, modified in changes:
        diff = generate_unified_diff(file_path, original, modified, context_lines)
        if diff:
            diffs.append(diff)

    # Each per-file diff already ends with a newline.
    return ''.join(diffs)


def apply_line_changes(
    original_content: str,
    line_number: int,
    new_lines: List[str],
    delete_count: int = 0
) -> str:
    """
    Apply line-level changes to content.
    
    Args:
        original_content: Original content
        line_number: Line number to start changes (1-based)
        new_lines: Lines to insert
        delete_count: Number of lines to delete
        
    Returns:
        Modified content
    """
    lines = original_content.splitlines(keepends=True)
    
    # Convert to 0-based index
    idx = line_number - 1
    
    # Delete lines
    if delete_count > 0:
        del lines[idx:idx + delete_count]
    
    # Insert new lines
    for i, new_line in enumerate(new_lines):
        if not new_line.endswith('\n'):
            new_line += '\n'
        lines.insert(idx + i, new_line)
    
    return ''.join(lines)


def validate_diff_format(diff: str) -> bool:
    """
    Validate that string is a proper unified diff.
    
    Args:
        diff: Diff string to validate
        
    Returns:
        True if valid unified diff
    """
    lines = diff.split('\n')
    
    has_file_header = False
    has_hunk_header = False
    
    for line in lines:
        if line.startswith('--- ') or line.startswith('+++ '):
            has_file_header = True
        elif line.startswith('@@'):
            has_hunk_header = True
    
    return has_file_header and has_hunk_header


def extract_changed_files(diff: str) -> List[str]:
    """
    Extract list of changed files from diff.
    
    Args:
        diff: Unified diff string
        
    Returns:
        List of file paths
    """
    files = []
    
    for line in diff.split('\n'):
        if line.startswith('+++ b/'):
            file_path = line[6:]  # Remove '+++ b/'
            files.append(file_path)
    
    return files


def count_diff_changes(diff: str) -> tuple[int, int]:
    """
    Count additions and deletions in diff.
    
    Args:
        diff: Unified diff string
        
    Returns:
        Tuple of (additions, deletions)
    """
    additions = 0
    deletions = 0
    
    for line in diff.split('\n'):
        if line.startswith('+') and not line.startswith('+++'):
            additions += 1
        elif line.startswith('-') and not line.startswith('---'):
            deletions += 1
    
    return additions, deletions

