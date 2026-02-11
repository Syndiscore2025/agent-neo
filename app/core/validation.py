"""
AGENT NEO - Diff Validation
Validates diffs against kernel rules.
"""

import re
from typing import List, Literal
from app.core.contracts import ValidationResult, DiffMetadata


# Validation limits
MAX_FILES_CHANGED = 20
MAX_LINES_CHANGED_RAPID = 2000
MAX_LINES_CHANGED_CRITICAL = 5000
MAX_FILE_DELETION_PERCENT = 40

# Forbidden patterns in all modes
# Using .* to catch patterns even when split across strings like ['git', 'reset']
FORBIDDEN_PATTERNS = [
    r'git.{0,10}reset',
    r'git.{0,10}rebase',
    r'DROP\s+TABLE',
    r'--force\b',
    r'\bFORCE\b',
]

# Forbidden patterns in RAPID mode only
FORBIDDEN_IN_RAPID = [
    r'ALTER\s+TABLE',
    r'CREATE\s+TABLE',
    r'DROP\s+INDEX',
    r'CREATE\s+INDEX',
]

# Files that cannot be modified in RAPID mode
RAPID_FORBIDDEN_FILES = [
    'Dockerfile',
    'docker-compose.yml',
    '.github/workflows/',
    'kubernetes/',
    'terraform/',
]


def parse_diff_metadata(diff: str) -> DiffMetadata:
    """
    Parse metadata from unified diff.
    
    Args:
        diff: Unified diff string
        
    Returns:
        DiffMetadata object
    """
    lines = diff.split('\n')
    files_changed = set()
    lines_added = 0
    lines_removed = 0
    is_valid = False
    
    # Check for unified diff format
    has_diff_header = False
    has_hunk_header = False
    
    for line in lines:
        # File headers
        if line.startswith('--- ') or line.startswith('+++ '):
            has_diff_header = True
            # Extract filename
            if line.startswith('+++ '):
                match = re.match(r'\+\+\+ b/(.+)', line)
                if match:
                    files_changed.add(match.group(1))
        
        # Hunk headers
        elif line.startswith('@@'):
            has_hunk_header = True
        
        # Added lines
        elif line.startswith('+') and not line.startswith('+++'):
            lines_added += 1
        
        # Removed lines
        elif line.startswith('-') and not line.startswith('---'):
            lines_removed += 1
    
    is_valid = has_diff_header and has_hunk_header
    
    return DiffMetadata(
        files_changed=len(files_changed),
        lines_added=lines_added,
        lines_removed=lines_removed,
        total_lines_changed=lines_added + lines_removed,
        file_paths=list(files_changed),
        is_valid_unified_diff=is_valid
    )


def validate_diff(
    diff: str,
    mode: Literal["RAPID", "CRITICAL"]
) -> ValidationResult:
    """
    Validate diff against kernel rules.
    
    Args:
        diff: Unified diff string
        mode: Execution mode
        
    Returns:
        ValidationResult object
    """
    errors = []
    warnings = []
    forbidden_found = []
    
    # Parse diff metadata
    metadata = parse_diff_metadata(diff)
    
    # Check if valid unified diff
    if not metadata.is_valid_unified_diff:
        errors.append("Not a valid unified diff format")
        return ValidationResult(
            valid=False,
            errors=errors,
            warnings=warnings,
            forbidden_patterns=forbidden_found
        )
    
    # Check file count
    if metadata.files_changed > MAX_FILES_CHANGED:
        errors.append(
            f"Too many files changed: {metadata.files_changed} (max: {MAX_FILES_CHANGED})"
        )
    
    # Check line count based on mode
    max_lines = MAX_LINES_CHANGED_RAPID if mode == "RAPID" else MAX_LINES_CHANGED_CRITICAL
    if metadata.total_lines_changed > max_lines:
        errors.append(
            f"Too many lines changed: {metadata.total_lines_changed} (max: {max_lines} for {mode} mode)"
        )
    
    # Check for forbidden patterns (all modes)
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, diff, re.IGNORECASE):
            forbidden_found.append(pattern)
            errors.append(f"Forbidden pattern found: {pattern}")
    
    # Check for RAPID-specific forbidden patterns
    if mode == "RAPID":
        for pattern in FORBIDDEN_IN_RAPID:
            if re.search(pattern, diff, re.IGNORECASE):
                forbidden_found.append(pattern)
                errors.append(f"Forbidden pattern in RAPID mode: {pattern}")
        
        # Check for forbidden files in RAPID mode
        for file_path in metadata.file_paths:
            for forbidden in RAPID_FORBIDDEN_FILES:
                if forbidden in file_path:
                    errors.append(f"Cannot modify {file_path} in RAPID mode")
    
    # Check file deletion percentage
    for file_path in metadata.file_paths:
        deletion_percent = _calculate_deletion_percent(diff, file_path)
        if deletion_percent > MAX_FILE_DELETION_PERCENT:
            errors.append(
                f"File {file_path} has {deletion_percent}% deletion (max: {MAX_FILE_DELETION_PERCENT}%)"
            )
    
    valid = len(errors) == 0
    
    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        files_changed=metadata.files_changed,
        lines_added=metadata.lines_added,
        lines_removed=metadata.lines_removed,
        forbidden_patterns=forbidden_found
    )


def _calculate_deletion_percent(diff: str, file_path: str) -> float:
    """Calculate percentage of lines deleted in a file."""
    lines = diff.split('\n')
    in_file = False
    added = 0
    removed = 0
    
    for line in lines:
        if f'+++ b/{file_path}' in line:
            in_file = True
            continue
        if in_file and (line.startswith('--- ') or line.startswith('+++ ')):
            break
        if in_file:
            if line.startswith('+') and not line.startswith('+++'):
                added += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed += 1
    
    total = added + removed
    if total == 0:
        return 0.0
    
    return (removed / total) * 100

