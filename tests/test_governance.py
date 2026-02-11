"""
Tests for governance module.
"""

import pytest
from app.modules.governance import (
    GovernanceValidator,
    GovernanceResult,
    GovernanceViolation,
    GovernanceProfile,
    ViolationSeverity
)


def test_governance_has_severe_property():
    """Test GovernanceResult has_severe property."""
    # No violations
    result = GovernanceResult(passed=True, violations=[], warnings=[])
    assert result.has_severe is False

    # INFO violation only
    result = GovernanceResult(
        passed=True,
        violations=[GovernanceViolation(
            rule_id="TEST-001",
            message="Info message",
            severity=ViolationSeverity.INFO
        )],
        warnings=[]
    )
    assert result.has_severe is False

    # SEVERE violation
    result = GovernanceResult(
        passed=False,
        violations=[GovernanceViolation(
            rule_id="TEST-002",
            message="Severe issue",
            severity=ViolationSeverity.SEVERE
        )],
        warnings=[]
    )
    assert result.has_severe is True


def test_governance_comm_010_is_this_ready():
    """Test COMM-010: 'is this ready?' reminder."""
    diff = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,2 @@
 line1
+line2
"""
    
    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="is this ready for production?",
        files_in_diff=["test.py"]
    )
    
    # Should have INFO violation for COMM-010
    assert any(v.rule_id == "COMM-010" for v in result.violations)
    assert any(v.severity == ViolationSeverity.INFO for v in result.violations)


def test_governance_exec_004_force_push():
    """Test EXEC-004: Never force push."""
    diff = """--- a/deploy.sh
+++ b/deploy.sh
@@ -1,1 +1,2 @@
 #!/bin/bash
+git push --force origin main
"""
    
    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Update deployment script",
        files_in_diff=["deploy.sh"]
    )
    
    # Should have SEVERE violation for EXEC-004
    assert any(v.rule_id == "EXEC-004" for v in result.violations)
    assert any(v.severity == ViolationSeverity.SEVERE for v in result.violations)


def test_governance_db_001_postgresql_only():
    """Test DB-001: PostgreSQL only (requires enforce_database_rules)."""
    diff = """--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 DATABASE_URL = "postgresql://localhost/db"
+CACHE_URL = "mysql://localhost/cache"
"""
    profile = GovernanceProfile(enforce_database_rules=True)

    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Add MySQL cache",
        files_in_diff=["config.py"],
        profile=profile
    )

    # Should have SEVERE violation for DB-001
    assert any(v.rule_id == "DB-001" for v in result.violations)
    assert any(v.severity == ViolationSeverity.SEVERE for v in result.violations)


def test_governance_db_001_not_checked_without_profile():
    """Test DB-001 is NOT checked when enforce_database_rules is False (default)."""
    diff = """--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 DATABASE_URL = "postgresql://localhost/db"
+CACHE_URL = "mysql://localhost/cache"
"""

    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Add MySQL cache",
        files_in_diff=["config.py"]
    )

    # Should NOT have DB-001 violation with default profile
    assert not any(v.rule_id == "DB-001" for v in result.violations)


def test_governance_db_002_parameterized_queries():
    """Test DB-002: Parameterized queries only (requires enforce_database_rules)."""
    # Use exact pattern that the rule checks for: "SELECT " +
    diff = """--- a/query.py
+++ b/query.py
@@ -1,1 +1,3 @@
 def get_user(user_id):
+    query = "SELECT " + "* FROM users WHERE id = " + str(user_id)
+    return db.execute(query)
"""
    profile = GovernanceProfile(enforce_database_rules=True)

    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Add user query",
        files_in_diff=["query.py"],
        profile=profile
    )

    # Should have SEVERE violation for DB-002
    assert any(v.rule_id == "DB-002" for v in result.violations)
    assert any(v.severity == ViolationSeverity.SEVERE for v in result.violations)


def test_governance_no_violations():
    """Test diff with no governance violations."""
    diff = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,2 @@
 def hello():
+    return "world"
"""
    
    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Add hello function",
        files_in_diff=["test.py"]
    )
    
    # Should have no violations
    assert len(result.violations) == 0
    assert result.has_severe is False


def test_governance_multiple_violations():
    """Test diff with multiple governance violations (DB rules enabled)."""
    diff = """--- a/deploy.sh
+++ b/deploy.sh
@@ -1,1 +1,3 @@
 #!/bin/bash
+git push --force origin main
+mysql -u root -p < schema.sql
"""
    profile = GovernanceProfile(enforce_database_rules=True)

    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Update deployment",
        files_in_diff=["deploy.sh"],
        profile=profile
    )

    # Should have multiple violations
    assert len(result.violations) >= 2
    assert any(v.rule_id == "EXEC-004" for v in result.violations)
    assert any(v.rule_id == "DB-001" for v in result.violations)


def test_governance_profile_disables_execution_rules():
    """Test that execution rules can be disabled via profile."""
    diff = """--- a/deploy.sh
+++ b/deploy.sh
@@ -1,1 +1,2 @@
 #!/bin/bash
+git push --force origin main
"""
    profile = GovernanceProfile(enforce_execution_rules=False, enforce_git_discipline=False)

    result = GovernanceValidator.validate_diff(
        diff_content=diff,
        description="Update deployment",
        files_in_diff=["deploy.sh"],
        profile=profile
    )

    # EXEC-004 should NOT fire when execution rules are disabled
    assert not any(v.rule_id == "EXEC-004" for v in result.violations)


def test_governance_default_profile_no_db_rules():
    """Test that default profile does NOT enforce database rules."""
    profile = GovernanceProfile()
    assert profile.enforce_database_rules is False
    assert profile.enforce_execution_rules is True
    assert profile.enforce_git_discipline is True

