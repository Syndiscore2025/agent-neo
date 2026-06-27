"""
AGENT NEO - Interactive Contracts
Pydantic models for interactive/chat features.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ---------------------------------------------------------------------------
# Execution result card — typed subset of core ExecuteResponse surfaced to UI
# ---------------------------------------------------------------------------
class ExecutionResultCard(BaseModel):
    """Structured execution result surfaced to the chat UI after diff approval."""
    status: str                                          # "Working" | "Broken"
    mode: str                                            # "CRITICAL" | "RAPID"
    commit_sha: Optional[str] = None
    pre_run_ref: Optional[str] = None                    # HEAD before this run's commit
    files_changed: List[str] = Field(default_factory=list)
    lines_changed: int = 0
    pushed: bool = False
    verify_steps: List[str] = Field(default_factory=list)
    rollback_command: Optional[str] = None
    pre_test_passed: Optional[bool] = None
    post_test_passed: Optional[bool] = None
    validation_passed: Optional[bool] = None
    error: Optional[str] = None
    reverted: bool = False


class ActionType(str):
    """Action types for chat responses."""
    CONVERSATIONAL = "conversational"
    DIFF_PROPOSAL = "diff_proposal"
    EXPLAIN = "explain"
    ERROR = "error"


class ChatMessage(BaseModel):
    """Single chat message."""
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    attachments: Optional[List[str]] = Field(default_factory=list)


class ChatContext(BaseModel):
    """Context information for chat request."""
    current_file: Optional[str] = None
    current_file_content: Optional[str] = None
    selected_code: Optional[str] = None
    selection_start_line: Optional[int] = None
    selection_end_line: Optional[int] = None
    workspace_path: Optional[str] = None
    language: Optional[str] = None
    # VS Code diagnostics (errors/warnings) collected by the extension
    diagnostics: Optional[List[str]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    context: Optional[ChatContext] = None
    attachment_ids: Optional[List[str]] = Field(default_factory=list)
    model: Optional[str] = None  # e.g. "claude-sonnet", "claude-opus", "gpt"


class DiffProposal(BaseModel):
    """Proposed code changes."""
    diff: str
    files_changed: List[str]
    additions: int
    deletions: int
    summary: str


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    session_id: str
    message: str
    action_type: str  # ActionType value
    proposed_diff: Optional[DiffProposal] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    """Chat session state."""
    session_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    proposed_diff: Optional[str] = None
    context: Optional[ChatContext] = None
    last_execution: Optional[ExecutionResultCard] = None   # for rollback
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatHistoryResponse(BaseModel):
    """Response for chat history."""
    session_id: str
    messages: List[ChatMessage]
    total_messages: int


class ApprovalRequest(BaseModel):
    """Request to approve or reject a proposed diff."""
    session_id: str
    approved: bool
    push: bool = False  # If True, push to remote after applying


class ApprovalResponse(BaseModel):
    """Response from approval action."""
    session_id: str
    approved: bool
    message: str
    execution_result: Optional[ExecutionResultCard] = None


class CompletionRequest(BaseModel):
    """Request for inline code completion."""
    file_path: str
    cursor_line: int
    cursor_column: int
    surrounding_code: str
    language: Optional[str] = None


class CompletionResponse(BaseModel):
    """Response with code completion suggestion."""
    suggestion: str
    confidence: float = Field(ge=0.0, le=1.0)


class AttachmentUpload(BaseModel):
    """Attachment upload request."""
    session_id: str
    file_name: str
    file_type: Literal["image", "pdf"]
    content_base64: str


class AttachmentResponse(BaseModel):
    """Response from attachment upload."""
    attachment_id: str
    session_id: str
    file_name: str
    file_type: str
    extracted_content: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SuggestionRequest(BaseModel):
    """Request for prompt suggestions."""
    session_id: Optional[str] = None
    current_input: str
    context: Optional[ChatContext] = None


class SuggestionResponse(BaseModel):
    """Response with prompt suggestions."""
    suggestions: List[str]


# ---------------------------------------------------------------------------
# Thread-switching / new-agent handoff
# ---------------------------------------------------------------------------
class SummarizeRequest(BaseModel):
    """Request to summarise the current session and hand off to a new thread."""
    session_id: str


class SessionSummaryResponse(BaseModel):
    """Response carrying a digest of the old thread + a fresh session ID."""
    old_session_id: str
    new_session_id: str
    summary: str                    # LLM-generated digest injected as system context
    message_count_was: int          # how many messages were in the old session


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------
class RollbackRequest(BaseModel):
    """Request to undo the last applied change."""
    session_id: str


class RollbackResponse(BaseModel):
    """Response after attempting a git rollback."""
    session_id: str
    success: bool
    message: str
    commit_reverted: Optional[str] = None
    restored_to: Optional[str] = None   # pre-run ref the run was rolled back to


# ---------------------------------------------------------------------------
# Task-aware context selection (Phase B)
# ---------------------------------------------------------------------------
class FileContext(BaseModel):
    """A file selected for a task, with the reason it was chosen."""
    path: str
    reason: str               # human-readable, e.g. "semantic match for 'payments'"
    score: Optional[float] = None
    source: str = "search"    # "active_file" | "import" | "test_file" | "sibling"
                              # | "semantic" | "keyword" | "convention" | "cross_repo"
    repo: Optional[str] = None  # managed-repo name when the file is from a non-active repo


class ServiceNode(BaseModel):
    """A service or manifest discovered in the repo's dependency graph."""
    name: str
    kind: str                 # "node" | "python" | "docker" | "compose-service"
    manifest: str             # repo-relative path to the manifest it came from
    depends_on: List[str] = Field(default_factory=list)
    key_dependencies: List[str] = Field(default_factory=list)


