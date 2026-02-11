"""
AGENT NEO - Policy Tests
"""

import pytest
from app.core.policy import should_auto_push, get_push_policy_message, validate_push_safety


def test_rapid_mode_auto_push():
    """Test RAPID mode allows auto-push."""
    assert should_auto_push("RAPID", force=False) == True
    assert should_auto_push("RAPID", force=True) == True


def test_critical_mode_no_force():
    """Test CRITICAL mode blocks push without force."""
    assert should_auto_push("CRITICAL", force=False) == False


def test_critical_mode_with_force():
    """Test CRITICAL mode allows push with force."""
    assert should_auto_push("CRITICAL", force=True) == True


def test_push_policy_messages():
    """Test policy message generation."""
    msg1 = get_push_policy_message("RAPID", force=False)
    assert "RAPID" in msg1
    
    msg2 = get_push_policy_message("CRITICAL", force=False)
    assert "BLOCKED" in msg2
    
    msg3 = get_push_policy_message("CRITICAL", force=True)
    assert "enabled" in msg3.lower()


def test_validate_push_safety_rapid_within_limits():
    """Test push safety validation for RAPID mode within limits."""
    safe, reason = validate_push_safety("RAPID", files_changed=10, lines_changed=1000)
    assert safe == True


def test_validate_push_safety_rapid_too_many_lines():
    """Test push safety validation for RAPID mode with too many lines."""
    safe, reason = validate_push_safety("RAPID", files_changed=10, lines_changed=3000)
    assert safe == False
    assert "2000" in reason


def test_validate_push_safety_rapid_too_many_files():
    """Test push safety validation for RAPID mode with too many files."""
    safe, reason = validate_push_safety("RAPID", files_changed=25, lines_changed=100)
    assert safe == False
    assert "20" in reason


def test_validate_push_safety_critical_within_limits():
    """Test push safety validation for CRITICAL mode within limits."""
    safe, reason = validate_push_safety("CRITICAL", files_changed=30, lines_changed=3000)
    assert safe == True


def test_validate_push_safety_critical_too_many_lines():
    """Test push safety validation for CRITICAL mode with too many lines."""
    safe, reason = validate_push_safety("CRITICAL", files_changed=10, lines_changed=6000)
    assert safe == False
    assert "5000" in reason


def test_validate_push_safety_critical_too_many_files():
    """Test push safety validation for CRITICAL mode with too many files."""
    safe, reason = validate_push_safety("CRITICAL", files_changed=60, lines_changed=100)
    assert safe == False
    assert "50" in reason


def test_should_auto_push_unknown_mode():
    """Test should_auto_push with unknown mode."""
    # Unknown mode should return False
    result = should_auto_push("UNKNOWN", force=False)
    assert result == False


def test_get_push_policy_message_unknown_mode():
    """Test get_push_policy_message with unknown mode."""
    msg = get_push_policy_message("UNKNOWN", force=False)
    assert "Unknown" in msg

