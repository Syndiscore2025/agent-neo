"""
AGENT NEO - Completion Service
Lightweight inline code completion (separate from governed execution).
"""

import logging
from typing import Optional

from app.interactive.contracts import CompletionRequest, CompletionResponse
from app.interactive.model_router import get_model_router

logger = logging.getLogger(__name__)


class CompletionService:
    """
    Provides inline code completion suggestions.
    
    This is a separate, lightweight path from the full execution pipeline.
    No tests, no approval, no governance - just fast suggestions.
    """
    
    def __init__(self):
        """Initialize completion service."""
        self.model_router = get_model_router()
    
    async def generate_completion(
        self,
        request: CompletionRequest
    ) -> CompletionResponse:
        """
        Generate inline completion suggestion.
        
        Args:
            request: Completion request
            
        Returns:
            Completion response with suggestion
            
        TODO: Implement in SLICE 7
        """
        logger.info(f"Generating completion for {request.file_path}:{request.cursor_line}")
        
        # Placeholder implementation
        # TODO: Implement actual completion logic in SLICE 7
        # This should:
        # 1. Build lightweight prompt from surrounding code
        # 2. Call model with low max_tokens
        # 3. Parse and return suggestion
        # 4. Be FAST (< 1 second ideally)
        
        return CompletionResponse(
            suggestion="",
            confidence=0.0
        )
    
    def build_completion_prompt(self, request: CompletionRequest) -> str:
        """
        Build prompt for completion request.
        
        Args:
            request: Completion request
            
        Returns:
            Formatted prompt
            
        TODO: Implement in SLICE 7
        """
        # Placeholder
        return f"Complete the following {request.language} code:\n\n{request.surrounding_code}"


# Global completion service instance
_completion_service: Optional[CompletionService] = None


def get_completion_service() -> CompletionService:
    """Get global completion service instance."""
    global _completion_service
    if _completion_service is None:
        _completion_service = CompletionService()
    return _completion_service

