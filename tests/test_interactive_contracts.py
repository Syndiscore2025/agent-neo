"""
Tests for interactive contracts.
"""

import pytest
from datetime import datetime
from app.interactive.contracts import (
    ChatMessage,
    ChatContext,
    ChatRequest,
    ChatResponse,
    ChatSession,
    ApprovalRequest,
    ApprovalResponse,
    CompletionRequest,
    CompletionResponse,
    AttachmentUpload,
    AttachmentResponse,
    SuggestionRequest,
    SuggestionResponse,
    DiffProposal,
    ActionType
)


class TestContracts:
    """Test interactive contract models."""
    
    def test_chat_message(self):
        """Test ChatMessage model."""
        message = ChatMessage(
            role="user",
            content="Hello"
        )
        
        assert message.role == "user"
        assert message.content == "Hello"
        assert isinstance(message.timestamp, datetime)
        assert message.attachments == []
    
    def test_chat_context(self):
        """Test ChatContext model."""
        context = ChatContext(
            current_file="test.py",
            language="python",
            selected_code="def test(): pass"
        )
        
        assert context.current_file == "test.py"
        assert context.language == "python"
        assert context.selected_code == "def test(): pass"
    
    def test_chat_request(self):
        """Test ChatRequest model."""
        request = ChatRequest(
            message="Explain this code",
            session_id="test-session"
        )
        
        assert request.message == "Explain this code"
        assert request.session_id == "test-session"
    
    def test_chat_response(self):
        """Test ChatResponse model."""
        response = ChatResponse(
            session_id="test-session",
            message="Here's the explanation",
            action_type=ActionType.CONVERSATIONAL
        )
        
        assert response.session_id == "test-session"
        assert response.message == "Here's the explanation"
        assert response.action_type == ActionType.CONVERSATIONAL
    
    def test_chat_session(self):
        """Test ChatSession model."""
        session = ChatSession(
            session_id="test-session",
            messages=[]
        )
        
        assert session.session_id == "test-session"
        assert len(session.messages) == 0
        assert isinstance(session.created_at, datetime)
    
    def test_approval_request(self):
        """Test ApprovalRequest model."""
        request = ApprovalRequest(
            session_id="test-session",
            approved=True
        )
        
        assert request.session_id == "test-session"
        assert request.approved is True
    
    def test_approval_response(self):
        """Test ApprovalResponse model."""
        response = ApprovalResponse(
            session_id="test-session",
            approved=True,
            message="Changes approved"
        )
        
        assert response.session_id == "test-session"
        assert response.approved is True
        assert response.message == "Changes approved"
    
    def test_completion_request(self):
        """Test CompletionRequest model."""
        request = CompletionRequest(
            file_path="test.py",
            cursor_line=10,
            cursor_column=5,
            surrounding_code="def test():",
            language="python"
        )
        
        assert request.file_path == "test.py"
        assert request.cursor_line == 10
        assert request.language == "python"
    
    def test_completion_response(self):
        """Test CompletionResponse model."""
        response = CompletionResponse(
            suggestion="    pass",
            confidence=0.85
        )
        
        assert response.suggestion == "    pass"
        assert response.confidence == 0.85
    
    def test_diff_proposal(self):
        """Test DiffProposal model."""
        proposal = DiffProposal(
            diff="--- a/test.py\n+++ b/test.py",
            files_changed=["test.py"],
            additions=5,
            deletions=2,
            summary="Added logging"
        )
        
        assert "test.py" in proposal.files_changed
        assert proposal.additions == 5
        assert proposal.deletions == 2
    
    def test_attachment_upload(self):
        """Test AttachmentUpload model."""
        upload = AttachmentUpload(
            session_id="test-session",
            file_name="screenshot.png",
            file_type="image",
            content_base64="base64data"
        )
        
        assert upload.file_name == "screenshot.png"
        assert upload.file_type == "image"
    
    def test_suggestion_request(self):
        """Test SuggestionRequest model."""
        request = SuggestionRequest(
            current_input="explain",
            session_id="test-session"
        )
        
        assert request.current_input == "explain"
        assert request.session_id == "test-session"
    
    def test_suggestion_response(self):
        """Test SuggestionResponse model."""
        response = SuggestionResponse(
            suggestions=["Explain this code", "Explain this function"]
        )
        
        assert len(response.suggestions) == 2

