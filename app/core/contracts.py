"""
AGENT NEO - Contracts
Strict Pydantic models for all API interactions.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime


class TaskRequest(BaseModel):
    """Request to execute a task."""
    task_id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="Task description")
    diff: Optional[str] = Field(None, description="Unified diff to apply")
    force: bool = Field(False, description="Force push in CRITICAL mode")
    
    @validator('task_id')
    def validate_task_id(cls, v):
        if not v or not v.strip():
            raise ValueError("task_id cannot be empty")
        return v.strip()
    
    @validator('description')
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError("description cannot be empty")
        return v.strip()


class PlanResponse(BaseModel):
    """Response from plan generation."""
    task_id: str
    mode: Literal["RAPID", "CRITICAL"]
    files_to_modify: List[str]
    estimated_lines: int
    validation_warnings: List[str]
    critical_keywords_found: List[str]


class ValidationResult(BaseModel):
    """Result of diff validation."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    forbidden_patterns: List[str] = Field(default_factory=list)


class TestResult(BaseModel):
    """Result of test execution."""
    passed: bool
    output: str
    duration_seconds: float
    coverage_percent: Optional[float] = None


class ExecuteResponse(BaseModel):
    """Response from task execution."""
    status: Literal["Working", "Broken"]
    task_id: str
    mode: Literal["RAPID", "CRITICAL"]
    commit_sha: Optional[str] = None
    summary: str
    files_changed: List[str] = Field(default_factory=list)
    lines_changed: int = 0
    validation_result: Optional[ValidationResult] = None
    pre_test_result: Optional[TestResult] = None
    post_test_result: Optional[TestResult] = None
    pushed: bool = False
    verify_steps: List[str] = Field(default_factory=list)
    rollback_command: Optional[str] = None
    governance_warnings: Optional[List[str]] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["Working", "Broken"]
    branch: str
    clean: bool
    remote: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class GitState(BaseModel):
    """Current git repository state."""
    branch: str
    clean: bool
    detached: bool
    remote_reachable: bool
    last_commit_sha: str
    last_commit_message: str


class DiffMetadata(BaseModel):
    """Metadata extracted from a diff."""
    files_changed: int
    lines_added: int
    lines_removed: int
    total_lines_changed: int
    file_paths: List[str]
    is_valid_unified_diff: bool
    
    @property
    def total_changes(self) -> int:
        return self.lines_added + self.lines_removed

