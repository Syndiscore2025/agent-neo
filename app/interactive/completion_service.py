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
        """
        logger.info(f"Generating completion for {request.file_path}:{request.cursor_line}")

        try:
            # Build lightweight prompt
            prompt = self.build_completion_prompt(request)

            # Call model with low max_tokens for speed
            # Use a fast model (GPT-4o or similar)
            response = await self.model_router.generate_completion(
                prompt=prompt,
                max_tokens=100,  # Keep it short for speed
                temperature=0.3  # Lower temperature for more deterministic completions
            )

            # Extract suggestion from response
            suggestion = self._extract_suggestion(response, request)

            # Calculate confidence (simple heuristic for now)
            confidence = self._calculate_confidence(suggestion, request)

            logger.info(f"Generated completion: {len(suggestion)} chars, confidence={confidence:.2f}")

            return CompletionResponse(
                suggestion=suggestion,
                confidence=confidence
            )

        except Exception as e:
            logger.error(f"Completion generation failed: {e}", exc_info=True)
            # Return empty suggestion on error
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
        """
        language = request.language or "code"

        prompt = f"""You are an expert {language} programmer. Complete the code at the cursor position.

File: {request.file_path}
Language: {language}

Code context:
```{language}
{request.surrounding_code}
```

Provide ONLY the completion text that should appear after the cursor. Do not repeat existing code.
Keep the completion concise and contextually appropriate.
Do not include explanations or markdown formatting."""

        return prompt

    def _extract_suggestion(self, response: str, request: CompletionRequest) -> str:
        """
        Extract completion suggestion from model response.

        Args:
            response: Raw model response
            request: Original request

        Returns:
            Cleaned suggestion text
        """
        if not response:
            return ""

        # Remove markdown code blocks if present
        suggestion = response.strip()
        if suggestion.startswith("```"):
            lines = suggestion.split("\n")
            # Remove first line (```language) and last line (```)
            if len(lines) > 2:
                suggestion = "\n".join(lines[1:-1])

        # Trim to reasonable length (max 3 lines for inline completion)
        lines = suggestion.split("\n")
        if len(lines) > 3:
            suggestion = "\n".join(lines[:3])

        return suggestion.strip()

    def _calculate_confidence(self, suggestion: str, request: CompletionRequest) -> float:
        """
        Calculate confidence score for suggestion.

        Args:
            suggestion: Generated suggestion
            request: Original request

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not suggestion:
            return 0.0

        # Simple heuristic-based confidence
        confidence = 0.5  # Base confidence

        # Boost confidence if suggestion is short and focused
        if len(suggestion) < 100:
            confidence += 0.2

        # Boost confidence if suggestion doesn't have obvious errors
        if not any(marker in suggestion.lower() for marker in ["error", "todo", "fixme", "???"]):
            confidence += 0.2

        # Reduce confidence if suggestion is very long
        if len(suggestion) > 200:
            confidence -= 0.3

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, confidence))


# Global completion service instance
_completion_service: Optional[CompletionService] = None


def get_completion_service() -> CompletionService:
    """Get global completion service instance."""
    global _completion_service
    if _completion_service is None:
        _completion_service = CompletionService()
    return _completion_service

