"""
AGENT NEO - Governance Module V3
Behavioral governance rules derived from user behavior patterns.
All rules are abstract and generalized - no domain-specific hardcoding.
"""

import re
from enum import Enum
from typing import List, Optional, Tuple
from dataclasses import dataclass, field


class ViolationSeverity(Enum):
    """Severity levels for governance violations."""
    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"


@dataclass
class GovernanceViolation:
    """Represents a governance rule violation."""
    rule_id: str
    rule_name: str
    severity: ViolationSeverity
    message: str
    suggestion: Optional[str] = None


@dataclass
class GovernanceResult:
    """Result of governance validation."""
    passed: bool
    violations: List[GovernanceViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def has_severe(self) -> bool:
        """Check if any severe violations exist."""
        return any(v.severity == ViolationSeverity.SEVERE for v in self.violations)
    
    @property
    def violation_count(self) -> int:
        return len(self.violations)


# =============================================================================
# PHASE 1: PRACTICAL RESPONSE ENFORCEMENT
# =============================================================================

class PracticalResponseRule:
    """
    Enforce practical-first responses.
    - Binary questions get YES/NO first
    - Complexity challenges get direct answers
    - "answer only" means no code
    """
    RULE_ID = "GOV-001"
    RULE_NAME = "Practical Response"
    
    # Patterns indicating binary questions
    BINARY_PATTERNS = [
        r'^(is|are|do|does|can|could|should|would|will|has|have|did)\s+',
        r'\?$',
    ]
    
    # Patterns indicating complexity challenge
    COMPLEXITY_CHALLENGE_PATTERNS = [
        r'does it (really )?matter',
        r'is this overkill',
        r'(too|overly) (restrictive|complex|complicated)',
        r'are you (making|being)',
    ]
    
    # Patterns indicating answer-only mode
    ANSWER_ONLY_PATTERNS = [
        r'answer only',
        r'just answer',
        r'no cod(e|ing)',
    ]
    
    @classmethod
    def detect_mode(cls, user_input: str) -> Tuple[str, bool]:
        """
        Detect response mode from user input.
        Returns: (mode, requires_enforcement)
        """
        lower_input = user_input.lower().strip()
        
        # Check answer-only first
        for pattern in cls.ANSWER_ONLY_PATTERNS:
            if re.search(pattern, lower_input, re.IGNORECASE):
                return ("answer_only", True)
        
        # Check complexity challenge
        for pattern in cls.COMPLEXITY_CHALLENGE_PATTERNS:
            if re.search(pattern, lower_input, re.IGNORECASE):
                return ("complexity_challenge", True)
        
        # Check binary question
        for pattern in cls.BINARY_PATTERNS:
            if re.search(pattern, lower_input, re.IGNORECASE):
                return ("binary_question", True)
        
        return ("standard", False)
    
    @classmethod
    def validate_response(cls, user_input: str, response: str) -> Optional[GovernanceViolation]:
        """Validate response follows practical-first rules."""
        mode, requires = cls.detect_mode(user_input)
        
        if not requires:
            return None
        
        response_start = response.strip()[:50].upper()
        
        if mode == "binary_question":
            if not (response_start.startswith("YES") or response_start.startswith("NO")):
                return GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.WARNING,
                    message="Binary question should start with YES or NO",
                    suggestion="Start response with direct YES/NO, then one-sentence reason"
                )
        
        if mode == "answer_only":
            if "```" in response:
                return GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.WARNING,
                    message="Answer-only mode requested but response contains code",
                    suggestion="Remove code blocks, provide text answer only"
                )
        
        return None


# =============================================================================
# PHASE 2: COPY-PASTE OUTPUT DISCIPLINE
# =============================================================================

