"""CinderACE Sessions v2 — LLM summarization engine.

Supports OpenAI, Anthropic, OpenRouter, and custom URL endpoints.
Each provider implements a common interface: summarize() and test_connection().
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def _validate_endpoint_url(url: str) -> None:
    """Ensure custom LLM endpoints use HTTPS (or are local/loopback).

    Prevents API keys from being sent over plain HTTP to non-local hosts.
    Localhost and loopback addresses are allowed for local proxies and
    self-hosted models (Ollama, vLLM, etc.).

    Raises:
        ValueError: If the URL uses http:// for a non-local host.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""

    if scheme == "https":
        return
    if scheme == "http":
        # Allow localhost and loopback for local models/proxies
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return
        # Allow local network IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        parts = host.split(".")
        if len(parts) == 4 and parts[0].isdigit():
            try:
                octet0 = int(parts[0])
                if octet0 in (10, 192, 172):
                    if octet0 == 192 and parts[1] == "168":
                        return
                    if octet0 == 10:
                        return
                    if octet0 == 172 and parts[1].isdigit():
                        octet1 = int(parts[1])
                        if 16 <= octet1 <= 31:
                            return
            except ValueError:
                pass
        raise ValueError(
            f"Refusing to send API key over plain HTTP to non-local host '{host}'. "
            "Use HTTPS, or connect to a localhost/loopback endpoint."
        )
    if scheme == "":
        raise ValueError(f"URL missing scheme (use https:// or http://localhost:...): {url}")

# ── Common Types ────────────────────────────────────────────────────


class SummarizeResult:
    """Structured result from a summarization call."""

    def __init__(self, success: bool, content: str = "", error: str = "",
                 model: str = "", tokens_used: int = 0):
        self.success = success
        self.content = content
        self.error = error
        self.model = model
        self.tokens_used = tokens_used

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "model": self.model,
            "tokens_used": self.tokens_used,
        }


# ── Abstract Provider ───────────────────────────────────────────────


class LLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    @abstractmethod
    def summarize(self, content: str, prompt_template: str,
                  max_tokens: int = 4096) -> SummarizeResult:
        """Send content + template to the LLM and return the summary."""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Validate the API key and endpoint are reachable."""
        ...


# ── OpenAI ──────────────────────────────────────────────────────────


class OpenAIProvider(LLMProvider):
    """OpenAI API (also works for OpenAI-compatible endpoints)."""

    API_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str, model: str = "", custom_url: str = ""):
        super().__init__(api_key, model or self.DEFAULT_MODEL)
        if custom_url:
            _validate_endpoint_url(custom_url)
        self._base_url = (custom_url.rstrip("/") if custom_url
                          else self.API_URL)

    def summarize(self, content: str, prompt_template: str,
                  max_tokens: int = 4096) -> SummarizeResult:
        prompt = prompt_template.replace("{content}", content)
        try:
            resp = requests.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=120,
            )
            if resp.status_code != 200:
                error_detail = resp.json().get("error", {}).get("message", resp.text)
                return SummarizeResult(
                    success=False,
                    error=f"API error ({resp.status_code}): {error_detail}",
                )
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return SummarizeResult(
                success=True,
                content=text,
                model=self._model,
                tokens_used=usage.get("total_tokens", 0),
            )
        except requests.exceptions.Timeout:
            return SummarizeResult(success=False, error="Request timed out (120s)")
        except requests.exceptions.ConnectionError:
            return SummarizeResult(success=False, error="Connection failed — check URL and network")
        except Exception as e:
            logger.exception("OpenAI summarize error")
            return SummarizeResult(success=False, error=str(e))

    def test_connection(self) -> bool:
        try:
            resp = requests.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False


# ── Anthropic ───────────────────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API."""

    API_URL = "https://api.anthropic.com/v1/messages"
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, model: str = ""):
        super().__init__(api_key, model or self.DEFAULT_MODEL)

    def summarize(self, content: str, prompt_template: str,
                  max_tokens: int = 4096) -> SummarizeResult:
        prompt = prompt_template.replace("{content}", content)
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=120,
            )
            if resp.status_code != 200:
                error_detail = resp.json().get("error", {}).get("message", resp.text)
                return SummarizeResult(
                    success=False,
                    error=f"API error ({resp.status_code}): {error_detail}",
                )
            data = resp.json()
            text_blocks = [
                b.get("text", "") for b in data.get("content", [])
                if b.get("type") == "text"
            ]
            text = "\n".join(text_blocks)
            usage = data.get("usage", {})
            return SummarizeResult(
                success=True,
                content=text,
                model=data.get("model", self._model),
                tokens_used=(usage.get("input_tokens", 0)
                             + usage.get("output_tokens", 0)),
            )
        except requests.exceptions.Timeout:
            return SummarizeResult(success=False, error="Request timed out (120s)")
        except requests.exceptions.ConnectionError:
            return SummarizeResult(success=False, error="Connection failed — check network")
        except Exception as e:
            logger.exception("Anthropic summarize error")
            return SummarizeResult(success=False, error=str(e))

    def test_connection(self) -> bool:
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False


