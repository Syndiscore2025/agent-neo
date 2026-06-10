"""
Tests for interactive model router.
"""

import pytest
from app.interactive.model_router import (
    ModelRouter,
    ModelType,
    get_model_router,
    resolve_model,
)


class TestModelRouter:
    """Test model router functionality."""
    
    def test_initialization(self):
        """Test router initialization."""
        router = ModelRouter()
        assert router is not None
        assert router.default_model is not None
    
    def test_select_model_default(self):
        """Test default model selection."""
        router = ModelRouter()
        model = router.select_model()
        
        assert model in [ModelType.CLAUDE_SONNET, ModelType.CLAUDE_OPUS, ModelType.GPT]
    
    def test_select_model_simple_task(self):
        """Test model selection for simple task."""
        router = ModelRouter()
        model = router.select_model(task_complexity="simple")
        
        # Simple tasks should use default (likely Sonnet)
        assert model is not None
    
    def test_select_model_complex_task(self):
        """Test model selection for complex task."""
        router = ModelRouter()
        model = router.select_model(task_complexity="complex")
        
        # Complex tasks should use Opus
        assert model == ModelType.CLAUDE_OPUS
    
    def test_select_model_user_preference(self):
        """Test model selection with user preference."""
        router = ModelRouter()
        model = router.select_model(user_preference="gpt")
        
        assert model == ModelType.GPT
    
    def test_select_model_invalid_preference(self):
        """Test model selection with invalid preference."""
        router = ModelRouter()
        model = router.select_model(user_preference="invalid-model")
        
        # Should fall back to default
        assert model is not None
    
    @pytest.mark.asyncio
    async def test_generate_response_placeholder(self):
        """Test response generation (requires API key)."""
        router = ModelRouter()

        # Skip if no API keys configured
        if not router._anthropic_client and not router._openai_client:
            pytest.skip("No LLM API clients initialized - API keys not configured")
            return

        try:
            response = await router.generate_response("Test prompt")

            # Should return a string
            assert isinstance(response, str)
            assert len(response) > 0
        except ValueError as e:
            if "not initialized" in str(e):
                pytest.skip("API client not initialized")
            else:
                raise
    
    @pytest.mark.asyncio
    async def test_generate_completion_placeholder(self):
        """Test completion generation."""
        router = ModelRouter()
        completion = await router.generate_completion(
            prompt="Complete this Python code: def test():",
            max_tokens=50,
            temperature=0.3
        )

        # Returns empty string if no API keys configured
        assert isinstance(completion, str)
    
    def test_is_configured(self):
        """Test configuration check."""
        router = ModelRouter()
        # May or may not be configured depending on env
        result = router.is_configured()
        assert isinstance(result, bool)
    
    def test_get_available_models(self):
        """Test getting available models."""
        router = ModelRouter()
        models = router.get_available_models()
        
        assert isinstance(models, list)
        # May be empty if no API keys configured
    
    def test_global_model_router(self):
        """Test global model router singleton."""
        router1 = get_model_router()
        router2 = get_model_router()

        assert router1 is router2


