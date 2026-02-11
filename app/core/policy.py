"""
AGENT NEO - Policy Enforcement
Decides if auto-push is allowed based on mode and flags.
"""

from typing import Literal


def should_auto_push(
    mode: Literal["RAPID", "CRITICAL"],
    force: bool = False
) -> bool:
    """
    Determine if auto-push to main is allowed.
    
    Args:
        mode: Execution mode (RAPID or CRITICAL)
        force: Force flag from request
        
    Returns:
        True if auto-push allowed, False otherwise
    """
    if mode == "RAPID":
        return True
    
    if mode == "CRITICAL":
        return force
    
    return False


def get_push_policy_message(
    mode: Literal["RAPID", "CRITICAL"],
    force: bool = False
) -> str:
    """
    Get human-readable push policy message.
    
    Args:
        mode: Execution mode
        force: Force flag
        
    Returns:
        Policy message string
    """
    if mode == "RAPID":
        return "Auto-push enabled (RAPID mode)"
    
    if mode == "CRITICAL" and force:
        return "Auto-push enabled (CRITICAL mode with force=true)"
    
    if mode == "CRITICAL" and not force:
        return "Auto-push BLOCKED (CRITICAL mode, force=false). Manual push required."
    
    return "Unknown policy"


def validate_push_safety(
    mode: Literal["RAPID", "CRITICAL"],
    files_changed: int,
    lines_changed: int
) -> tuple[bool, str]:
    """
    Validate if push is safe based on change size.
    
    Args:
        mode: Execution mode
        files_changed: Number of files changed
        lines_changed: Total lines changed
        
    Returns:
        Tuple of (is_safe, reason)
    """
    if mode == "RAPID":
        if lines_changed > 2000:
            return False, f"Too many lines changed for RAPID mode: {lines_changed} (max: 2000)"
        if files_changed > 20:
            return False, f"Too many files changed: {files_changed} (max: 20)"
    
    if mode == "CRITICAL":
        if lines_changed > 5000:
            return False, f"Too many lines changed: {lines_changed} (max: 5000)"
        if files_changed > 50:
            return False, f"Too many files changed: {files_changed} (max: 50)"
    
    return True, "Push safety validated"

