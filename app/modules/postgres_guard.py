"""
AGENT NEO - PostgreSQL Guard
PostgreSQL-first database governance and validation.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PostgresValidationResult:
    """Result of PostgreSQL validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    recommendations: List[str]


# Unsafe SQL patterns
UNSAFE_SQL_PATTERNS = [
    r'DROP\s+TABLE',
    r'TRUNCATE\s+TABLE',
    r'DELETE\s+FROM\s+\w+\s*;',  # DELETE without WHERE
    r'UPDATE\s+\w+\s+SET\s+.*\s*;',  # UPDATE without WHERE
    r'--\s*DROP',
    r';.*DROP',
    r';\s*DELETE',
    r';\s*TRUNCATE',
]

# Required patterns for production
REQUIRED_PATTERNS = {
    'connection_string': r'postgresql://|postgres://',
    'parameterized_query': r'\$\d+|%\(.*?\)s|placeholder',
}

# Prohibited database types
PROHIBITED_DATABASES = [
    'sqlite',
    'sqlite3',
    'memory',
    ':memory:',
]


def validate_connection_string(conn_str: str) -> PostgresValidationResult:
    """
    Validate PostgreSQL connection string.
    
    Args:
        conn_str: Database connection string
        
    Returns:
        PostgresValidationResult
    """
    errors = []
    warnings = []
    recommendations = []
    
    # Check for PostgreSQL protocol
    if not re.search(r'postgresql://|postgres://', conn_str, re.IGNORECASE):
        errors.append("Connection string must use postgresql:// or postgres:// protocol")
    
    # Check for prohibited databases
    for prohibited in PROHIBITED_DATABASES:
        if prohibited.lower() in conn_str.lower():
            errors.append(f"Prohibited database type detected: {prohibited}")
    
    # Check for hardcoded credentials
    if re.search(r'://[^:]+:[^@]+@', conn_str):
        warnings.append("Hardcoded credentials detected in connection string")
        recommendations.append("Use environment variables for database credentials")
    
    # Check for connection pooling parameters
    if 'pool_size' not in conn_str.lower() and 'poolclass' not in conn_str.lower():
        recommendations.append("Consider adding connection pooling configuration")
    
    # Check for SSL/TLS
    if 'sslmode' not in conn_str.lower():
        warnings.append("SSL mode not specified in connection string")
        recommendations.append("Add sslmode parameter for production (e.g., sslmode=require)")
    
    valid = len(errors) == 0
    
    return PostgresValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        recommendations=recommendations
    )


def detect_unsafe_sql(sql_content: str) -> PostgresValidationResult:
    """
    Detect unsafe SQL patterns in code.
    
    Args:
        sql_content: SQL code or file content
        
    Returns:
        PostgresValidationResult
    """
    errors = []
    warnings = []
    recommendations = []
    
    # Check for unsafe patterns
    for pattern in UNSAFE_SQL_PATTERNS:
        matches = re.finditer(pattern, sql_content, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            errors.append(f"Unsafe SQL pattern detected: {match.group()}")
    
    # Check for SQL injection vulnerabilities
    if re.search(r'f["\'].*SELECT.*{.*}', sql_content):
        errors.append("Potential SQL injection: f-string used in SQL query")
        recommendations.append("Use parameterized queries instead of string formatting")
    
    if re.search(r'\.format\(.*\).*SELECT', sql_content):
        errors.append("Potential SQL injection: .format() used in SQL query")
        recommendations.append("Use parameterized queries instead of .format()")
    
    # Check for string concatenation in queries
    if re.search(r'["\'].*SELECT.*["\']\s*\+', sql_content):
        warnings.append("String concatenation detected in SQL query")
        recommendations.append("Use parameterized queries for safety")
    
    valid = len(errors) == 0
    
    return PostgresValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        recommendations=recommendations
    )


def validate_migration_structure(migration_content: str) -> PostgresValidationResult:
    """
    Validate migration file structure.
    
    Args:
        migration_content: Migration file content
        
    Returns:
        PostgresValidationResult
    """
    errors = []
    warnings = []
    recommendations = []
    
    # Check for upgrade function
    if 'def upgrade' not in migration_content:
        errors.append("Migration missing upgrade() function")
    
    # Check for downgrade function
    if 'def downgrade' not in migration_content:
        errors.append("Migration missing downgrade() function")
        recommendations.append("All migrations must include rollback capability")
    
    # Check for empty downgrade
    if 'def downgrade' in migration_content:
        downgrade_match = re.search(r'def downgrade\(\):.*?(?=def|\Z)', migration_content, re.DOTALL)
        if downgrade_match:
            downgrade_body = downgrade_match.group()
            if 'pass' in downgrade_body and len(downgrade_body.strip().split('\n')) <= 2:
                warnings.append("Downgrade function appears to be empty")
                recommendations.append("Implement proper rollback logic in downgrade()")
    
    valid = len(errors) == 0
    
    return PostgresValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        recommendations=recommendations
    )


def generate_postgres_setup_instructions() -> Dict[str, Any]:
    """
    Generate production-ready PostgreSQL setup instructions.
    
    Returns:
        Dictionary with setup instructions and templates
    """
    return {
        "docker_compose": """version: '3.8'
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
""",
        "env_template": """# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_secure_password
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=require
""",
        "alembic_setup": """# Install Alembic
pip install alembic psycopg2-binary

# Initialize Alembic
alembic init alembic

# Configure alembic.ini to use environment variable:
# sqlalchemy.url = postgresql://user:pass@localhost/dbname

# Create first migration
alembic revision -m "initial schema"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
""",
        "connection_pooling": """from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
)
"""
    }

