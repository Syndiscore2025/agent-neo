"""
Tests for authentication module.
"""

import os
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import (
    constant_time_compare,
    get_expected_token,
    verify_bearer_token,
    generate_secure_token
)


def test_constant_time_compare_equal():
    """Test constant time comparison with equal strings."""
    assert constant_time_compare("test123", "test123") is True


def test_constant_time_compare_not_equal():
    """Test constant time comparison with different strings."""
    assert constant_time_compare("test123", "test456") is False


def test_constant_time_compare_different_lengths():
    """Test constant time comparison with different length strings."""
    assert constant_time_compare("short", "muchlongerstring") is False


def test_constant_time_compare_empty_strings():
    """Test constant time comparison with empty strings."""
    assert constant_time_compare("", "") is True


def test_get_expected_token_configured():
    """Test getting token when configured."""
    with patch.dict(os.environ, {"AGENT_NEO_TOKEN": "test-token-123"}):
        assert get_expected_token() == "test-token-123"


def test_get_expected_token_not_configured():
    """Test getting token when not configured."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_expected_token() is None


def test_verify_bearer_token_success():
    """Test successful token verification."""
    with patch.dict(os.environ, {"AGENT_NEO_TOKEN": "valid-token"}):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token"
        )
        result = verify_bearer_token(credentials)
        assert result == "valid-token"


def test_verify_bearer_token_invalid():
    """Test token verification with invalid token."""
    with patch.dict(os.environ, {"AGENT_NEO_TOKEN": "valid-token"}):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token"
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_bearer_token(credentials)
        
        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in exc_info.value.detail


def test_verify_bearer_token_not_configured():
    """Test token verification when token not configured."""
    with patch.dict(os.environ, {}, clear=True):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="any-token"
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_bearer_token(credentials)
        
        assert exc_info.value.status_code == 401
        assert "Authentication not configured" in exc_info.value.detail


def test_verify_bearer_token_empty_token():
    """Test token verification with empty token."""
    with patch.dict(os.environ, {"AGENT_NEO_TOKEN": "valid-token"}):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=""
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_bearer_token(credentials)
        
        assert exc_info.value.status_code == 401


def test_generate_secure_token_length():
    """Test that generated token has correct length."""
    token = generate_secure_token()
    assert len(token) == 64


def test_generate_secure_token_uniqueness():
    """Test that generated tokens are unique."""
    token1 = generate_secure_token()
    token2 = generate_secure_token()
    assert token1 != token2


def test_generate_secure_token_url_safe():
    """Test that generated token is URL-safe."""
    token = generate_secure_token()
    # URL-safe base64 uses only alphanumeric, -, and _
    assert all(c.isalnum() or c in ['-', '_'] for c in token)