class ServiceGraph(BaseModel):
    """Coarse cross-service dependency graph parsed from repo manifests."""
    nodes: List[ServiceNode] = Field(default_factory=list)
    summary: str = ""


class CommitInfo(BaseModel):
    """A git commit surfaced as 'why/when did this change' context."""
    sha: str
    short_sha: str
    author: str = ""
    date: str = ""
    subject: str = ""
    files: List[str] = Field(default_factory=list)
    reason: str = ""          # why it was surfaced, e.g. "touches payments.py"


class GitHistory(BaseModel):
    """Commits from git history relevant to the current task."""
    commits: List[CommitInfo] = Field(default_factory=list)
    summary: str = ""


class ContextPack(BaseModel):
    """Ranked, explainable set of files relevant to a task."""
    task: str
    primary_files: List[FileContext] = Field(default_factory=list)
    supporting_files: List[FileContext] = Field(default_factory=list)
    summary: str = ""
    service_graph: Optional[ServiceGraph] = None
    recent_history: Optional[GitHistory] = None


# ---------------------------------------------------------------------------
# Verification + bounded repair (Phase C)
# ---------------------------------------------------------------------------
class VerificationSummary(BaseModel):
    """Final outcome of the system-controlled verification/repair loop."""
    final_status: str = "skipped"    # "passed" | "failed" | "skipped"
    checks_run: List[str] = Field(default_factory=list)
    passed: bool = True
    repair_attempted: bool = False
    repair_attempts: int = 0
    last_failure_summary: str = ""


# ---------------------------------------------------------------------------
# Autonomous task runner
# ---------------------------------------------------------------------------
class AutoRunStep(BaseModel):
    """Single step in an autonomous run."""
    step_name: str           # "plan" | "diff" | "apply" | "verify"
    status: str              # "success" | "failed" | "skipped"
    message: str
    duration_ms: Optional[int] = None


class AutoRunRequest(BaseModel):
    """Request to execute a task fully autonomously (plan → diff → apply → verify)."""
    session_id: Optional[str] = None
    task: str = Field(..., min_length=1)
    context: Optional[ChatContext] = None
    push: bool = False       # If True, push to remote after applying
    model: Optional[str] = None  # Any resolvable model id (e.g. claude-opus, gpt-4o)


class AutoRunResponse(BaseModel):
    """Response from an autonomous task run."""
    session_id: str
    task: str
    steps: List[AutoRunStep]
    overall_status: str      # "success" | "failed" | "partial"
    summary: str
    execution_result: Optional[ExecutionResultCard] = None
    context_summary: Optional[str] = None
    context_files: List[FileContext] = Field(default_factory=list)
    verification: Optional[VerificationSummary] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# SSE Streaming events (yielded by /chat/autorun/stream)
