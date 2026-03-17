"""
AGENT NEO - Interactive Contracts
Pydantic models for interactive/chat features.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


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


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1)
    context: Optional[ChatContext] = None


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
    execution_result: Optional[Dict[str, Any]] = None


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