class CopyPasteOutputRule:
    """
    Enforce copy-paste ready output.
    - Single code block for prompts/configs/commands/scripts
    - Complete and ready to run
    - No explanatory text outside block
    """
    RULE_ID = "GOV-002"
    RULE_NAME = "Copy-Paste Output"

    # Patterns indicating copy-paste request
    COPYABLE_REQUEST_PATTERNS = [
        r'give me (a |the )?(prompt|config|command|script)',
        r'(write|create|generate) (a |the )?(prompt|config|command|script)',
        r'(show|provide) (a |the )?(prompt|config|command|script)',
    ]

    @classmethod
    def is_copyable_request(cls, user_input: str) -> bool:
        """Check if user is requesting copyable output."""
        lower_input = user_input.lower()
        return any(re.search(p, lower_input) for p in cls.COPYABLE_REQUEST_PATTERNS)

    @classmethod
    def validate_response(cls, user_input: str, response: str) -> Optional[GovernanceViolation]:
        """Validate response is copy-paste ready when required."""
        if not cls.is_copyable_request(user_input):
            return None

        # Count code blocks
        code_blocks = re.findall(r'```[\s\S]*?```', response)

        if len(code_blocks) == 0:
            return GovernanceViolation(
                rule_id=cls.RULE_ID,
                rule_name=cls.RULE_NAME,
                severity=ViolationSeverity.WARNING,
                message="Copyable output requested but no code block provided",
                suggestion="Wrap output in single code block"
            )

        if len(code_blocks) > 1:
            return GovernanceViolation(
                rule_id=cls.RULE_ID,
                rule_name=cls.RULE_NAME,
                severity=ViolationSeverity.INFO,
                message="Multiple code blocks detected, prefer single block",
                suggestion="Consolidate into one complete, runnable block"
            )

        return None


# =============================================================================
# PHASE 3: ENTERPRISE-GRADE SOLO STANDARD
# =============================================================================

class EnterpriseStandardRule:
    """
    Enforce enterprise-grade standards even for solo projects.
    Required: health checks, restart policy, structured logging,
    monitoring hooks, secure config, proper env vars.
    """
    RULE_ID = "GOV-003"
    RULE_NAME = "Enterprise Standard"

    # Required infrastructure patterns
    REQUIRED_PATTERNS = {
        "health_check": [r'health', r'/health', r'healthcheck', r'liveness', r'readiness'],
        "restart_policy": [r'restart', r'restart.policy', r'always', r'on-failure'],
        "structured_logging": [r'logging', r'logger', r'log.format', r'json.log'],
        "env_config": [r'environ', r'getenv', r'\.env', r'config'],
    }

    # Shortcut patterns to reject
    SHORTCUT_PATTERNS = [
        r'skip.+health',
        r'no.+restart',
        r'disable.+log',
        r'hardcode',
    ]

    @classmethod
    def validate_diff(cls, diff_content: str, description: str) -> List[GovernanceViolation]:
        """Validate diff meets enterprise standards."""
        violations = []
        lower_desc = description.lower()

        # Check for deployment-related tasks
        deployment_keywords = ['deploy', 'docker', 'kubernetes', 'service', 'infrastructure']
        is_deployment = any(kw in lower_desc for kw in deployment_keywords)

        if not is_deployment:
            return violations

        # Check for shortcuts
        for pattern in cls.SHORTCUT_PATTERNS:
            if re.search(pattern, diff_content, re.IGNORECASE):
                violations.append(GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.SEVERE,
                    message=f"Shortcut pattern detected: {pattern}",
                    suggestion="Use enterprise-grade configuration"
                ))

        return violations


# =============================================================================
# PHASE 4: SIMPLICITY VS OVERENGINEERING
# =============================================================================

class SimplicityRule:
    """
    Prefer simplest working solution.
    Reject unnecessary infrastructure unless explicitly required.
    """
    RULE_ID = "GOV-004"
    RULE_NAME = "Simplicity First"

    # Overengineering indicators
    OVERENGINEERING_PATTERNS = [
        r'kafka',
        r'rabbitmq',
        r'redis.+(queue|pubsub)',
        r'kubernetes',
        r'microservice',
        r'event.?sourcing',
        r'cqrs',
        r'saga.?pattern',
    ]

    # Justification patterns
    JUSTIFICATION_PATTERNS = [
        r'need.+(scale|distributed|async)',
        r'require.+(queue|messaging)',
        r'must.+(decouple|separate)',
    ]

    @classmethod
    def validate_diff(cls, diff_content: str, description: str) -> Optional[GovernanceViolation]:
        """Check for overengineering without justification."""
        has_complex = any(
            re.search(p, diff_content, re.IGNORECASE)
            for p in cls.OVERENGINEERING_PATTERNS
        )

        if not has_complex:
            return None

        has_justification = any(
            re.search(p, description, re.IGNORECASE)
            for p in cls.JUSTIFICATION_PATTERNS
        )

        if has_justification:
            return None

        return GovernanceViolation(
            rule_id=cls.RULE_ID,
            rule_name=cls.RULE_NAME,
            severity=ViolationSeverity.WARNING,
            message="Complex infrastructure detected without explicit justification",
            suggestion="Prefer simpler solution or provide explicit requirement"
        )


# =============================================================================
# PHASE 5: FAST ITERATION MODE
# =============================================================================

