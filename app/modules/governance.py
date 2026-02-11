"""
AGENT NEO - Governance Module
User-defined behavioral rules only.
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


class GovernanceValidator:
    """Validates diffs against user-defined governance rules."""
    
    @staticmethod
    def validate_diff(
        diff_content: str,
        description: str,
        files_in_diff: List[str]
    ) -> GovernanceResult:
        """
        Validate diff against all governance rules.
        
        Args:
            diff_content: The unified diff content
            description: Task description
            files_in_diff: List of file paths in diff
            
        Returns:
            GovernanceResult with violations and warnings
        """
        violations = []
        warnings = []
        
        # COMMUNICATION RULES - all INFO level (guidance only)
        violations.extend(GovernanceValidator._check_communication_rules(description))
        
        # EXECUTION RULES - WARNING level
        violations.extend(GovernanceValidator._check_execution_rules(diff_content, files_in_diff))
        
        # DATABASE RULES - SEVERE level
        violations.extend(GovernanceValidator._check_database_rules(diff_content))
        
        # ERROR HANDLING RULES - WARNING level
        violations.extend(GovernanceValidator._check_error_handling_rules(diff_content))
        
        # API RULES - SEVERE level
        violations.extend(GovernanceValidator._check_api_rules(diff_content, files_in_diff))
        
        # DEPLOYMENT RULES - WARNING level
        violations.extend(GovernanceValidator._check_deployment_rules(diff_content, files_in_diff))
        
        # LOGGING RULES - WARNING level
        violations.extend(GovernanceValidator._check_logging_rules(diff_content))
        
        # SIMPLICITY RULE - INFO level
        violations.extend(GovernanceValidator._check_simplicity_rules(diff_content, description))
        
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
    def _check_execution_rules(diff_content: str, files_in_diff: List[str]) -> List[GovernanceViolation]:
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

    @staticmethod
    def _check_error_handling_rules(diff_content: str) -> List[GovernanceViolation]:
        """Check error handling rules (WARNING level)."""
        violations = []
        # No automated checks - these are runtime/code review concerns
        return violations

    @staticmethod
    def _check_api_rules(diff_content: str, files_in_diff: List[str]) -> List[GovernanceViolation]:
        """Check API rules (SEVERE level for breaking changes)."""
        violations = []
        # No automated checks - breaking changes need semantic analysis
        return violations

    @staticmethod
    def _check_deployment_rules(diff_content: str, files_in_diff: List[str]) -> List[GovernanceViolation]:
        """Check deployment rules (WARNING level)."""
        violations = []

        # Rule 2: Run migrations before serving traffic
        # This is a deployment-time check, not diff-time

        return violations

    @staticmethod
    def _check_logging_rules(diff_content: str) -> List[GovernanceViolation]:
        """Check logging rules (WARNING/SEVERE level)."""
        violations = []
        # No automated checks - sensitive data detection needs semantic analysis
        return violations

    @staticmethod
    def _check_simplicity_rules(diff_content: str, description: str) -> List[GovernanceViolation]:
        """Check simplicity rules (INFO level - guidance only)."""
        violations = []

        # Rule 2: Do not over-engineer
        # This is subjective and guidance-only

        return violations