# ---------------------------------------------------------------------------
class StreamEvent(BaseModel):
    """Single SSE payload emitted during a streaming agent run."""
    type: str          # "tool_start" | "tool_end" | "text" | "finish" | "commit" | "error"
    tool: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    result: Optional[str] = None
    duration_ms: Optional[int] = None
    content: Optional[str] = None   # incremental text tokens
    success: Optional[bool] = None
    summary: Optional[str] = None
    sha: Optional[str] = None
    files: Optional[List[str]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Integrations registry / proxy
# ---------------------------------------------------------------------------
class IntegrationCatalogEntry(BaseModel):
    """Built-in service preset surfaced to the Coding Matrix UI."""
    provider: str
    label: str
    description: str
    default_base_url: Optional[str] = None
    default_auth_type: Literal["bearer", "x-api-key", "custom_header", "none"] = "bearer"
    default_auth_header: str = "Authorization"
    default_auth_scheme: Optional[str] = "Bearer"


class IntegrationUpsertRequest(BaseModel):
    """Create or update a stored integration secret/config."""
    provider: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    auth_type: Literal["bearer", "x-api-key", "custom_header", "none"] = "bearer"
    auth_header: str = "Authorization"
    auth_scheme: Optional[str] = "Bearer"
    secret: Optional[str] = None
    clear_secret: bool = False
    headers: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class IntegrationSummary(BaseModel):
    """Sanitized integration record returned to the browser."""
    id: str
    provider: str
    label: str
    base_url: Optional[str] = None
    auth_type: Literal["bearer", "x-api-key", "custom_header", "none"] = "bearer"
    auth_header: str = "Authorization"
    auth_scheme: Optional[str] = "Bearer"
    headers: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None
    secret_configured: bool = False
    created_at: datetime
    updated_at: datetime


class IntegrationsListResponse(BaseModel):
    """Collection wrapper for stored integrations."""
    integrations: List[IntegrationSummary] = Field(default_factory=list)


class DeleteIntegrationResponse(BaseModel):
    """Delete confirmation."""
    deleted: bool
    integration_id: str


# ---------------------------------------------------------------------------
# Workspace / Repo binding
# ---------------------------------------------------------------------------

class WorkspaceBindRequest(BaseModel):
    """Request to clone a GitHub repo and bind it as the active workspace."""
    integration_id: str = Field(..., description="ID of the GitHub integration stored in the registry")
    owner: str
    repo: str
    branch: str = "main"


class WorkspaceBindResponse(BaseModel):
    """Result of a workspace bind operation."""
    bound: bool
    owner: str
    repo: str
    branch: str
    workspace_path: str
    file_count: int


class WorkspaceStatusResponse(BaseModel):
    """Current workspace binding status."""
    bound: bool
    owner: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    workspace_path: Optional[str] = None
    file_count: int = 0


class WorkspaceCommitRequest(BaseModel):
    """Request to commit and push changes from the active workspace."""
    integration_id: str = Field(..., description="GitHub integration to use for authentication")
    message: str = Field(..., description="Git commit message")


class WorkspaceCommitResponse(BaseModel):
    """Result of a commit+push operation."""
    committed: bool
    pushed: bool
    sha: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Managed repos — durable repo registry (attach / clone / activate)
# ---------------------------------------------------------------------------

class RepoAttachRequest(BaseModel):
    """Request to register an already-local git repo."""
    path: str = Field(..., min_length=1, description="Absolute path to a local git repository")
    name: Optional[str] = None


class RepoCloneRequest(BaseModel):
    """Request to clone a GitHub repo into a user-chosen path and register it."""
    url: str = Field(..., min_length=1, description="Repository URL (https)")
    dest_path: str = Field(..., min_length=1, description="Absolute destination path for the clone")
    name: Optional[str] = None
    # Transient credential: used only for this clone, never persisted or logged
    token: Optional[str] = None


class RepoActivateRequest(BaseModel):
    """Request to mark a managed repo as the active one."""
    repo_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# External integrations — MCP servers + governed CLI tools
# ---------------------------------------------------------------------------

class McpServerUpsertRequest(BaseModel):
    """Create or update an MCP server registration (no secret values)."""
    name: Optional[str] = None
    transport: Optional[Literal["stdio", "http"]] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    # Binding name → secret reference (values live in SecretStorage / backend env)
    secret_env: Optional[Dict[str, str]] = None
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


class McpSecretsRequest(BaseModel):
    """Push secret values for an MCP server (held in memory only)."""
    secrets: Dict[str, str] = Field(default_factory=dict)


class CliToolUpsertRequest(BaseModel):
    """Create or update a governed CLI tool registration."""
    name: Optional[str] = None
    executable: Optional[str] = None
    default_args: Optional[List[str]] = None
    allowed_subcommands: Optional[List[str]] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = None
    description: Optional[str] = None

