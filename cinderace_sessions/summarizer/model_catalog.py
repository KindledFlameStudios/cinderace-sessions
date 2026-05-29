"""CinderACE Sessions v2 — Model catalog for LLM providers.

Provides live model discovery from OpenAI, Anthropic, OpenRouter, and Ollama
with static fallbacks when no API key is configured or the fetch fails.

Returns a normalized dict: {ok, models, live, msg}
Each model: {id, name, description, free}
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger(__name__)

# ── Provider model list URLs ─────────────────────────────────────────

OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# ── Preferred sort order per provider ──────────────────────────────

PREFERRED_ORDER = {
    "openai": [
        "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "gpt-4-turbo", "gpt-4", "o3", "o3-mini", "o4-mini",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "openrouter": [
        "anthropic/claude-sonnet-4-20250514", "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o", "openai/gpt-4o-mini", "google/gemini-2.5-pro",
        "google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct",
    ],
}

# ── Static fallback chat models per provider ──────────────────────

STATIC_MODELS = {
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o", "description": "Most capable GPT-4 model"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast and affordable"},
        {"id": "gpt-4.1", "name": "GPT-4.1", "description": "Latest GPT-4.1 series"},
        {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini", "description": "Balanced performance"},
        {"id": "gpt-4.1-nano", "name": "GPT-4.1 Nano", "description": "Fastest and cheapest"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "Previous generation"},
        {"id": "o3", "name": "o3", "description": "Reasoning model"},
        {"id": "o3-mini", "name": "o3 Mini", "description": "Fast reasoning"},
        {"id": "o4-mini", "name": "o4 Mini", "description": "Latest reasoning model"},
    ],
    "anthropic": [
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Latest and most capable"},
        {"id": "claude-3-7-sonnet-20250219", "name": "Claude 3.7 Sonnet", "description": "Extended thinking"},
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "description": "Strong all-rounder"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "Fast and affordable"},
        {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "Most capable legacy model"},
    ],
    "openrouter": [
        {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "via OpenRouter"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "description": "via OpenRouter"},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "via OpenRouter"},
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "description": "via OpenRouter"},
        {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro", "description": "via OpenRouter"},
        {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "description": "via OpenRouter"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "description": "via OpenRouter"},
    ],
}


# ── Error handling ──────────────────────────────────────────────────

def friendly_auth_error(msg: str) -> str:
    """Convert raw HTTP/API errors into human-readable strings."""
    m = msg.lower()
    if "invalid" in m and ("api" in m or "key" in m or "auth" in m or "token" in m):
        return "Invalid API key"
    if "unauthorized" in m or " 401" in m:
        return "Invalid API key"
    if "forbidden" in m or " 403" in m:
        return "Access forbidden — check your API key permissions"
    if "rate" in m or " 429" in m:
        return "Rate limited; try again in a moment"
    if "connection" in m or "refused" in m:
        return "Connection refused — check URL and network"
    if "timed out" in m or "timeout" in m:
        return "Request timed out"
    if "not found" in m or " 404" in m:
        return "Endpoint not found — check the URL"
    return str(msg)[:120]


# ── Internal helpers ────────────────────────────────────────────────

def _read_json(url: str, headers: dict | None = None,
               timeout: int = 15) -> dict:
    """Fetch JSON from a URL with error handling."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _static_models(provider: str, msg: str = "") -> dict:
    """Build a static fallback result from hardcoded models."""
    models = STATIC_MODELS.get(provider, [])
    return {
        "ok": True,
        "models": [{**m, "free": False} for m in models],
        "live": False,
        "msg": msg,
    }


def _sort_models(models: list[dict], provider: str) -> list[dict]:
    """Sort models with preferred ones first, rest alphabetized."""
    preferred = PREFERRED_ORDER.get(provider, [])
    ranked = []
    rest = list(models)

    for pref in preferred:
        for i, m in enumerate(rest):
            if m["id"] == pref:
                ranked.append(rest.pop(i))
                break

    rest.sort(key=lambda m: m.get("name", m["id"]).lower())
    return ranked + rest


# ── Live fetchers ───────────────────────────────────────────────────

