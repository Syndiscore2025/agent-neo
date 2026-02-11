"""
AGENT NEO - Core Engine
Main execution pipeline.
"""

import os
from typing import Literal, Optional
from pathlib import Path

from app.core.contracts import (
    TaskRequest,
    ExecuteResponse,
    PlanResponse,
    ValidationResult,
    TestResult
)
from app.core.modes import detect_mode
from app.core.policy import should_auto_push, validate_push_safety
from app.core.validation import validate_diff, parse_diff_metadata
from app.core.output import (
    create_success_response,
    create_error_response,
    log_operation
)
from app.modules.git_guard import (
    validate_git_state,
    get_git_state,
    get_last_commits
)
from app.modules.patch_git import apply_patch, commit_changes, push_to_main
from app.modules.tests_runner import run_tests
from app.modules.repo_context import scan_repository
from app.modules.governance import GovernanceValidator, ViolationSeverity


class Engine:
    """Core execution engine for AGENT NEO."""
    
    def __init__(self, repo_path: str):
        """
        Initialize engine.
        
        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        self._load_kernel()
    
    def _load_kernel(self):
        """Load kernel rules from files."""
        kernel_path = Path(__file__).parent.parent / "kernel"
        self.kernel_rules = {}
        
        for kernel_file in ["KERNEL.md", "STYLE.md", "GUARDRAILS.md", "PLAYBOOKS.md"]:
            file_path = kernel_path / kernel_file
            if file_path.exists():
                self.kernel_rules[kernel_file] = file_path.read_text()
    
    def plan(self, request: TaskRequest) -> PlanResponse:
        """
        Generate execution plan.
        
        Args:
            request: Task request
            
        Returns:
            PlanResponse object
        """
        mode, critical_keywords = detect_mode(request.description)
        
        # Scan repository context
        repo_info = scan_repository(str(self.repo_path))
        
        # Estimate files to modify (simplified - would need AI/LLM in production)
        files_to_modify = []
        estimated_lines = 0
        
        if request.diff:
            metadata = parse_diff_metadata(request.diff)
            files_to_modify = metadata.file_paths
            estimated_lines = metadata.total_lines_changed
        
        validation_warnings = []
        if mode == "CRITICAL":
            validation_warnings.append("CRITICAL mode: auto-push blocked unless force=true")
        
        return PlanResponse(
            task_id=request.task_id,
            mode=mode,
            files_to_modify=files_to_modify,
            estimated_lines=estimated_lines,
            validation_warnings=validation_warnings,
            critical_keywords_found=critical_keywords
        )
    
    def execute(self, request: TaskRequest) -> ExecuteResponse:
        """
        Execute task with full pipeline.
        
        Args:
            request: Task request
            
        Returns:
            ExecuteResponse object
        """
        # Detect mode
        mode, _ = detect_mode(request.description)
        
        log_operation(
            task_id=request.task_id,
            mode=mode,
            operation="execute_start",
            status="Working"
        )
        
        try:
            # Initialize governance_warnings
            governance_warnings = []

            # Step 1: Validate git state
            require_remote = os.getenv("REQUIRE_REMOTE", "true").lower() == "true"
            validate_git_state(str(self.repo_path), require_remote=require_remote)

            # Step 2: Get git log
            last_commits = get_last_commits(str(self.repo_path), count=5)

            # Step 3: Validate diff
            if not request.diff:
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error="No diff provided"
                )
            
            validation_result = validate_diff(request.diff, mode)
            if not validation_result.valid:
                log_operation(
                    task_id=request.task_id,
                    mode=mode,
                    operation="validation_failed",
                    status="Broken",
                    errors=validation_result.errors
                )
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error=f"Validation failed: {', '.join(validation_result.errors)}",
                    validation_result=validation_result
                )
            
            # Step 4: Governance validation
            diff_metadata = parse_diff_metadata(request.diff)
            governance_result = GovernanceValidator.validate_diff(
                diff_content=request.diff,
                description=request.description,
                files_in_diff=diff_metadata.file_paths
            )

            # Capture warnings for success response
            governance_warnings = governance_result.warnings

            if governance_result.violations:
                log_operation(
                    task_id=request.task_id,
                    mode=mode,
                    operation="governance_check",
                    status="Working" if governance_result.passed else "Broken",
                    governance_violations=[
                        {"rule": v.rule_id, "message": v.message, "severity": v.severity.value}
                        for v in governance_result.violations
                    ]
                )

                # CRITICAL mode: block on severe violations
                if mode == "CRITICAL" and governance_result.has_severe:
                    severe_violations = [v for v in governance_result.violations if v.severity == ViolationSeverity.SEVERE]
                    return create_error_response(
                        task_id=request.task_id,
                        mode=mode,
                        error=f"Governance violations (CRITICAL mode blocks severe): {', '.join(v.message for v in severe_violations)}",
                        validation_result=validation_result
                    )

                # RAPID mode: block on severe violations
                if mode == "RAPID" and governance_result.has_severe:
                    severe_violations = [v for v in governance_result.violations if v.severity == ViolationSeverity.SEVERE]
                    return create_error_response(
                        task_id=request.task_id,
                        mode=mode,
                        error=f"Governance violations (severe): {', '.join(v.message for v in severe_violations)}",
                        validation_result=validation_result
                    )

            # Step 5: Validate push safety
            safe, reason = validate_push_safety(
                mode=mode,
                files_changed=validation_result.files_changed,
                lines_changed=validation_result.lines_added + validation_result.lines_removed
            )
            if not safe:
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error=reason,
                    validation_result=validation_result
                )

            # Step 6: Run pre-tests
            pre_test_result = run_tests(str(self.repo_path))
            if not pre_test_result.passed:
                log_operation(
                    task_id=request.task_id,
                    mode=mode,
                    operation="pre_tests_failed",
                    status="Broken"
                )
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error="Pre-apply tests failed",
                    test_result=pre_test_result
                )
            
            # Step 6: Apply patch
            apply_success, apply_error = apply_patch(str(self.repo_path), request.diff)
            if not apply_success:
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error=f"Failed to apply patch: {apply_error}"
                )
            
            # Step 7: Commit changes
            commit_message = f"[AGENT NEO] {request.task_id}: {request.description[:100]}"
            commit_sha, commit_error = commit_changes(str(self.repo_path), commit_message)
            if not commit_sha:
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error=f"Failed to commit: {commit_error}"
                )
            
            # Step 8: Run post-tests
            post_test_result = run_tests(str(self.repo_path))
            if not post_test_result.passed:
                log_operation(
                    task_id=request.task_id,
                    mode=mode,
                    operation="post_tests_failed",
                    status="Broken",
                    commit_sha=commit_sha
                )
                return create_error_response(
                    task_id=request.task_id,
                    mode=mode,
                    error="Post-apply tests failed. Changes committed but not pushed.",
                    test_result=post_test_result
                )
            
            # Step 9: Push to main (if allowed)
            pushed = False
            skip_push = os.getenv("SKIP_PUSH", "false").lower() == "true"
            if should_auto_push(mode, request.force) and not skip_push:
                push_success, push_error = push_to_main(str(self.repo_path))
                if not push_success:
                    return create_error_response(
                        task_id=request.task_id,
                        mode=mode,
                        error=f"Failed to push: {push_error}. Changes committed locally."
                    )
                pushed = True
            
            # Step 10: Create success response
            metadata = parse_diff_metadata(request.diff)
            
            summary = f"Successfully applied changes. Mode: {mode}. "
            if pushed:
                summary += "Changes pushed to main."
            else:
                summary += "Changes committed locally. Manual push required."

            if governance_warnings:
                summary += f" Governance warnings: {len(governance_warnings)}."

            log_operation(
                task_id=request.task_id,
                mode=mode,
                operation="execute_complete",
                status="Working",
                commit_sha=commit_sha,
                files_changed=validation_result.files_changed,
                lines_changed=validation_result.lines_added + validation_result.lines_removed,
                pushed=pushed,
                governance_warnings=governance_warnings
            )

            return create_success_response(
                task_id=request.task_id,
                mode=mode,
                commit_sha=commit_sha,
                summary=summary,
                files_changed=metadata.file_paths,
                lines_changed=metadata.total_lines_changed,
                validation_result=validation_result,
                pre_test_result=pre_test_result,
                post_test_result=post_test_result,
                pushed=pushed,
                governance_warnings=governance_warnings if governance_warnings else None
            )
            
        except Exception as e:
            log_operation(
                task_id=request.task_id,
                mode=mode,
                operation="execute_error",
                status="Broken",
                error=str(e)
            )
            return create_error_response(
                task_id=request.task_id,
                mode=mode,
                error=f"Execution error: {str(e)}"
            )

