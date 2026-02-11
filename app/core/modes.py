"""
AGENT NEO - Mode Detection
Determines RAPID vs CRITICAL mode based on task description.
"""

from typing import List, Tuple, Literal
import re


# Critical keywords that trigger CRITICAL mode
CRITICAL_KEYWORDS = [
    "parsing",
    "extraction",
    "auth",
    "authentication",
    "authorization",
    "security",
    "schema",
    "migration",
    "database",
    "multi-tenant",
    "multitenant",
    "financial",
    "payment",
    "billing",
    "production infrastructure",
    "deployment",
    "infrastructure",
]


def detect_mode(description: str) -> Tuple[Literal["RAPID", "CRITICAL"], List[str]]:
    """
    Detect execution mode based on task description.
    
    Args:
        description: Task description text
        
    Returns:
        Tuple of (mode, list of critical keywords found)
    """
    description_lower = description.lower()
    found_keywords = []
    
    for keyword in CRITICAL_KEYWORDS:
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, description_lower):
            found_keywords.append(keyword)
    
    if found_keywords:
        return "CRITICAL", found_keywords
    
    return "RAPID", []


def is_critical_mode(description: str) -> bool:
    """
    Check if task should run in CRITICAL mode.
    
    Args:
        description: Task description text
        
    Returns:
        True if CRITICAL mode, False if RAPID mode
    """
    mode, _ = detect_mode(description)
    return mode == "CRITICAL"


def get_mode_description(mode: Literal["RAPID", "CRITICAL"]) -> str:
    """
    Get human-readable description of mode.
    
    Args:
        mode: RAPID or CRITICAL
        
    Returns:
        Description string
    """
    if mode == "RAPID":
        return "RAPID: Auto-commit and auto-push enabled"
    else:
        return "CRITICAL: Auto-commit enabled, auto-push requires force flag"