def fetch_openai_models(api_key: str) -> dict:
    """Fetch available chat models from OpenAI."""
    if not api_key:
        return _static_models("openai", "No API key; showing built-in models")

    try:
        data = _read_json(
            OPENAI_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        raw = data.get("data", [])
        # Filter to chat/completion models (exclude embedding, TTS, etc.)
        chat_models = []
        skip_prefixes = ("text-embedding", "dall-e", "tts", "whisper",
                         "babbage", "davinci")
        for m in raw:
            mid = m.get("id", "")
            if any(mid.startswith(p) for p in skip_prefixes):
                continue
            chat_models.append({
                "id": mid,
                "name": mid,  # OpenAI returns IDs as names
                "description": "",
                "free": False,
            })

        if not chat_models:
            return _static_models(
                "openai", "No chat models found; showing built-in models")

        return {
            "ok": True,
            "models": _sort_models(chat_models, "openai"),
            "live": True,
            "msg": "",
        }

    except urllib.error.HTTPError as e:
        return _static_models(
            "openai",
            f"Could not refresh: {friendly_auth_error(str(e.reason))}")
    except Exception as e:
        logger.debug("OpenAI model fetch failed: %s", e, exc_info=True)
        return _static_models(
            "openai",
            f"Could not refresh: {friendly_auth_error(str(e))}")


def fetch_anthropic_models(api_key: str) -> dict:
    """Fetch available models from Anthropic."""
    if not api_key:
        return _static_models("anthropic", "No API key; showing built-in models")

    try:
        data = _read_json(
            ANTHROPIC_MODELS_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        raw = data.get("data", [])
        chat_models = []
        for m in raw:
            mid = m.get("id", "")
            # Anthropic returns model IDs directly
            chat_models.append({
                "id": mid,
                "name": mid,
                "description": m.get("display_name", ""),
                "free": False,
            })

        if not chat_models:
            return _static_models(
                "anthropic", "No models found; showing built-in models")

        return {
            "ok": True,
            "models": _sort_models(chat_models, "anthropic"),
            "live": True,
            "msg": "",
        }

    except urllib.error.HTTPError as e:
        return _static_models(
            "anthropic",
            f"Could not refresh: {friendly_auth_error(str(e.reason))}")
    except Exception as e:
        logger.debug("Anthropic model fetch failed: %s", e, exc_info=True)
        return _static_models(
            "anthropic",
            f"Could not refresh: {friendly_auth_error(str(e))}")


def fetch_openrouter_models(api_key: str) -> dict:
    """Fetch available models from OpenRouter."""
    if not api_key:
        return _static_models("openrouter", "No API key; showing built-in models")

    try:
        data = _read_json(
            OPENROUTER_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        raw = data.get("data", [])
        chat_models = []
        for m in raw:
            mid = m.get("id", "")
            # Skip embedding-only models
            arch = m.get("architecture", {})
            if isinstance(arch, dict):
                modality = arch.get("modality", "")
                if modality == "embed" or "embed" in str(m.get("output_modalities", [])):
                    continue

            name = m.get("name", mid)
            # Detect free models (OpenRouter uses :free suffix or pricing)
            free = mid.endswith(":free")
            pricing = m.get("pricing", {})
            if isinstance(pricing, dict):
                prompt_price = pricing.get("prompt", "1")
                try:
                    free = float(prompt_price) == 0.0
                except (ValueError, TypeError):
                    pass

            chat_models.append({
                "id": mid,
                "name": name,
                "description": m.get("context_length", ""),
                "free": free,
            })

        if not chat_models:
            return _static_models(
                "openrouter", "No chat models found; showing built-in models")

        return {
            "ok": True,
            "models": _sort_models(chat_models, "openrouter"),
            "live": True,
            "msg": "",
        }

    except urllib.error.HTTPError as e:
        return _static_models(
            "openrouter",
            f"Could not refresh: {friendly_auth_error(str(e.reason))}")
    except Exception as e:
        logger.debug("OpenRouter model fetch failed: %s", e, exc_info=True)
        return _static_models(
            "openrouter",
            f"Could not refresh: {friendly_auth_error(str(e))}")


def fetch_ollama_models() -> dict:
    """Fetch running chat models from local Ollama."""
    try:
        # Import here to avoid hard dependency
        from cinderace_sessions.summarizer.ollama import list_models
        models_raw = list_models()
        if models_raw is None:
            return {
                "ok": False,
                "models": [],
                "live": False,
                "msg": "Ollama is not running",
            }
        chat_models = []
        for m in models_raw:
            mid = m if isinstance(m, str) else m.get("name", "")
            # Filter out embedding models
            if "embed" in mid.lower():
                continue
            chat_models.append({
                "id": mid,
                "name": mid,
                "description": "",
                "free": True,
            })
        return {
            "ok": True,
            "models": chat_models,
            "live": True,
            "msg": "",
        }
    except Exception as e:
        logger.debug("Ollama model fetch failed: %s", e, exc_info=True)
        return {
            "ok": False,
            "models": [],
            "live": False,
            "msg": f"Ollama error: {friendly_auth_error(str(e))}",
        }


# ── Dispatch ────────────────────────────────────────────────────────

def get_provider_models(provider: str, api_key: str = "") -> dict:
    """Fetch available chat models for a provider.

    Returns:
        {ok: bool, models: list, live: bool, msg: str}
    """
    dispatch = {
        "openai": fetch_openai_models,
        "anthropic": fetch_anthropic_models,
        "openrouter": fetch_openrouter_models,
        "ollama": lambda _key="": fetch_ollama_models(),
        "custom": lambda _key="": _static_models("openai", "Custom endpoint — enter model name manually"),
    }
    fn = dispatch.get(provider)
    if fn is None:
        return {"ok": False, "models": [], "live": False,
                "msg": f"Unknown provider: {provider}"}
    return fn(api_key) if provider != "ollama" else fn()