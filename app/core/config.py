"""
AGENT NEO - Configuration
Environment-driven limits and settings with sensible defaults.
"""

import os


def _get_int_env(name: str, default: int) -> int:
    """Get integer from environment variable with default."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Diff limits - configurable via environment variables
RAPID_MAX_FILES = _get_int_env("RAPID_MAX_FILES", 20)
RAPID_MAX_LINES = _get_int_env("RAPID_MAX_LINES", 2000)
CRITICAL_MAX_FILES = _get_int_env("CRITICAL_MAX_FILES", 50)
CRITICAL_MAX_LINES = _get_int_env("CRITICAL_MAX_LINES", 5000)
MAX_DIFF_SIZE_BYTES = _get_int_env("MAX_DIFF_SIZE_BYTES", 51200)  # 50KB

# File deletion threshold
MAX_FILE_DELETION_PERCENT = _get_int_env("MAX_FILE_DELETION_PERCENT", 40)

