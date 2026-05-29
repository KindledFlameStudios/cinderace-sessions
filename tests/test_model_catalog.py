"""Tests for the model catalog — static fallbacks and error handling."""

import pytest

from cinderace_sessions.summarizer.model_catalog import (
    get_provider_models,
    fetch_openai_models,
    fetch_anthropic_models,
    fetch_openrouter_models,
    fetch_ollama_models,
    friendly_auth_error,
    _static_models,
)


# ── Static fallbacks ─────────────────────────────────────────────────

class TestStaticFallbacks:
    def test_openai_static_models(self):
        result = _static_models("openai", "No API key")
        assert result["ok"] is True
        assert result["live"] is False
        assert len(result["models"]) > 0
        # Check each model has required fields
        for m in result["models"]:
            assert "id" in m
            assert "name" in m
            assert m["free"] is False  # OpenAI has no free models

    def test_anthropic_static_models(self):
        result = _static_models("anthropic", "No API key")
        assert result["ok"] is True
        assert len(result["models"]) >= 3  # At least Sonnet, Haiku, Opus

    def test_openrouter_static_models(self):
        result = _static_models("openrouter", "No API key")
        assert result["ok"] is True
        assert len(result["models"]) >= 5

    def test_unknown_provider_static(self):
        result = _static_models("unknown_provider", "No API key")
        assert result["ok"] is True
        assert len(result["models"]) == 0

    def test_result_shape(self):
        result = _static_models("openai", "Test message")
        assert "ok" in result
        assert "models" in result
        assert "live" in result
        assert "msg" in result
        assert result["live"] is False


# ── Live fetch with no key ──────────────────────────────────────────

class TestFetchWithoutKey:
    def test_openai_no_key_returns_static(self):
        result = fetch_openai_models("")
        assert result["ok"] is True
        assert result["live"] is False
        assert "No API key" in result["msg"]

    def test_anthropic_no_key_returns_static(self):
        result = fetch_anthropic_models("")
        assert result["ok"] is True
        assert result["live"] is False

    def test_openrouter_no_key_returns_static(self):
        result = fetch_openrouter_models("")
        assert result["ok"] is True
        assert result["live"] is False

    def test_ollama_returns_result(self):
        # May be running or not, but should not crash
        result = fetch_ollama_models()
        assert "ok" in result
        assert "models" in result


# ── Friendly error messages ───────────────────────────────────────────

class TestFriendlyAuthError:
    def test_invalid_key(self):
        assert "Invalid API key" in friendly_auth_error("Invalid api key provided")

    def test_unauthorized(self):
        assert "Invalid API key" in friendly_auth_error("401 Unauthorized")

    def test_rate_limited(self):
        assert "Rate limited" in friendly_auth_error("429 rate limit exceeded")

    def test_connection_refused(self):
        assert "Connection refused" in friendly_auth_error("Connection refused on port 443")

    def test_timeout(self):
        assert "timed out" in friendly_auth_error("Request timed out after 30s")

    def test_not_found(self):
        assert "not found" in friendly_auth_error("404 Not found")

    def test_generic_error(self):
        result = friendly_auth_error("Some random error")
        assert len(result) > 0


# ── Dispatch function ────────────────────────────────────────────────

class TestGetProviderModels:
    def test_known_provider(self):
        result = get_provider_models("openai", "")
        assert result["ok"] is True
        assert len(result["models"]) > 0

    def test_unknown_provider(self):
        result = get_provider_models("nonexistent_provider", "")
        assert result["ok"] is False

    def test_custom_provider(self):
        result = get_provider_models("custom", "")
        assert result["ok"] is True
        assert "manually" in result["msg"].lower() or "enter" in result["msg"].lower()

    def test_ollama_dispatch(self):
        result = get_provider_models("ollama", "")
        # Should not crash regardless of Ollama status
        assert "ok" in result