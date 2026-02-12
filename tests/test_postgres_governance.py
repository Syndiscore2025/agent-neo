"""
AGENT NEO - PostgreSQL Governance Tests
"""

import pytest
from app.modules.governance import (
    GovernanceValidator,
    GovernanceProfile,
    ViolationSeverity
)


def test_postgresql_enforcement_sqlite_import():
    """Test PostgreSQL enforcement detects SQLite import."""
    diff = """
+import sqlite3
+
+conn = sqlite3.connect('database.db')
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    assert result.passed is False
    assert any(v.rule_id == "PG-002" for v in result.violations)


def test_postgresql_enforcement_sqlite_file():
    """Test PostgreSQL enforcement detects SQLite file patterns."""
    diff = """
+DATABASE_URL = "sqlite:///app.db"
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    assert result.passed is False
    assert any(v.rule_id == "PG-001" for v in result.violations)


def test_postgresql_enforcement_memory_database():
    """Test PostgreSQL enforcement detects in-memory database."""
    diff = """
+DATABASE_URL = "sqlite:///:memory:"
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    assert result.passed is False
    assert any(v.rule_id == "PG-003" for v in result.violations)


def test_postgresql_enforcement_valid_postgres():
    """Test PostgreSQL enforcement allows PostgreSQL."""
    diff = """
+import psycopg2
+
+DATABASE_URL = "postgresql://user:pass@localhost/db"
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    # Should pass (may have warnings about pooling)
    assert result.passed is True


def test_postgresql_enforcement_warns_no_pooling():
    """Test PostgreSQL enforcement warns about missing pooling."""
    diff = """
+DATABASE_URL = "postgresql://user:pass@localhost/db"
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    # Should have warning about pooling
    warnings = [v for v in result.violations if v.severity == ViolationSeverity.WARNING]
    assert any(v.rule_id == "PG-004" for v in warnings)


def test_postgresql_enforcement_migration_without_downgrade():
    """Test PostgreSQL enforcement detects migration without downgrade."""
    diff = """
+++ b/alembic/versions/001_initial.py
+def upgrade():
+    op.create_table('users')
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    files = ["alembic/versions/001_initial.py"]
    result = GovernanceValidator.validate_diff(diff, "Add migration", files, profile)
    
    assert result.passed is False
    assert any(v.rule_id == "PG-005" for v in result.violations)


def test_postgresql_enforcement_migration_with_downgrade():
    """Test PostgreSQL enforcement allows migration with downgrade."""
    diff = """
+++ b/alembic/versions/001_initial.py
+def upgrade():
+    op.create_table('users')
+
+def downgrade():
+    op.drop_table('users')
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=True)
    files = ["alembic/versions/001_initial.py"]
    result = GovernanceValidator.validate_diff(diff, "Add migration", files, profile)
    
    # Should pass
    assert result.passed is True


def test_postgresql_enforcement_disabled():
    """Test PostgreSQL enforcement can be disabled."""
    diff = """
+import sqlite3
"""
    
    profile = GovernanceProfile(enforce_postgresql_only=False)
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    # Should pass when enforcement disabled
    assert result.passed is True


def test_default_profile_enforces_postgresql():
    """Test default profile enforces PostgreSQL."""
    diff = """
+import sqlite3
"""
    
    # Default profile should enforce PostgreSQL
    profile = GovernanceProfile()
    result = GovernanceValidator.validate_diff(diff, "Add database", [], profile)
    
    assert result.passed is False
    assert any("PG-" in v.rule_id for v in result.violations)

