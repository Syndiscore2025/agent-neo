"""
AGENT NEO - Mode Detection Tests
"""

import pytest
from app.core.modes import detect_mode, is_critical_mode, get_mode_description


def test_rapid_mode_simple_task():
    """Test RAPID mode for simple tasks."""
    mode, keywords = detect_mode("Add a new feature to the dashboard")
    assert mode == "RAPID"
    assert len(keywords) == 0


def test_critical_mode_auth():
    """Test CRITICAL mode for auth-related tasks."""
    mode, keywords = detect_mode("Update authentication logic")
    assert mode == "CRITICAL"
    assert "authentication" in keywords


def test_critical_mode_security():
    """Test CRITICAL mode for security tasks."""
    mode, keywords = detect_mode("Fix security vulnerability")
    assert mode == "CRITICAL"
    assert "security" in keywords


def test_critical_mode_schema():
    """Test CRITICAL mode for schema changes."""
    mode, keywords = detect_mode("Add database schema migration")
    assert mode == "CRITICAL"
    assert "schema" in keywords
    assert "migration" in keywords


def test_critical_mode_financial():
    """Test CRITICAL mode for financial tasks."""
    mode, keywords = detect_mode("Update payment processing logic")
    assert mode == "CRITICAL"
    assert "payment" in keywords


def test_critical_mode_multi_tenant():
    """Test CRITICAL mode for multi-tenant tasks."""
    mode, keywords = detect_mode("Add multi-tenant support")
    assert mode == "CRITICAL"
    assert "multi-tenant" in keywords


def test_is_critical_mode():
    """Test is_critical_mode helper."""
    assert is_critical_mode("Update authentication") == True
    assert is_critical_mode("Add new button") == False


def test_get_mode_description():
    """Test mode description generation."""
    rapid_desc = get_mode_description("RAPID")
    assert "auto-push enabled" in rapid_desc.lower()
    
    critical_desc = get_mode_description("CRITICAL")
    assert "force flag" in critical_desc.lower()


def test_case_insensitive_detection():
    """Test that mode detection is case-insensitive."""
    mode1, _ = detect_mode("Update AUTHENTICATION logic")
    mode2, _ = detect_mode("Update authentication logic")
    assert mode1 == mode2 == "CRITICAL"


def test_word_boundary_detection():
    """Test that keywords require word boundaries."""
    # "parsing" should trigger CRITICAL
    mode1, keywords1 = detect_mode("Fix parsing error")
    assert mode1 == "CRITICAL"
    
    # "pars" should not trigger (partial match)
    mode2, keywords2 = detect_mode("Fix pars error")
    assert mode2 == "RAPID"

