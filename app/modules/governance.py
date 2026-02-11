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
        
        # Rule 4: Never force push
        if "--force" in diff_content or "git push -f" in diff_content or "git push --force" in diff_content:
            violations.append(GovernanceViolation(
                rule_id="EXEC-004",
                message="Force push detected in diff - never force push",
                severity=ViolationSeverity.SEVERE
            ))
        
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

