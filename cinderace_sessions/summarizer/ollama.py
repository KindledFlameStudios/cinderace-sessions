"""CinderACE Sessions v2 — Ollama local model support.

Uses Ollama's HTTP API at localhost:11434 for local LLM summarization.
"""

from __future__ import annotations

import logging

import requests

from .engine import LLMProvider, SummarizeResult

from cinderace_sessions.config import load_config

logger = logging.getLogger(__name__)

_config = load_config()
OLLAMA_URL = _config.get("ollama_url", "http://localhost:11434")
DEFAULT_MODEL = "llama3.2"


class OllamaProvider(LLMProvider):
    """Local Ollama provider — no API key needed."""

    def __init__(self, model: str = "", base_url: str = ""):
        # Ollama doesn't need an API key
        super().__init__(api_key="", model=model or DEFAULT_MODEL)
        self._base_url = (base_url.rstrip("/") if base_url
                          else OLLAMA_URL)

    def summarize(self, content: str, prompt_template: str,
                  max_tokens: int = 4096) -> SummarizeResult:
        prompt = prompt_template.replace("{content}", content)
        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.3,
                    },
                },
                timeout=300,  # Local models can be slower
            )
            if resp.status_code != 200:
                return SummarizeResult(
                    success=False,
                    error=f"Ollama error ({resp.status_code}): {resp.text[:200]}",
                )
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            # Ollama reports eval_count as total tokens generated
            eval_count = data.get("eval_count", 0)
            prompt_count = data.get("prompt_eval_count", 0)
            return SummarizeResult(
                success=True,
                content=text,
                model=data.get("model", self._model),
                tokens_used=prompt_count + eval_count,
            )
        except requests.exceptions.Timeout:
            return SummarizeResult(
                success=False,
                error="Ollama request timed out (300s) — model may be loading or too slow",
            )
        except requests.exceptions.ConnectionError:
            return SummarizeResult(
                success=False,
                error="Cannot connect to Ollama — is it running? (ollama serve)",
            )
        except Exception as e:
            logger.error("Ollama summarize error: %s", e)
            return SummarizeResult(success=False, error=str(e))

    def test_connection(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            # Health check: ping the API
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False

            # Check if our model exists (or can be pulled)
            models = resp.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            # Accept partial match (e.g. "llama3.2" matches "llama3.2:latest")
            return any(self._model.split(":")[0] in name for name in model_names)
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available Ollama model names."""
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return []
            models = resp.json().get("models", [])
            return [m.get("name", "") for m in models]
        except Exception:
            return []


def list_models(url: str = "") -> list[str] | None:
    """List available Ollama model names (standalone, no instance needed).

    Returns None if Ollama is not running, empty list if running but no models.
    """
    url = (url.rstrip("/") if url else OLLAMA_URL)
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        if resp.status_code != 200:
            return None
        models = resp.json().get("models", [])
        return [m.get("name", "") for m in models]
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def is_ollama_running(url: str = "") -> bool:
    """Quick check if Ollama is running at the given URL."""
    url = (url.rstrip("/") if url else OLLAMA_URL)
    try:
        resp = requests.get(f"{url}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False