"""
AGENT NEO - Governance Module
Configurable behavioral rules gated by GovernanceProfile.
"""

from typing import List, Optional
from enum import Enum
from dataclasses import dataclass


class ViolationSeverity(Enum):
    """Severity levels for governance violations."""
    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"


@dataclass
class GovernanceViolation:
    """Single governance violation."""
    rule_id: str
    message: str
    severity: ViolationSeverity


@dataclass
class GovernanceResult:
    """Result of governance validation."""
    passed: bool
    violations: List[GovernanceViolation]
    warnings: List[str]

    @property
    def has_severe(self) -> bool:
        """Check if any severe violations exist."""
        return any(v.severity == ViolationSeverity.SEVERE for v in self.violations)


@dataclass
class GovernanceProfile:
    """
    Configurable profile that controls which governance rule groups are active.

    No default assumptions about multi-tenancy, database type,
    API stability, or schema behavior.
    """
    enforce_execution_rules: bool = True
    enforce_git_discipline: bool = True
    enforce_database_rules: bool = False
    enforce_api_stability: bool = False
    enforce_test_coverage: bool = False
    enforce_logging_rules: bool = False
    enforce_deployment_rules: bool = False
    enforce_additive_only: bool = False
    enforce_postgresql_only: bool = True  # Enterprise standard: PostgreSQL only


# Centralized forbidden patterns structure
# Used by both governance and validation modules
FORBIDDEN_PATTERNS = {
    "EXEC": [
        r'--force\b',
        r'\bFORCE\b',
        "git push -f",
        "git push --force",
    ],
    "GIT": [
        r'git.{0,10}reset',
        r'git.{0,10}rebase',
    ],
    "DB": [
        r'DROP\s+TABLE',
        r'ALTER\s+TABLE',
        r'CREATE\s+TABLE',
        r'DROP\s+INDEX',
        r'CREATE\s+INDEX',
    ],
    "POSTGRES": [
        r'sqlite',
        r'sqlite3',
        r':memory:',
        r'\.db\b',
        r'\.sqlite\b',
    ],
    "API": [],
    "DEPLOY": [],
    "LOG": [],
}

# Files that cannot be modified in RAPID mode
RAPID_FORBIDDEN_FILES = [
    'Dockerfile',
    'docker-compose.yml',
    '.github/workflows/',
    'kubernetes/',
    'terraform/',
]


