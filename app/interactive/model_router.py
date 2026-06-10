"""
AGENT NEO - Model Router
Routes requests to the appropriate LLM provider (Anthropic or OpenAI).
Any model id is accepted: catalog aliases resolve to concrete API models,
and unknown ids pass through by prefix (claude* → Anthropic, gpt*/o* → OpenAI).
"""

import os
import logging
from typing import Optional, Literal
from enum import Enum

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    """Legacy model aliases (kept for back-compat)."""
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    GPT = "gpt"


# ── Model catalog ────────────────────────────────────────────────────────────
# Friendly id → provider + concrete API model id. Ids NOT in the catalog still
# work via prefix pass-through (claude* → Anthropic; gpt*/o1*/o3*/o4*/chatgpt*
# → OpenAI), so new provider models need no code change. Extra ids can be
# surfaced in the picker via NEO_ANTHROPIC_MODELS / NEO_OPENAI_MODELS.
MODEL_CATALOG: dict[str, dict] = {
    # Anthropic
    "claude-sonnet": {"provider": "anthropic", "api_model": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
    "claude-opus":   {"provider": "anthropic", "api_model": "claude-opus-4-20250514",   "label": "Claude Opus 4"},
    # OpenAI ("gpt" alias resolves to OPENAI_MODEL env, default o1)
    "gpt":    {"provider": "openai", "api_model": None,     "label": "GPT (OPENAI_MODEL)"},
    "gpt-4o": {"provider": "openai", "api_model": "gpt-4o", "label": "GPT-4o"},
    "o1":     {"provider": "openai", "api_model": "o1",     "label": "OpenAI o1"},
    "o3":     {"provider": "openai", "api_model": "o3",     "label": "OpenAI o3"},
}

_OPENAI_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")
_FALLBACK_MODEL = ("anthropic", "claude-sonnet-4-20250514")


def _extra_env_models() -> dict[str, dict]:
    """Extra catalog entries from NEO_ANTHROPIC_MODELS / NEO_OPENAI_MODELS (comma-separated ids)."""
    extras: dict[str, dict] = {}
    for env_var, provider in (("NEO_ANTHROPIC_MODELS", "anthropic"), ("NEO_OPENAI_MODELS", "openai")):
        for mid in os.getenv(env_var, "").split(","):
            mid = mid.strip()
            if mid and mid not in MODEL_CATALOG:
                extras[mid] = {"provider": provider, "api_model": mid, "label": mid}
    return extras


def resolve_model(model: Optional[str]) -> tuple[str, str]:
    """
    Resolve any model id to (provider, api_model).

    Order: catalog/env-extras hit → prefix pass-through. Empty/None resolves
    via DEFAULT_MODEL. Raises ValueError for unresolvable ids.
    """
    if not model:
        default = os.getenv("DEFAULT_MODEL", "").strip() or ModelType.CLAUDE_SONNET.value
        try:
            return resolve_model(default)
        except ValueError:
            logger.warning(f"DEFAULT_MODEL '{default}' is unresolvable; falling back to claude-sonnet")
            return _FALLBACK_MODEL

    model = str(model).strip()
    entry = MODEL_CATALOG.get(model) or _extra_env_models().get(model)
    if entry:
        return entry["provider"], entry["api_model"] or os.getenv("OPENAI_MODEL", "o1")

    lower = model.lower()
    if lower.startswith("claude"):
        return "anthropic", model
    if lower.startswith(_OPENAI_PREFIXES):
        return "openai", model

    raise ValueError(f"Cannot resolve model '{model}' to a provider")


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
    
    def _resolve_or_default(self, model: Optional[str]) -> tuple[str, str]:
        """Resolve a model id, falling back to the configured default on error."""
        try:
            return resolve_model(model)
        except ValueError:
            logger.warning(f"Invalid model '{model}'; falling back to default")
            return resolve_model(None)

    async def generate_response(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate response from the selected model.

        Args:
            prompt: Input prompt
            model: Any resolvable model id (defaults to DEFAULT_MODEL)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature

        Returns:
            Generated response text
        """
        provider, api_model = self._resolve_or_default(model)
        logger.info(f"Generating response with {provider}:{api_model}")

        try:
            if provider == "anthropic":
                return await self._generate_anthropic_response(
                    prompt=prompt,
                    api_model=api_model,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            return await self._generate_openai_response(
                prompt=prompt,
                api_model=api_model,
                max_tokens=max_tokens,
                temperature=temperature
            )
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            raise

    async def _generate_anthropic_response(
        self,
        prompt: str,
        api_model: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using Anthropic API."""
        if not self._anthropic_client:
            raise ValueError("Anthropic client not initialized. Check ANTHROPIC_API_KEY.")

        try:
            response = self._anthropic_client.messages.create(
                model=api_model,
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

    @staticmethod
    def _openai_token_kwargs(api_model: str, max_tokens: int, temperature: Optional[float] = None) -> dict:
        """Token/temperature kwargs — o1/o3/o4 reasoning models use
        max_completion_tokens and don't support temperature."""
        if api_model.lower().startswith(("o1", "o3", "o4")):
            return {"max_completion_tokens": max_tokens}
        kwargs: dict = {"max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature
        return kwargs

    async def _generate_openai_response(
        self,
        prompt: str,
        api_model: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate response using OpenAI API."""
        if not self._openai_client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY.")

        create_kwargs: dict = {
            "model": api_model,
            "messages": [{"role": "user", "content": prompt}],
            **self._openai_token_kwargs(api_model, max_tokens, temperature),
        }

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
    
    # ── Anthropic ⇄ OpenAI conversion helpers ────────────────────────────────

    @staticmethod
    def _tools_to_openai(tools: list) -> list:
        """Convert Anthropic tool schemas to OpenAI function-tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _messages_to_openai(system: str, messages: list) -> list:
        """Convert Anthropic-block message history to OpenAI chat format."""
        import json as _json

        oai: list = [{"role": "system", "content": system}]
        for msg in messages:
            role, content = msg["role"], msg["content"]
            if isinstance(content, str):
                oai.append({"role": role, "content": content})
                continue

            if role == "assistant":
                text_parts: list[str] = []
                tool_calls: list[dict] = []
                for block in content:
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": _json.dumps(block.get("input") or {}),
                            },
                        })
                entry: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                oai.append(entry)
            else:
                # user message blocks: tool_result and/or text
                text_parts = []
                for block in content:
                    btype = block.get("type")
                    if btype == "tool_result":
                        rc = block.get("content", "")
                        if isinstance(rc, list):
                            rc = "\n".join(
                                b.get("text", "") for b in rc if isinstance(b, dict)
                            )
                        oai.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": str(rc),
                        })
                    elif btype == "text":
                        text_parts.append(block.get("text", ""))
                if text_parts:
                    oai.append({"role": "user", "content": "\n".join(text_parts)})
        return oai

    async def _openai_generate_with_tools(
        self, system: str, messages: list, tools: list, max_tokens: int, api_model: str
    ) -> dict:
        """OpenAI tool-use generation; returns Anthropic-shaped result dict."""
        if not self._openai_client:
            raise ValueError("OpenAI client not initialised. Check OPENAI_API_KEY.")
        import json as _json

        response = self._openai_client.chat.completions.create(
            model=api_model,
            messages=self._messages_to_openai(system, messages),
            tools=self._tools_to_openai(tools),
            **self._openai_token_kwargs(api_model, max_tokens),
        )
        choice = response.choices[0].message
        text = choice.content or ""
        tool_calls: list[dict] = []
        raw_serialisable: list[dict] = []
        if text:
            raw_serialisable.append({"type": "text", "text": text})
        for tc in (choice.tool_calls or []):
            try:
                parsed = _json.loads(tc.function.arguments or "{}")
            except Exception:
                parsed = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "input": parsed})
            raw_serialisable.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": parsed,
            })
        return {"text": text, "tool_calls": tool_calls, "raw_content": raw_serialisable}

    async def _openai_stream_with_tools(
        self, system: str, messages: list, tools: list, max_tokens: int, api_model: str
    ):
        """OpenAI streaming tool-use; yields the same event vocabulary as Anthropic."""
        if not self._openai_client:
            yield {"type": "error", "error": "OpenAI client not initialised. Check OPENAI_API_KEY."}
            return
        import json as _json

        try:
            stream = self._openai_client.chat.completions.create(
                model=api_model,
                messages=self._messages_to_openai(system, messages),
                tools=self._tools_to_openai(tools),
                stream=True,
                **self._openai_token_kwargs(api_model, max_tokens),
            )
            pending: dict[int, dict] = {}  # index → {"id", "name", "args"}
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None:
                    continue
                if delta.content:
                    yield {"type": "text", "content": delta.content}
                for tc in (delta.tool_calls or []):
                    slot = pending.setdefault(tc.index, {"id": None, "name": None, "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name and slot["name"] is None:
                        slot["name"] = tc.function.name
                        yield {
                            "type": "tool_start",
                            "tool": slot["name"],
                            "id": slot["id"] or "",
                            "input": {},
                        }
                    if tc.function and tc.function.arguments:
                        slot["args"] += tc.function.arguments

            for idx in sorted(pending):
                slot = pending[idx]
                if not slot["name"]:
                    continue
                try:
                    parsed = _json.loads(slot["args"]) if slot["args"] else {}
                except Exception:
                    parsed = {}
                yield {
                    "type": "tool_ready",
                    "tool": slot["name"],
                    "id": slot["id"] or f"call_{idx}",
                    "input": parsed,
                }
            yield {"type": "done"}

        except Exception as exc:
            logger.error(f"_openai_stream_with_tools error: {exc}", exc_info=True)
            yield {"type": "error", "error": str(exc)}

    async def generate_with_tools(
        self,
        system: str,
        messages: list,
        tools: list,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> dict:
        """
        Generate a response with native tool-use (Anthropic or OpenAI).

        Returns:
            {
                "text": str,          # concatenated text blocks
                "tool_calls": [       # list of tool call dicts
                    {"id": str, "name": str, "input": dict}
                ],
                "raw_content": list,  # raw content blocks (for multi-turn)
            }
        """
        provider, api_model = self._resolve_or_default(model)
        if provider == "openai":
            return await self._openai_generate_with_tools(
                system, messages, tools, max_tokens, api_model
            )

        if not self._anthropic_client:
            raise ValueError("Anthropic client not initialised. Check ANTHROPIC_API_KEY.")

        response = self._anthropic_client.messages.create(
            model=api_model,
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

    async def stream_with_tools(
        self,
        system: str,
        messages: list,
        tools: list,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ):
        """
        Async generator — streams a tool-use response event by event
        (Anthropic or OpenAI, same event vocabulary).

        Yields dicts with 'type' field:
          {"type": "text",       "content": str}
          {"type": "tool_start", "tool": str, "id": str, "input": {}}
          {"type": "tool_ready", "tool": str, "id": str, "input": dict}
          {"type": "done"}
          {"type": "error",      "error": str}
        """
        provider, api_model = self._resolve_or_default(model)
        if provider == "openai":
            async for event in self._openai_stream_with_tools(
                system, messages, tools, max_tokens, api_model
            ):
                yield event
            return

        if not self._anthropic_client:
            yield {"type": "error", "error": "Anthropic client not initialised. Check ANTHROPIC_API_KEY."}
            return

        try:
            import anthropic as _ant
            with self._anthropic_client.messages.stream(
                model=api_model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            ) as stream:
                current_tool_id: str | None = None
                current_tool_name: str | None = None
                current_tool_json: str = ""

                for event in stream:
                    etype = type(event).__name__

                    if etype == "RawContentBlockStartEvent":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_id = block.id
                            current_tool_name = block.name
                            current_tool_json = ""
                            yield {"type": "tool_start", "tool": block.name, "id": block.id, "input": {}}

                    elif etype == "RawContentBlockDeltaEvent":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield {"type": "text", "content": delta.text}
                        elif delta.type == "input_json_delta":
                            current_tool_json += delta.partial_json

                    elif etype == "RawContentBlockStopEvent":
                        if current_tool_name:
                            import json as _json
                            try:
                                parsed_input = _json.loads(current_tool_json) if current_tool_json else {}
                            except Exception:
                                parsed_input = {}
                            yield {
                                "type": "tool_ready",
                                "tool": current_tool_name,
                                "id": current_tool_id,
                                "input": parsed_input,
                            }
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_json = ""

                yield {"type": "done"}

        except Exception as exc:
            logger.error(f"stream_with_tools error: {exc}", exc_info=True)
            yield {"type": "error", "error": str(exc)}

    def is_configured(self) -> bool:
        """Check if at least one model is configured."""
        return bool(self.anthropic_api_key or self.openai_api_key)
    
    def _configured_catalog(self) -> dict[str, dict]:
        """Catalog (built-ins + env extras + discovered) filtered to configured providers."""
        from app.interactive.model_pricing import get_discovered_models

        catalog = {**MODEL_CATALOG, **_extra_env_models()}
        known_api = {e["api_model"] for e in catalog.values() if e["api_model"]}
        for provider in ("anthropic", "openai"):
            for m in get_discovered_models(provider):
                if m["id"] not in catalog and m["id"] not in known_api:
                    catalog[m["id"]] = {"provider": provider, "api_model": m["id"], "label": m["label"]}
        return {
            mid: entry for mid, entry in catalog.items()
            if (entry["provider"] == "anthropic" and self.anthropic_api_key)
            or (entry["provider"] == "openai" and self.openai_api_key)
        }

    def get_available_models(self) -> list[str]:
        """Get list of available/configured model ids."""
        return list(self._configured_catalog().keys())

    def get_model_catalog(self) -> list[dict]:
        """Get available models with metadata: [{id, label, provider, input/output_per_mtok}]."""
        from app.interactive.model_pricing import get_pricing

        out = []
        for mid, entry in self._configured_catalog().items():
            api_model = entry["api_model"] or os.getenv("OPENAI_MODEL", "o1")
            price = get_pricing(api_model) or {}
            out.append({
                "id": mid,
                "label": entry["label"],
                "provider": entry["provider"],
                "input_per_mtok": price.get("input_per_mtok"),
                "output_per_mtok": price.get("output_per_mtok"),
            })
        return out


# Global model router instance
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get global model router instance."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router

