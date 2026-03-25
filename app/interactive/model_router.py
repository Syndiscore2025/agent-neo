"""
AGENT NEO - Model Router
Routes requests to appropriate LLM (Claude Sonnet, Claude Opus, GPT).
"""

import os
import logging
from typing import Optional, Literal
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Available model types."""
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT = "gpt"


class ModelRouter:
    """
    Routes requests to appropriate LLM.

    Strategy:
    - Default: Claude Sonnet (fast, cost-effective)
    - Complex tasks: Claude Opus (more capable)
    - Alternative/fallback: GPT
    """

    def __init__(self):
        """Initialize model router."""
        self.default_model = os.getenv("DEFAULT_MODEL", ModelType.CLAUDE_SONNET.value)
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # Initialize API clients
        self._anthropic_client = None
        self._openai_client = None

        if self.anthropic_api_key:
            try:
                from anthropic import Anthropic
                self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
                logger.info("Anthropic client initialized")
            except ImportError:
                logger.warning("anthropic package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")

        if self.openai_api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI client initialized")
            except ImportError:
                logger.warning("openai package not installed")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
    
    def select_model(
        self,
        task_complexity: Literal["simple", "complex"] = "simple",
        user_preference: Optional[str] = None
    ) -> ModelType:
        """
        Select appropriate model for task.
        
        Args:
            task_complexity: Complexity level
            user_preference: Optional user override
            
        Returns:
            Selected model type
        """
        # User preference takes priority
        if user_preference:
            try:
                return ModelType(user_preference)
            except ValueError:
                logger.warning(f"Invalid model preference: {user_preference}")
        
        # Default routing logic
        if task_complexity == "complex":
            return ModelType.CLAUDE_OPUS
        
        return ModelType(self.default_model)
    
    async def generate_response(
        self,
        prompt: str,
        model: Optional[ModelType] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate response from selected model.

        Args:
            prompt: Input prompt
            model: Model to use (defaults to Sonnet)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature

        Returns:
            Generated response text
        """
        if model is None:
            model = ModelType(self.default_model)

        logger.info(f"Generating response with {model.value}")

        try:
            if model in [ModelType.CLAUDE_SONNET, ModelType.CLAUDE_OPUS]:
                return await self._generate_anthropic_response(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            elif model == ModelType.GPT:
                return await self._generate_openai_response(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            else:
                raise ValueError(f"Unknown model type: {model}")
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    async def _generate_anthropic_response(
        self,
        prompt: str,
        model: ModelType,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using Anthropic API."""
        if not self._anthropic_client:
            raise ValueError("Anthropic client not initialized. Check ANTHROPIC_API_KEY.")

        # Map model type to Anthropic model name
        model_name = "claude-sonnet-4-20250514" if model == ModelType.CLAUDE_SONNET else "claude-opus-4-20250514"

        try:
            response = self._anthropic_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    async def _generate_openai_response(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using OpenAI API."""
        if not self._openai_client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY.")

        # Use o1 (reasoning model) or fallback to gpt-4o
        model_name = os.getenv("OPENAI_MODEL", "o1")

        # o1/o3 reasoning models use max_completion_tokens and don't support
        # the temperature parameter — use separate kwargs accordingly.
        is_reasoning_model = model_name.startswith(("o1", "o3"))

        create_kwargs: dict = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        if is_reasoning_model:
            create_kwargs["max_completion_tokens"] = max_tokens
            # temperature is not supported on reasoning models; omit it
        else:
            create_kwargs["max_tokens"] = max_tokens
            create_kwargs["temperature"] = temperature

        try:
            response = self._openai_client.chat.completions.create(**create_kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    async def generate_completion(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.3
    ) -> str:
        """
        Generate inline code completion (lightweight, fast).

        Args:
            prompt: Completion prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Completion suggestion
        """
        logger.info(f"Generating completion with max_tokens={max_tokens}")

        # Use GPT-4o for completions (faster than o1)
        # o1 is too slow for inline completions
        if self.openai_api_key:
            try:
                response = self._openai_client.chat.completions.create(
                    model="gpt-4o",  # Use fast model for completions
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"OpenAI completion error: {e}")
                return ""

        # Fallback to Claude if OpenAI not available
        if self.anthropic_api_key:
            try:
                response = self._anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text
            except Exception as e:
                logger.error(f"Anthropic completion error: {e}")
                return ""

        logger.warning("No API keys configured for completion")
        return ""
    
    async def generate_with_tools(
        self,
        system: str,
        messages: list,
        tools: list,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Generate a response with Anthropic native tool-use.

        Returns:
            {
                "text": str,          # concatenated text blocks
                "tool_calls": [       # list of tool call dicts
                    {"id": str, "name": str, "input": dict}
                ],
                "raw_content": list,  # raw content blocks (for multi-turn)
            }
        """
        if not self._anthropic_client:
            raise ValueError("Anthropic client not initialised. Check ANTHROPIC_API_KEY.")

        model_name = "claude-sonnet-4-20250514"
        response = self._anthropic_client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        raw_content = response.content   # list of ContentBlock objects

        for block in raw_content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        # Convert raw content to serialisable dicts for multi-turn messages
        raw_serialisable = []
        for block in raw_content:
            if block.type == "text":
                raw_serialisable.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                raw_serialisable.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return {
            "text": "\n".join(text_parts),
            "tool_calls": tool_calls,
            "raw_content": raw_serialisable,
        }

    def is_configured(self) -> bool:
        """Check if at least one model is configured."""
        return bool(self.anthropic_api_key or self.openai_api_key)
    
    def get_available_models(self) -> list[str]:
        """Get list of available/configured models."""
        available = []
        if self.anthropic_api_key:
            available.extend([ModelType.CLAUDE_SONNET.value, ModelType.CLAUDE_OPUS.value])
        if self.openai_api_key:
            available.append(ModelType.GPT.value)
        return available


# Global model router instance
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get global model router instance."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router

