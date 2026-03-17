"""
Tests for interactive session manager.
"""

import pytest
from app.interactive.session_manager import SessionManager, get_session_manager
from app.interactive.contracts import ChatMessage, ChatContext, ExecutionResultCard


class TestSessionManager:
    """Test session manager functionality."""
    
    def test_create_session(self):
        """Test creating a new session."""
        manager = SessionManager()
        session_id = manager.create_session()
        
        assert session_id is not None
        assert len(session_id) > 0
        
        session = manager.get_session(session_id)
        assert session is not None
        assert session.session_id == session_id
        assert len(session.messages) == 0
    
    def test_create_session_with_context(self):
        """Test creating session with initial context."""
        manager = SessionManager()
        context = ChatContext(
            current_file="test.py",
            language="python"
        )
        
        session_id = manager.create_session(context)
        session = manager.get_session(session_id)
        
        assert session.context is not None
        assert session.context.current_file == "test.py"
        assert session.context.language == "python"
    
    def test_add_message(self):
        """Test adding messages to session."""
        manager = SessionManager()
        session_id = manager.create_session()
        
        message = ChatMessage(
            role="user",
            content="Hello"
        )
        
        success = manager.add_message(session_id, message)
        assert success is True
        
        session = manager.get_session(session_id)
        assert len(session.messages) == 1
        assert session.messages[0].content == "Hello"
    
    def test_add_message_invalid_session(self):
        """Test adding message to non-existent session."""
        manager = SessionManager()
        message = ChatMessage(role="user", content="Hello")
        
        success = manager.add_message("invalid-id", message)
        assert success is False
    
    def test_set_and_get_proposed_diff(self):
        """Test storing and retrieving proposed diff."""
        manager = SessionManager()
        session_id = manager.create_session()
        
        diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new"
        
        success = manager.set_proposed_diff(session_id, diff)
        assert success is True
        
        retrieved_diff = manager.get_proposed_diff(session_id)
        assert retrieved_diff == diff
    
    def test_clear_proposed_diff(self):
        """Test clearing proposed diff."""
        manager = SessionManager()
        session_id = manager.create_session()
        
        diff = "--- a/test.py\n+++ b/test.py"
        manager.set_proposed_diff(session_id, diff)
        
        success = manager.clear_proposed_diff(session_id)
        assert success is True
        
        retrieved_diff = manager.get_proposed_diff(session_id)
        assert retrieved_diff is None
    
    def test_delete_session(self):
        """Test deleting a session."""
        manager = SessionManager()
        session_id = manager.create_session()
        
        deleted = manager.delete_session(session_id)
        assert deleted is True
        
        session = manager.get_session(session_id)
        assert session is None
    
    def test_delete_nonexistent_session(self):
        """Test deleting non-existent session."""
        manager = SessionManager()
        deleted = manager.delete_session("invalid-id")
        assert deleted is False
    
    def test_get_session_count(self):
        """Test getting session count."""
        manager = SessionManager()
        
        assert manager.get_session_count() == 0
        
        manager.create_session()
        assert manager.get_session_count() == 1
        
        manager.create_session()
        assert manager.get_session_count() == 2
    
    def test_global_session_manager(self):
        """Test global session manager singleton."""
        manager1 = get_session_manager()
        manager2 = get_session_manager()

        assert manager1 is manager2

    # ------------------------------------------------------------------
    # Wave 2 — last_execution persistence
    # ------------------------------------------------------------------
    def test_set_and_get_last_execution(self):
        """Test storing and retrieving the last execution result card."""
        manager = SessionManager()
        session_id = manager.create_session()

        card = ExecutionResultCard(
            status="Working",
            mode="CRITICAL",
            commit_sha="abc12345",
            files_changed=["app/main.py"],
        )
        result = manager.set_last_execution(session_id, card)
        assert result is True

        retrieved = manager.get_last_execution(session_id)
        assert retrieved is not None
        assert retrieved.commit_sha == "abc12345"
        assert retrieved.status == "Working"
        assert "app/main.py" in retrieved.files_changed

    def test_get_last_execution_no_execution(self):
        """Test get_last_execution returns None when nothing has been stored."""
        manager = SessionManager()
        session_id = manager.create_session()

        result = manager.get_last_execution(session_id)
        assert result is None

    def test_set_last_execution_invalid_session(self):
        """Test set_last_execution returns False for unknown session."""
        manager = SessionManager()
        card = ExecutionResultCard(status="Working", mode="CRITICAL")
        result = manager.set_last_execution("nonexistent-session", card)
        assert result is False

    def test_get_last_execution_invalid_session(self):
        """Test get_last_execution returns None for unknown session."""
        manager = SessionManager()
        result = manager.get_last_execution("nonexistent-session")
        assert result is None

    def test_set_last_execution_overwrites_previous(self):
        """Test that set_last_execution replaces the previous value."""
        manager = SessionManager()
        session_id = manager.create_session()

        card1 = ExecutionResultCard(status="Working", mode="CRITICAL", commit_sha="first-sha")
        card2 = ExecutionResultCard(status="Broken", mode="CRITICAL", commit_sha="second-sha")

        manager.set_last_execution(session_id, card1)
        manager.set_last_execution(session_id, card2)

        retrieved = manager.get_last_execution(session_id)
        assert retrieved.commit_sha == "second-sha"
        assert retrieved.status == "Broken"

