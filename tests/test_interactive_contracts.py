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
    ActionType,
    ExecutionResultCard,
    SummarizeRequest,
    SessionSummaryResponse,
    RollbackRequest,
    RollbackResponse,
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

    # ------------------------------------------------------------------
    # Wave 2 — new contract models
    # ------------------------------------------------------------------
    def test_execution_result_card_minimal(self):
        """Test ExecutionResultCard with minimal fields."""
        card = ExecutionResultCard(status="Working", mode="CRITICAL")
        assert card.status == "Working"
        assert card.mode == "CRITICAL"
        assert card.commit_sha is None
        assert card.files_changed == []
        assert card.lines_changed == 0
        assert card.pushed is False
        assert card.verify_steps == []
        assert card.error is None

    def test_execution_result_card_full(self):
        """Test ExecutionResultCard with all fields."""
        card = ExecutionResultCard(
            status="Broken",
            mode="CRITICAL",
            commit_sha="abc123def456",
            files_changed=["app/main.py", "app/core.py"],
            lines_changed=42,
            pushed=True,
            verify_steps=["pytest passed", "lint clean"],
            rollback_command="git revert abc123def456",
            pre_test_passed=True,
            post_test_passed=False,
            validation_passed=True,
            error="Post-test failure",
        )
        assert card.commit_sha == "abc123def456"
        assert len(card.files_changed) == 2
        assert card.lines_changed == 42
        assert card.pushed is True
        assert card.pre_test_passed is True
        assert card.post_test_passed is False
        assert card.error == "Post-test failure"

    def test_summarize_request(self):
        """Test SummarizeRequest model."""
        req = SummarizeRequest(session_id="sess-abc")
        assert req.session_id == "sess-abc"

    def test_session_summary_response(self):
        """Test SessionSummaryResponse model."""
        resp = SessionSummaryResponse(
            old_session_id="old-123",
            new_session_id="new-456",
            summary="The developer fixed a bug in the parser.",
            message_count_was=25,
        )
        assert resp.old_session_id == "old-123"
        assert resp.new_session_id == "new-456"
        assert resp.message_count_was == 25
        assert "parser" in resp.summary

    def test_rollback_request(self):
        """Test RollbackRequest model."""
        req = RollbackRequest(session_id="sess-xyz")
        assert req.session_id == "sess-xyz"

    def test_rollback_response_success(self):
        """Test RollbackResponse on success."""
        resp = RollbackResponse(
            session_id="sess-xyz",
            success=True,
            message="✓ Rolled back commit abc12345.",
            commit_reverted="abc12345",
        )
        assert resp.success is True
        assert resp.commit_reverted == "abc12345"

    def test_rollback_response_failure(self):
        """Test RollbackResponse on failure."""
        resp = RollbackResponse(
            session_id="sess-xyz",
            success=False,
            message="No previous execution found.",
        )
        assert resp.success is False
        assert resp.commit_reverted is None

    def test_chat_session_stores_last_execution(self):
        """Test that ChatSession accepts and stores last_execution."""
        card = ExecutionResultCard(status="Working", mode="CRITICAL", commit_sha="deadbeef")
        session = ChatSession(session_id="test-sess", last_execution=card)
        assert session.last_execution is not None
        assert session.last_execution.commit_sha == "deadbeef"

    def test_approval_response_uses_execution_result_card(self):
        """Test ApprovalResponse.execution_result is typed as ExecutionResultCard."""
        card = ExecutionResultCard(status="Working", mode="CRITICAL")
        resp = ApprovalResponse(
            session_id="s1",
            approved=True,
            message="Applied.",
            execution_result=card,
        )
        assert isinstance(resp.execution_result, ExecutionResultCard)
        assert resp.execution_result.status == "Working"

