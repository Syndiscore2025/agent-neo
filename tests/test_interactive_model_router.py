"""
Tests for interactive model router.
"""

import pytest
from app.interactive.model_router import ModelRouter, ModelType, get_model_router


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
        """Test completion generation (placeholder)."""
        router = ModelRouter()
        completion = await router.generate_completion(
            code_context="def test():",
            cursor_position=10,
            language="python"
        )
        
        # Placeholder returns empty string
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