class FastIterationRule:
    """
    Detect fast iteration directives.
    Short commands like "yes", "do it", "ship it" should proceed without clarification.
    """
    RULE_ID = "GOV-005"
    RULE_NAME = "Fast Iteration"

    # Fast iteration patterns
    FAST_PATTERNS = [
        r'^yes$',
        r'^no$',
        r'^ok$',
        r'^do it$',
        r'^ship it$',
        r'^fix it$',
        r'^loosen$',
        r'^proceed$',
        r'^continue$',
        r'^go$',
        r'^approved$',
    ]

    @classmethod
    def is_fast_directive(cls, user_input: str) -> bool:
        """Check if input is a fast iteration directive."""
        clean_input = user_input.lower().strip()
        return any(re.match(p, clean_input) for p in cls.FAST_PATTERNS)

    @classmethod
    def get_directive_type(cls, user_input: str) -> Optional[str]:
        """Get the type of fast directive."""
        clean_input = user_input.lower().strip()

        if clean_input in ['yes', 'ok', 'approved', 'proceed', 'continue', 'go']:
            return "confirm"
        if clean_input in ['do it', 'ship it']:
            return "execute"
        if clean_input == 'fix it':
            return "fix"
        if clean_input == 'loosen':
            return "relax_constraints"
        if clean_input == 'no':
            return "reject"

        return None


# =============================================================================
# PHASE 6: HONEST AUDIT MODE
# =============================================================================

class HonestAuditRule:
    """
    Detect audit requests and enforce honest, structured responses.
    No reassurance, no softening - direct WORKING/BROKEN lists.
    """
    RULE_ID = "GOV-006"
    RULE_NAME = "Honest Audit"

    # Audit trigger patterns
    AUDIT_PATTERNS = [
        r'is this ready',
        r'are we good',
        r'audit this',
        r'status check',
        r'what.+broken',
        r'what.+working',
        r'review this',
    ]

    @classmethod
    def is_audit_request(cls, user_input: str) -> bool:
        """Check if user is requesting an audit."""
        lower_input = user_input.lower()
        return any(re.search(p, lower_input) for p in cls.AUDIT_PATTERNS)

    @classmethod
    def format_audit_response(cls, working: List[str], broken: List[str]) -> str:
        """Format audit response in required structure."""
        lines = []

        lines.append("WORKING:")
        if working:
            for item in working:
                lines.append(f"- {item}")
        else:
            lines.append("- (none)")

        lines.append("")
        lines.append("BROKEN:")
        if broken:
            for item in broken:
                lines.append(f"- {item}")
        else:
            lines.append("- (none)")

        return "\n".join(lines)


# =============================================================================
# PHASE 7: CONTEXT PERSISTENCE
# =============================================================================

class ContextPersistenceRule:
    """
    Avoid re-explaining decisions already made.
    Reference recent changes implicitly.
    """
    RULE_ID = "GOV-007"
    RULE_NAME = "Context Persistence"

    # Patterns indicating redundant explanation
    REDUNDANT_PATTERNS = [
        r'as (i|we) (mentioned|discussed|explained) (earlier|before|previously)',
        r'to recap',
        r'as you (may )?know',
        r'let me explain again',
    ]

    @classmethod
    def validate_response(cls, response: str) -> Optional[GovernanceViolation]:
        """Check for redundant explanations."""
        for pattern in cls.REDUNDANT_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                return GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.INFO,
                    message="Redundant explanation detected",
                    suggestion="Reference context implicitly, avoid re-explaining"
                )
        return None


# =============================================================================
# PHASE 8: STRUCTURED COMPARISON
# =============================================================================

class StructuredComparisonRule:
    """
    Default to tables for comparisons.
    Avoid paragraph-only responses when evaluating options.
    """
    RULE_ID = "GOV-008"
    RULE_NAME = "Structured Comparison"

    # Comparison trigger patterns
    COMPARISON_PATTERNS = [
        r'compare',
        r'vs\.?',
        r'versus',
        r'difference between',
        r'which (is|should|would) (better|best)',
        r'pros and cons',
        r'tradeoffs?',
        r'options?',
    ]

    @classmethod
    def is_comparison_request(cls, user_input: str) -> bool:
        """Check if user is requesting a comparison."""
        lower_input = user_input.lower()
        return any(re.search(p, lower_input) for p in cls.COMPARISON_PATTERNS)

    @classmethod
    def validate_response(cls, user_input: str, response: str) -> Optional[GovernanceViolation]:
        """Check if comparison uses structured format."""
        if not cls.is_comparison_request(user_input):
            return None

        # Check for table markers
        has_table = '|' in response and '-|-' in response.replace(' ', '')
        has_list = re.search(r'^[\-\*]\s', response, re.MULTILINE)

        if not has_table and not has_list:
            return GovernanceViolation(
                rule_id=cls.RULE_ID,
                rule_name=cls.RULE_NAME,
                severity=ViolationSeverity.INFO,
                message="Comparison requested but no structured format used",
                suggestion="Use table or bullet list for clear tradeoffs"
            )

        return None


