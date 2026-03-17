"""
AGENT NEO - Suggestion Engine
Generates predictive prompt suggestions when user pauses typing.
Uses GPT-4o-mini for low-latency, context-aware suggestions; falls back
to keyword matching when no API key is available.
"""

import json
import logging
from typing import List, Optional

from app.interactive.contracts import SuggestionRequest, SuggestionResponse, ChatContext

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 5


class SuggestionEngine:
    """
    Generates contextual prompt suggestions.

    Triggered when the user pauses typing in the chat input.
    """

    def __init__(self):
        """Initialize suggestion engine."""
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_suggestions(
        self,
        request: SuggestionRequest
    ) -> SuggestionResponse:
        """
        Generate prompt suggestions using LLM (with keyword fallback).

        Args:
            request: Suggestion request

        Returns:
            SuggestionResponse with up to 5 prompt suggestions
        """
        logger.info(f"Generating suggestions for input: '{request.current_input[:60]}'")

        try:
            suggestions = await self._get_llm_suggestions(request)
            return SuggestionResponse(suggestions=suggestions)
        except Exception as exc:
            logger.warning(f"LLM suggestions unavailable ({exc}), using fallback")
            suggestions = self._get_contextual_suggestions(
                current_input=request.current_input,
                context=request.context,
            )
            return SuggestionResponse(suggestions=suggestions)

    # ------------------------------------------------------------------
    # LLM-backed path
    # ------------------------------------------------------------------

    async def _get_llm_suggestions(self, request: SuggestionRequest) -> List[str]:
        """
        Ask GPT-4o-mini to produce contextual follow-up suggestions.

        Args:
            request: Suggestion request including optional session_id

        Returns:
            List of suggestion strings

        Raises:
            Exception if no API key or network failure (caller falls back)
        """
        import os
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        # Build recent-conversation snippet if a session is available
        session_snippet = ""
        if request.session_id:
            try:
                from app.interactive.session_manager import get_session_manager
                session = get_session_manager().get_session(request.session_id)
                if session and session.messages:
                    recent = session.messages[-6:]  # last 3 exchanges
                    session_snippet = "\n".join(
                        f"{m.role}: {m.content[:120]}" for m in recent
                    )
            except Exception as exc:
                logger.debug(f"Could not load session history for suggestions: {exc}")

        # Build context hint
        context_hint = ""
        if request.context:
            ctx = request.context
            if ctx.current_file:
                context_hint += f"Current file: {ctx.current_file}\n"
            if ctx.language:
                context_hint += f"Language: {ctx.language}\n"
            if ctx.selected_code:
                context_hint += f"Selected code snippet:\n{ctx.selected_code[:300]}\n"

        prompt = (
            "You are an AI coding assistant. "
            "Generate 3-5 concise, actionable follow-up prompt suggestions "
            "a developer might want to type next.\n\n"
            f"Partial user input: \"{request.current_input}\"\n"
        )
        if context_hint:
            prompt += f"\nEditor context:\n{context_hint}"
        if session_snippet:
            prompt += f"\nRecent conversation:\n{session_snippet}\n"
        prompt += (
            "\nReturn ONLY a JSON array of strings. "
            "Example: [\"Explain this code\", \"Add error handling\"]\n"
            "Suggestions:"
        )

        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        suggestions: List[str] = json.loads(raw)
        return suggestions[:_MAX_SUGGESTIONS]
    
    # ------------------------------------------------------------------
    # Keyword-based fallback path
    # ------------------------------------------------------------------

    def _get_contextual_suggestions(
        self,
        current_input: str,
        context: Optional[ChatContext],
    ) -> List[str]:
        """
        Keyword-based suggestion fallback (no API key required).

        Args:
            current_input: Current user input
            context: Chat context

        Returns:
            List of suggested prompts
        """
        if not current_input or len(current_input) < 3:
            return self._get_default_suggestions(context)
        return self._get_input_based_suggestions(current_input, context)
    
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
        context: Optional[ChatContext],
    ) -> List[str]:
        """
        Get suggestions based on keyword matching in partial input.

        Args:
            current_input: Partial user input
            context: Chat context

        Returns:
            List of contextual prompts
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