class TestResolveModel:
    """Test wide-open model id resolution."""

    def test_catalog_aliases(self):
        assert resolve_model("claude-sonnet") == ("anthropic", "claude-sonnet-4-20250514")
        assert resolve_model("claude-opus") == ("anthropic", "claude-opus-4-20250514")
        assert resolve_model("gpt-4o") == ("openai", "gpt-4o")

    def test_gpt_alias_uses_openai_model_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
        assert resolve_model("gpt") == ("openai", "gpt-4.1")
        monkeypatch.delenv("OPENAI_MODEL")
        assert resolve_model("gpt") == ("openai", "o1")

    def test_prefix_passthrough(self):
        """Unknown ids route by prefix — no hardcoded model lock-in."""
        assert resolve_model("claude-haiku-99-20990101") == ("anthropic", "claude-haiku-99-20990101")
        assert resolve_model("gpt-7-turbo") == ("openai", "gpt-7-turbo")
        assert resolve_model("o4-mini") == ("openai", "o4-mini")
        assert resolve_model("chatgpt-4o-latest") == ("openai", "chatgpt-4o-latest")

    def test_unresolvable_raises(self):
        with pytest.raises(ValueError):
            resolve_model("llama-3-70b")

    def test_none_uses_default_model_env(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4o")
        assert resolve_model(None) == ("openai", "gpt-4o")

    def test_bad_default_falls_back_to_sonnet(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_MODEL", "not-a-model")
        assert resolve_model(None) == ("anthropic", "claude-sonnet-4-20250514")

    def test_env_extra_models_in_catalog(self, monkeypatch):
        monkeypatch.setenv("NEO_OPENAI_MODELS", "my-fine-tune-1")
        assert resolve_model("my-fine-tune-1") == ("openai", "my-fine-tune-1")

    def test_router_fallback_on_invalid(self):
        router = ModelRouter()
        provider, api_model = router._resolve_or_default("invalid-model")
        assert provider in ("anthropic", "openai")
        assert api_model

    def test_get_model_catalog_shape(self):
        router = ModelRouter()
        catalog = router.get_model_catalog()
        assert isinstance(catalog, list)
        for entry in catalog:
            assert set(entry.keys()) == {
                "id", "label", "provider", "input_per_mtok", "output_per_mtok"
            }

    def test_messages_to_openai_roundtrip_shapes(self):
        """Anthropic-block history converts to valid OpenAI chat format."""
        messages = [
            {"role": "user", "content": "do the task"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "reading file"},
                {"type": "tool_use", "id": "tc_1", "name": "read_file", "input": {"path": "a.py"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tc_1", "content": "file contents"},
            ]},
        ]
        oai = ModelRouter._messages_to_openai("sys prompt", messages)
        assert oai[0] == {"role": "system", "content": "sys prompt"}
        assert oai[1] == {"role": "user", "content": "do the task"}
        assert oai[2]["role"] == "assistant"
        assert oai[2]["tool_calls"][0]["id"] == "tc_1"
        assert oai[2]["tool_calls"][0]["function"]["name"] == "read_file"
        assert oai[3] == {"role": "tool", "tool_call_id": "tc_1", "content": "file contents"}

    def test_tools_to_openai_shape(self):
        tools = [{"name": "read_file", "description": "Read a file", "input_schema": {"type": "object", "properties": {}}}]
        oai = ModelRouter._tools_to_openai(tools)
        assert oai[0]["type"] == "function"
        assert oai[0]["function"]["name"] == "read_file"
        assert oai[0]["function"]["parameters"] == {"type": "object", "properties": {}}


class TestModelPricing:
    """Test pricing/discovery cache (app.interactive.model_pricing)."""

    @pytest.fixture(autouse=True)
    def _isolated_cache(self, tmp_path, monkeypatch):
        """Point the cache at an empty temp file and reset in-memory state."""
        from app.interactive import model_pricing
        monkeypatch.setenv("NEO_PRICING_CACHE", str(tmp_path / "pricing.json"))
        monkeypatch.setattr(model_pricing, "_cache", None)
        yield
        model_pricing._cache = None

    def test_fallback_pricing_when_no_cache(self):
        from app.interactive.model_pricing import get_pricing
        price = get_pricing("claude-sonnet-4-20250514")
        assert price == {"input_per_mtok": 3.0, "output_per_mtok": 15.0}
        assert get_pricing("unknown-model-xyz") is None
        assert get_pricing("") is None

    def test_parse_litellm_pricing(self):
        from app.interactive.model_pricing import _parse_litellm_pricing
        data = {
            "claude-sonnet-4-20250514": {
                "litellm_provider": "anthropic",
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
            },
            "openai/gpt-4o": {
                "litellm_provider": "openai",
                "input_cost_per_token": 0.0000025,
                "output_cost_per_token": 0.00001,
            },
            "gemini-pro": {"litellm_provider": "vertex_ai", "input_cost_per_token": 1e-6},
            "sample_spec": "not a dict",
        }
        parsed = _parse_litellm_pricing(data)
        assert parsed["claude-sonnet-4-20250514"] == {"input_per_mtok": 3.0, "output_per_mtok": 15.0}
        assert parsed["gpt-4o"] == {"input_per_mtok": 2.5, "output_per_mtok": 10.0}
        assert "gemini-pro" not in parsed

    def test_parse_openai_models_filters(self):
        from app.interactive.model_pricing import _parse_openai_models
        data = {"data": [
            {"id": "gpt-4o"},
            {"id": "gpt-4o-2024-05-13"},      # dated duplicate
            {"id": "gpt-4o-audio-preview"},   # excluded token
            {"id": "whisper-1"},              # wrong prefix
            {"id": "o3-mini"},
        ]}
        ids = [m["id"] for m in _parse_openai_models(data)]
        assert ids == ["gpt-4o", "o3-mini"]

    def test_parse_anthropic_models(self):
        from app.interactive.model_pricing import _parse_anthropic_models
        data = {"data": [
            {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
            {"id": "other-model"},
        ]}
        models = _parse_anthropic_models(data)
        assert models == [{"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"}]

    def test_is_stale(self):
        from datetime import datetime, timezone
        from app.interactive import model_pricing
        assert model_pricing._is_stale(24) is True  # never refreshed
        model_pricing._cache = {"updated_at": datetime.now(timezone.utc).isoformat()}
        assert model_pricing._is_stale(24) is False
        model_pricing._cache = {"updated_at": "2020-01-01T00:00:00+00:00"}
        assert model_pricing._is_stale(24) is True

    def test_catalog_includes_pricing(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        router = ModelRouter()
        catalog = {e["id"]: e for e in router.get_model_catalog()}
        assert catalog["claude-sonnet"]["input_per_mtok"] == 3.0
        assert catalog["claude-sonnet"]["output_per_mtok"] == 15.0

    def test_catalog_merges_discovered_models(self, monkeypatch):
        from app.interactive import model_pricing
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        model_pricing._cache = {"models": {"anthropic": [
            {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5"},
            {"id": "claude-sonnet-4-20250514", "label": "dup of alias api_model"},
        ]}}
        router = ModelRouter()
        ids = router.get_available_models()
        assert "claude-haiku-4-5" in ids
        # discovered id matching an existing alias's api_model is not duplicated
        assert "claude-sonnet-4-20250514" not in ids