# =============================================================================
# PHASE 9: COMPLIANCE-FIRST AUTOMATION
# =============================================================================

class ComplianceRule:
    """
    No evasion, stealth, or bypass mechanisms.
    Prefer rate limiting, backoff, official APIs.
    """
    RULE_ID = "GOV-009"
    RULE_NAME = "Compliance First"

    # Bypass/evasion patterns to reject
    BYPASS_PATTERNS = [
        r'bypass',
        r'evade',
        r'stealth',
        r'avoid detection',
        r'spoof',
        r'fake.+(user.?agent|ip|header)',
        r'rotate.+proxy',
        r'captcha.+(bypass|solve|break)',
    ]

    # Compliant patterns to prefer
    COMPLIANT_PATTERNS = [
        r'rate.?limit',
        r'backoff',
        r'retry',
        r'official.?api',
        r'api.?key',
        r'oauth',
        r'throttle',
    ]

    @classmethod
    def validate_diff(cls, diff_content: str) -> Optional[GovernanceViolation]:
        """Check for bypass/evasion patterns."""
        for pattern in cls.BYPASS_PATTERNS:
            if re.search(pattern, diff_content, re.IGNORECASE):
                return GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.SEVERE,
                    message=f"Non-compliant pattern detected: {pattern}",
                    suggestion="Use official APIs, rate limiting, and backoff strategies"
                )
        return None


# =============================================================================
# PHASE 10: DOCUMENT SYNC
# =============================================================================

class DocumentSyncRule:
    """
    Detect operational docs and update them when code changes affect:
    - Environment variables
    - Deployment flow
    - Service configuration
    - API endpoints
    """
    RULE_ID = "GOV-010"
    RULE_NAME = "Document Sync"

    # Doc file patterns
    DOC_PATTERNS = [
        r'README\.md',
        r'CHANGELOG\.md',
        r'DEPLOY.*\.md',
        r'docs/',
        r'\.env\.example',
    ]

    # Change patterns requiring doc updates
    DOC_TRIGGER_PATTERNS = [
        r'(os\.)?getenv\([\'"](\w+)[\'"]\)',  # New env var
        r'@app\.(get|post|put|delete|patch)',  # New endpoint
        r'docker-compose',
        r'Dockerfile',
        r'\.service$',
    ]

    @classmethod
    def check_doc_sync_needed(cls, diff_content: str, existing_files: List[str]) -> Optional[GovernanceViolation]:
        """Check if doc sync is needed based on changes."""
        # Check if changes trigger doc update
        needs_update = any(
            re.search(p, diff_content, re.IGNORECASE)
            for p in cls.DOC_TRIGGER_PATTERNS
        )

        if not needs_update:
            return None

        # Check if docs are being updated
        docs_updated = any(
            any(re.search(dp, f, re.IGNORECASE) for dp in cls.DOC_PATTERNS)
            for f in existing_files
        )

        if docs_updated:
            return None

        return GovernanceViolation(
            rule_id=cls.RULE_ID,
            rule_name=cls.RULE_NAME,
            severity=ViolationSeverity.INFO,
            message="Code changes may require documentation updates",
            suggestion="Update README, .env.example, or deployment docs"
        )


# =============================================================================
# PHASE 11: RESPONSE TONE GOVERNANCE
# =============================================================================

class ResponseToneRule:
    """
    Enforce professional, direct tone.
    No fluff, no flattery, no defensive tone.
    """
    RULE_ID = "GOV-011"
    RULE_NAME = "Response Tone"

    # Fluff patterns to avoid
    FLUFF_PATTERNS = [
        r'^(great|good|excellent|wonderful|fantastic|amazing) (question|point|idea|observation)',
        r'^that\'s (a )?(great|good|excellent|interesting)',
        r'^i (really )?(like|love|appreciate)',
        r'^absolutely[!\.]',
        r'^definitely[!\.]',
    ]

    # Defensive patterns to avoid
    DEFENSIVE_PATTERNS = [
        r'i (might be|could be|may be) wrong',
        r'i\'m not (entirely )?sure',
        r'don\'t quote me',
        r'take this with a grain of salt',
    ]

    @classmethod
    def validate_response(cls, response: str) -> List[GovernanceViolation]:
        """Check response tone."""
        violations = []
        response_start = response[:200].lower()

        for pattern in cls.FLUFF_PATTERNS:
            if re.search(pattern, response_start, re.IGNORECASE):
                violations.append(GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.INFO,
                    message="Fluff/flattery detected in response",
                    suggestion="Skip flattery, respond directly"
                ))
                break

        for pattern in cls.DEFENSIVE_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                violations.append(GovernanceViolation(
                    rule_id=cls.RULE_ID,
                    rule_name=cls.RULE_NAME,
                    severity=ViolationSeverity.INFO,
                    message="Defensive tone detected",
                    suggestion="Be direct and confident"
                ))
                break

        return violations