class GovernanceValidator:
    """Validates diffs against profile-gated governance rules."""

    @staticmethod
    def validate_diff(
        diff_content: str,
        description: str,
        files_in_diff: List[str],
        profile: Optional[GovernanceProfile] = None
    ) -> GovernanceResult:
        """
        Validate diff against governance rules enabled by profile.

        Args:
            diff_content: The unified diff content
            description: Task description
            files_in_diff: List of file paths in diff
            profile: GovernanceProfile controlling which rules are active.
                     If None, uses default profile (execution + git only).

        Returns:
            GovernanceResult with violations and warnings
        """
        if profile is None:
            profile = GovernanceProfile()

        violations = []

        # COMMUNICATION RULES - always active (INFO level guidance only)
        violations.extend(GovernanceValidator._check_communication_rules(description))

        # EXECUTION / GIT DISCIPLINE RULES
        if profile.enforce_execution_rules or profile.enforce_git_discipline:
            violations.extend(GovernanceValidator._check_execution_rules(diff_content))

        # DATABASE RULES - only when profile enables them
        if profile.enforce_database_rules:
            violations.extend(GovernanceValidator._check_database_rules(diff_content))

        # POSTGRESQL ENFORCEMENT - enterprise standard
        if profile.enforce_postgresql_only:
            violations.extend(GovernanceValidator._check_postgresql_rules(diff_content, files_in_diff))

        # Extract warnings from INFO violations
        warnings = [v.message for v in violations if v.severity == ViolationSeverity.INFO]

        # Passed if no SEVERE violations
        passed = not any(v.severity == ViolationSeverity.SEVERE for v in violations)

        return GovernanceResult(
            passed=passed,
            violations=violations,
            warnings=warnings
        )
    
    @staticmethod
    def _check_communication_rules(description: str) -> List[GovernanceViolation]:
        """Check communication rules (INFO level - guidance only)."""
        violations = []
        desc_lower = description.lower()
        
        # These are guidance rules, not blocking
        # Rule 10: "is this ready?" should trigger honest audit
        if "is this ready" in desc_lower or "ready?" in desc_lower:
            violations.append(GovernanceViolation(
                rule_id="COMM-010",
                message="Task asks 'is this ready' - provide honest WORKING/BROKEN audit",
                severity=ViolationSeverity.INFO
            ))
        
        return violations
    
    @staticmethod
    def _check_execution_rules(diff_content: str) -> List[GovernanceViolation]:
        """Check execution rules (WARNING level)."""
        violations = []

        # Rule 4: Never force push - uses centralized FORBIDDEN_PATTERNS["EXEC"]
        for pattern in FORBIDDEN_PATTERNS["EXEC"]:
            if pattern in diff_content:
                violations.append(GovernanceViolation(
                    rule_id="EXEC-004",
                    message="Force push detected in diff - never force push",
                    severity=ViolationSeverity.SEVERE
                ))
                break  # One violation is enough for force push

        # Rule 12: Do not create new test files unless asked
        # This is checked at description level, not diff level

        return violations
    
    @staticmethod
    def _check_database_rules(diff_content: str) -> List[GovernanceViolation]:
        """Check database rules (SEVERE level)."""
        violations = []

        diff_lower = diff_content.lower()

        # Rule 1: PostgreSQL only
        if any(db in diff_lower for db in ["mysql", "sqlite", "mongodb", "mongo", "mariadb"]):
            violations.append(GovernanceViolation(
                rule_id="DB-001",
                message="Non-PostgreSQL database detected - PostgreSQL only",
                severity=ViolationSeverity.SEVERE
            ))

        # Rule 2: Parameterized queries only - check for SQL string concatenation
        if any(pattern in diff_content for pattern in [
            "f\"SELECT", "f\"INSERT", "f\"UPDATE", "f\"DELETE",
            "\"SELECT \" +", "\"INSERT \" +", "\"UPDATE \" +", "\"DELETE \" +"
        ]):
            violations.append(GovernanceViolation(
                rule_id="DB-002",
                message="SQL string concatenation detected - use parameterized queries only",
                severity=ViolationSeverity.SEVERE
            ))

        return violations

    @staticmethod
    def _check_postgresql_rules(diff_content: str, files_in_diff: List[str]) -> List[GovernanceViolation]:
        """Check PostgreSQL-only enforcement rules (SEVERE level)."""
        violations = []

        diff_lower = diff_content.lower()

        # Check for prohibited database types
        for pattern in FORBIDDEN_PATTERNS["POSTGRES"]:
            if pattern in diff_lower:
                violations.append(GovernanceViolation(
                    rule_id="PG-001",
                    message=f"Prohibited database pattern detected: {pattern} - PostgreSQL only",
                    severity=ViolationSeverity.SEVERE
                ))
                break

        # Check for SQLite imports
        if 'import sqlite3' in diff_content or 'from sqlite3' in diff_content:
            violations.append(GovernanceViolation(
                rule_id="PG-002",
                message="SQLite import detected - use PostgreSQL only",
                severity=ViolationSeverity.SEVERE
            ))

        # Check for in-memory database usage
        if ':memory:' in diff_content or 'memory://' in diff_content:
            violations.append(GovernanceViolation(
                rule_id="PG-003",
                message="In-memory database detected - use PostgreSQL only",
                severity=ViolationSeverity.SEVERE
            ))

        # Warn if database connection without pooling
        if 'postgresql://' in diff_lower or 'postgres://' in diff_lower:
            if 'pool' not in diff_lower:
                violations.append(GovernanceViolation(
                    rule_id="PG-004",
                    message="PostgreSQL connection without pooling - consider adding connection pooling",
                    severity=ViolationSeverity.WARNING
                ))

        # Check for migration files without downgrade
        for file_path in files_in_diff:
            if 'alembic/versions/' in file_path or 'migrations/' in file_path:
                if 'def downgrade' not in diff_content:
                    violations.append(GovernanceViolation(
                        rule_id="PG-005",
                        message="Migration file missing downgrade() function",
                        severity=ViolationSeverity.SEVERE
                    ))
                    break

        return violations