# ── OpenRouter ──────────────────────────────────────────────────────


class OpenRouterProvider(LLMProvider):
    """OpenRouter API (unified gateway to many models)."""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

    def __init__(self, api_key: str, model: str = ""):
        super().__init__(api_key, model or self.DEFAULT_MODEL)

    def summarize(self, content: str, prompt_template: str,
                  max_tokens: int = 4096) -> SummarizeResult:
        prompt = prompt_template.replace("{content}", content)
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cinderace.sessions.local",
                    "X-Title": "CinderACE Sessions",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=120,
            )
            if resp.status_code != 200:
                error_detail = resp.json().get("error", {}).get("message", resp.text)
                return SummarizeResult(
                    success=False,
                    error=f"API error ({resp.status_code}): {error_detail}",
                )
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return SummarizeResult(
                success=True,
                content=text,
                model=self._model,
                tokens_used=usage.get("total_tokens", 0),
            )
        except requests.exceptions.Timeout:
            return SummarizeResult(success=False, error="Request timed out (120s)")
        except requests.exceptions.ConnectionError:
            return SummarizeResult(success=False, error="Connection failed — check network")
        except Exception as e:
            logger.exception("OpenRouter summarize error")
            return SummarizeResult(success=False, error=str(e))

    def test_connection(self) -> bool:
        try:
            resp = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cinderace.sessions.local",
                    "X-Title": "CinderACE Sessions",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False


# ── Provider Factory ────────────────────────────────────────────────


def get_provider(provider_name: str, api_key: str, model: str = "",
                 custom_url: str = "") -> LLMProvider:
    """Create a provider instance by name.

    Args:
        provider_name: One of 'openai', 'anthropic', 'openrouter', 'custom'
        api_key: API key for the provider
        model: Model name (uses provider default if empty)
        custom_url: Custom endpoint URL (for 'openai' with custom base, or 'custom')

    Returns:
        LLMProvider instance ready for summarize() / test_connection()

    Raises:
        ValueError: If provider_name is unknown
    """
    providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "openrouter": OpenRouterProvider,
        "custom": OpenAIProvider,  # Custom uses OpenAI-compatible API format
    }

    cls = providers.get(provider_name)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Supported: {', '.join(providers.keys())}"
        )

    if provider_name == "custom":
        if not custom_url:
            raise ValueError("Custom provider requires a URL endpoint")
        _validate_endpoint_url(custom_url)
        return OpenAIProvider(api_key=api_key, model=model, custom_url=custom_url)

    if provider_name == "openai" and custom_url:
        _validate_endpoint_url(custom_url)
        return OpenAIProvider(api_key=api_key, model=model, custom_url=custom_url)

    return cls(api_key=api_key, model=model)