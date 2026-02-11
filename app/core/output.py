"""
AGENT NEO - Output Formatting
Structured output generation.
"""

import logging
from datetime import datetime
from typing import List, Optional, Literal
from app.core.contracts import ExecuteResponse, ValidationResult, TestResult


# Configure logging
logging.basicConfig(
    format='[AGENT NEO] [%(asctime)s] [%(levelname)s] [%(module)s] %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def log_operation(
    task_id: str,
    mode: Literal["RAPID", "CRITICAL"],
    operation: str,
    status: Literal["Working", "Broken"],
    commit_sha: Optional[str] = None,
    files_changed: int = 0,
    lines_changed: int = 0,
    **kwargs
):
    """
    Log operation with structured data.
    
    Args:
        task_id: Task identifier
        mode: Execution mode
        operation: Operation name
        status: Working or Broken
        commit_sha: Git commit SHA if committed
        files_changed: Number of files changed
        lines_changed: Number of lines changed
        **kwargs: Additional context
    """
    log_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task_id,
        "mode": mode,
        "operation": operation,
        "status": status,
        "commit_sha": commit_sha,
        "files_changed": files_changed,
        "lines_changed": lines_changed,
        **kwargs
    }
    
    log_message = " | ".join([f"{k}={v}" for k, v in log_data.items() if v is not None])
    
    if status == "Working":
        logger.info(log_message)
    else:
        logger.error(log_message)


def create_success_response(
    task_id: str,
    mode: Literal["RAPID", "CRITICAL"],
    commit_sha: str,
    summary: str,
    files_changed: List[str],
    lines_changed: int,
    validation_result: ValidationResult,
    pre_test_result: Optional[TestResult],
    post_test_result: Optional[TestResult],
    pushed: bool,
    governance_warnings: Optional[List[str]] = None
) -> ExecuteResponse:
    """
    Create success response.

    Args:
        task_id: Task identifier
        mode: Execution mode
        commit_sha: Git commit SHA
        summary: Summary message
        files_changed: List of changed files
        lines_changed: Total lines changed
        validation_result: Validation result
        pre_test_result: Pre-apply test result
        post_test_result: Post-apply test result
        pushed: Whether changes were pushed
        governance_warnings: Optional governance warnings

    Returns:
        ExecuteResponse object
    """
    rollback_command = f"git revert {commit_sha} --no-edit && git push origin main"

    verify_steps = [
        f"git show {commit_sha}",
        f"git log -1 {commit_sha}",
        "git status",
    ]

    if pushed:
        verify_steps.append("git log origin/main -1")

    return ExecuteResponse(
        status="Working",
        task_id=task_id,
        mode=mode,
        commit_sha=commit_sha,
        summary=summary,
        files_changed=files_changed,
        lines_changed=lines_changed,
        validation_result=validation_result,
        pre_test_result=pre_test_result,
        post_test_result=post_test_result,
        pushed=pushed,
        verify_steps=verify_steps,
        rollback_command=rollback_command,
        governance_warnings=governance_warnings
    )


def create_error_response(
    task_id: str,
    mode: Literal["RAPID", "CRITICAL"],
    error: str,
    validation_result: Optional[ValidationResult] = None,
    test_result: Optional[TestResult] = None
) -> ExecuteResponse:
    """
    Create error response.
    
    Args:
        task_id: Task identifier
        mode: Execution mode
        error: Error message
        validation_result: Validation result if available
        test_result: Test result if available
        
    Returns:
        ExecuteResponse object
    """
    return ExecuteResponse(
        status="Broken",
        task_id=task_id,
        mode=mode,
        summary=f"Execution failed: {error}",
        error=error,
        validation_result=validation_result,
        pre_test_result=test_result,
        pushed=False
    )


def format_test_output(output: str, max_lines: int = 50) -> str:
    """
    Format test output, keeping last N lines.
    
    Args:
        output: Full test output
        max_lines: Maximum lines to keep
        
    Returns:
        Formatted output
    """
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output
    
    return '\n'.join(lines[-max_lines:])