# =============================================================================
# MAIN GOVERNANCE VALIDATOR
# =============================================================================

class GovernanceValidator:
    """
    Main governance validator that aggregates all rules.
    Used by engine.py to validate diffs and responses.
    """

    @classmethod
    def validate_diff(
        cls,
        diff_content: str,
        description: str,
        files_in_diff: Optional[List[str]] = None
    ) -> GovernanceResult:
        """
        Validate a diff against all governance rules.

        Args:
            diff_content: The diff content to validate
            description: Task description
            files_in_diff: List of files being modified

        Returns:
            GovernanceResult with violations and warnings
        """
        violations = []

        # Phase 3: Enterprise Standard
        enterprise_violations = EnterpriseStandardRule.validate_diff(diff_content, description)
        violations.extend(enterprise_violations)

        # Phase 4: Simplicity
        simplicity_violation = SimplicityRule.validate_diff(diff_content, description)
        if simplicity_violation:
            violations.append(simplicity_violation)

        # Phase 9: Compliance
        compliance_violation = ComplianceRule.validate_diff(diff_content)
        if compliance_violation:
            violations.append(compliance_violation)

        # Phase 10: Document Sync
        if files_in_diff:
            doc_violation = DocumentSyncRule.check_doc_sync_needed(diff_content, files_in_diff)
            if doc_violation:
                violations.append(doc_violation)

        # Determine if passed (no severe violations)
        passed = not any(v.severity == ViolationSeverity.SEVERE for v in violations)

        return GovernanceResult(
            passed=passed,
            violations=violations,
            warnings=[v.message for v in violations if v.severity == ViolationSeverity.WARNING]
        )

    @classmethod
    def validate_response(
        cls,
        user_input: str,
        response: str
    ) -> GovernanceResult:
        """
        Validate a response against governance rules.

        Args:
            user_input: The user's input/question
            response: The generated response

        Returns:
            GovernanceResult with violations
        """
        violations = []

        # Phase 1: Practical Response
        practical_violation = PracticalResponseRule.validate_response(user_input, response)
        if practical_violation:
            violations.append(practical_violation)

        # Phase 2: Copy-Paste Output
        copypaste_violation = CopyPasteOutputRule.validate_response(user_input, response)
        if copypaste_violation:
            violations.append(copypaste_violation)

        # Phase 7: Context Persistence
        context_violation = ContextPersistenceRule.validate_response(response)
        if context_violation:
            violations.append(context_violation)

        # Phase 8: Structured Comparison
        comparison_violation = StructuredComparisonRule.validate_response(user_input, response)
        if comparison_violation:
            violations.append(comparison_violation)

        # Phase 11: Response Tone
        tone_violations = ResponseToneRule.validate_response(response)
        violations.extend(tone_violations)

        passed = not any(v.severity == ViolationSeverity.SEVERE for v in violations)

        return GovernanceResult(
            passed=passed,
            violations=violations,
            warnings=[v.message for v in violations if v.severity == ViolationSeverity.WARNING]
        )

    @classmethod
    def detect_user_mode(cls, user_input: str) -> dict:
        """
        Detect special modes from user input.

        Returns dict with:
            - fast_iteration: bool
            - fast_directive: str or None
            - audit_request: bool
            - comparison_request: bool
            - answer_only: bool
        """
        return {
            "fast_iteration": FastIterationRule.is_fast_directive(user_input),
            "fast_directive": FastIterationRule.get_directive_type(user_input),
            "audit_request": HonestAuditRule.is_audit_request(user_input),
            "comparison_request": StructuredComparisonRule.is_comparison_request(user_input),
            "answer_only": PracticalResponseRule.detect_mode(user_input)[0] == "answer_only",
        }

    @classmethod
    def format_audit(cls, working: List[str], broken: List[str]) -> str:
        """Format an audit response."""
        return HonestAuditRule.format_audit_response(working, broken)