"""
AGENT NEO - Session Manager
Manages chat session state for interactive conversations.
"""

import uuid
from typing import Dict, Optional
from datetime import datetime

from app.interactive.contracts import ChatSession, ChatMessage, ChatContext


class SessionManager:
    """
    Manages chat sessions.
    
    For personal use, simple in-memory storage is sufficient.
    """
    
    def __init__(self):
        """Initialize session manager."""
        self._sessions: Dict[str, ChatSession] = {}
    
    def create_session(self, context: Optional[ChatContext] = None) -> str:
        """
        Create a new chat session.
        
        Args:
            context: Optional initial context
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        session = ChatSession(
            session_id=session_id,
            messages=[],
            context=context
        )
        self._sessions[session_id] = session
        return session_id
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Get session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            ChatSession or None if not found
        """
        return self._sessions.get(session_id)
    
    def add_message(self, session_id: str, message: ChatMessage) -> bool:
        """
        Add message to session.
        
        Args:
            session_id: Session ID
            message: Message to add
            
        Returns:
            True if successful, False if session not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.messages.append(message)
        session.updated_at = datetime.utcnow()
        return True
    
    def set_proposed_diff(self, session_id: str, diff: str) -> bool:
        """
        Store proposed diff in session.
        
        Args:
            session_id: Session ID
            diff: Unified diff string
            
        Returns:
            True if successful, False if session not found
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.proposed_diff = diff
        session.updated_at = datetime.utcnow()
        return True
    
    def get_proposed_diff(self, session_id: str) -> Optional[str]:
        """
        Get proposed diff from session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Diff string or None
        """
        session = self.get_session(session_id)
        if not session:
            return None
        return session.proposed_diff
    
    def clear_proposed_diff(self, session_id: str) -> bool:
        """
        Clear proposed diff from session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if successful
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.proposed_diff = None
        session.updated_at = datetime.utcnow()
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if deleted, False if not found
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def get_session_count(self) -> int:
        """Get total number of active sessions."""
        return len(self._sessions)


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get global session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

