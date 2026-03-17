"""
AGENT NEO - Suggestion Engine
Generates predictive prompt suggestions when user pauses typing.
"""

import logging
from typing import List, Optional

from app.interactive.contracts import SuggestionRequest, SuggestionResponse, ChatContext

logger = logging.getLogger(__name__)


class SuggestionEngine:
    """
    Generates contextual prompt suggestions.
    
    Triggered when user pauses typing in chat input.
    """
    
    def __init__(self):
        """Initialize suggestion engine."""
        pass
    
    async def generate_suggestions(
        self,
        request: SuggestionRequest
    ) -> SuggestionResponse:
        """
        Generate prompt suggestions.
        
        Args:
            request: Suggestion request
            
        Returns:
            List of suggested prompts
            
        TODO: Implement in SLICE 8
        """
        logger.info(f"Generating suggestions for input: {request.current_input[:50]}")
        
        suggestions = self._get_contextual_suggestions(
            current_input=request.current_input,
            context=request.context
        )
        
        return SuggestionResponse(suggestions=suggestions)
    
    def _get_contextual_suggestions(
        self,
        current_input: str,
        context: Optional[ChatContext]
    ) -> List[str]:
        """
        Get contextual suggestions based on input and context.
        
        Args:
            current_input: Current user input
            context: Chat context
            
        Returns:
            List of suggested prompts
            
        TODO: Implement smart suggestions in SLICE 8
        """
        suggestions = []
        
        # Default suggestions if no input
        if not current_input or len(current_input) < 3:
            suggestions = self._get_default_suggestions(context)
        else:
            # Context-aware suggestions based on partial input
            suggestions = self._get_input_based_suggestions(current_input, context)
        
        return suggestions[:5]  # Limit to 5 suggestions
    
    def _get_default_suggestions(self, context: Optional[ChatContext]) -> List[str]:
        """
        Get default suggestions when no input.
        
        Args:
            context: Chat context
            
        Returns:
            List of default prompts
        """
        suggestions = []
        
        if context and context.selected_code:
            suggestions.extend([
                "Explain this code",
                "Refactor this function",
                "Add error handling",
                "Generate tests for this",
                "Add logging to this"
            ])
        elif context and context.current_file:
            suggestions.extend([
                "Explain this file",
                "Add tests for this file",
                "Refactor this file",
                "Add documentation",
                "Find potential bugs"
            ])
        else:
            suggestions.extend([
                "Show repository overview",
                "List all test files",
                "Find TODO comments",
                "Show recent changes",
                "Explain the architecture"
            ])
        
        return suggestions
    
    def _get_input_based_suggestions(
        self,
        current_input: str,
        context: Optional[ChatContext]
    ) -> List[str]:
        """
        Get suggestions based on partial input.
        
        Args:
            current_input: Partial user input
            context: Chat context
            
        Returns:
            List of contextual prompts
            
        TODO: Implement smarter matching in SLICE 8
        """
        input_lower = current_input.lower()
        suggestions = []
        
        # Simple keyword matching for MVP
        if "explain" in input_lower:
            suggestions.extend([
                "Explain this code",
                "Explain this function",
                "Explain the architecture"
            ])
        elif "add" in input_lower or "create" in input_lower:
            suggestions.extend([
                "Add logging to this file",
                "Add error handling",
                "Add tests for this",
                "Create a new function"
            ])
        elif "fix" in input_lower:
            suggestions.extend([
                "Fix this error",
                "Fix this bug",
                "Fix the failing test"
            ])
        elif "refactor" in input_lower:
            suggestions.extend([
                "Refactor this function",
                "Refactor this file",
                "Refactor for better readability"
            ])
        
        return suggestions


# Global suggestion engine instance
_suggestion_engine: Optional[SuggestionEngine] = None


def get_suggestion_engine() -> SuggestionEngine:
    """Get global suggestion engine instance."""
    global _suggestion_engine
    if _suggestion_engine is None:
        _suggestion_engine = SuggestionEngine()
    return _suggestion_engine

