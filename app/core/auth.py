"""
AGENT NEO - Authentication Module
Bearer token authentication for Augment integration.
"""

import os
import secrets
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED


security = HTTPBearer()


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks.
    
    Args:
        a: First string
        b: Second string
        
    Returns:
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def get_expected_token() -> Optional[str]:
    """
    Get expected Bearer token from environment.
    
    Returns:
        Token string or None if not configured
    """
    return os.getenv("AGENT_NEO_TOKEN")


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """
    Verify Bearer token from Authorization header.
    
    Args:
        credentials: HTTP authorization credentials from request
        
    Returns:
        Token string if valid
        
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    expected_token = get_expected_token()
    
    # If no token configured, reject all requests
    if not expected_token:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Authentication not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from credentials
    provided_token = credentials.credentials
    
    # Constant-time comparison to prevent timing attacks
    if not constant_time_compare(provided_token, expected_token):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return provided_token


def generate_secure_token() -> str:
    """
    Generate a cryptographically secure random token.
    
    Returns:
        Secure token string (64 characters)
    """
    return secrets.token_urlsafe(48)  # 48 bytes = 64 base64 characters

