"""CinderACE Sessions v2 — configuration system.

Resolution order: env var > ~/.cinderace-sessions/settings.json > defaults
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ── defaults ──────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "output_directory": "",
    "default_export_format": "md",
    "html_theme": "ember",
    "include_thinking": True,
    "include_tools": True,
    "user_label": "User",
    "assistant_label": "Assistant",
    "user_emoji": "",
    "assistant_emoji": "",
    "auto_detect_on_launch": True,
    "summarizer_provider": "",
    "summarizer_api_key": "",
    "summarizer_model": "",
    "summarizer_custom_url": "",
    "default_ember_collection": "general",
    "ember_memory_url": "http://localhost:2214",
}

CONFIG_DIR = Path.home() / ".cinderace-sessions"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CUSTOM_CLIS_FILE = CONFIG_DIR / "custom_clis.json"


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load merged configuration: env vars > settings file > defaults."""
    config = dict(DEFAULTS)

    # Layer 1: file defaults
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
        except (json.JSONDecodeError, OSError):
            pass

    # Layer 2: environment variable overrides (CINDERACE_SESSIONS_* prefix)
    env_map = {
        "CINDERACE_SESSIONS_OUTPUT_DIR": "output_directory",
        "CINDERACE_SESSIONS_EXPORT_FORMAT": "default_export_format",
        "CINDERACE_SESSIONS_HTML_THEME": "html_theme",
        "CINDERACE_SESSIONS_INCLUDE_THINKING": "include_thinking",
        "CINDERACE_SESSIONS_INCLUDE_TOOLS": "include_tools",
        "CINDERACE_SESSIONS_USER_LABEL": "user_label",
        "CINDERACE_SESSIONS_ASSISTANT_LABEL": "assistant_label",
    }
    for env_key, config_key in env_map.items():
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # coerce booleans
            if isinstance(DEFAULTS.get(config_key), bool):
                config[config_key] = env_val.lower() in ("1", "true", "yes")
            else:
                config[config_key] = env_val

    return config


def save_settings(settings: dict[str, Any]) -> bool:
    """Persist user settings to disk. Returns True on success.

    Sets file permissions to owner-only (0o600) since the file
    may contain API keys.
    """
    _ensure_config_dir()
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        # Protect API keys — owner read/write only
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass  # Windows doesn't support Unix permissions
        return True
    except OSError:
        return False


def load_custom_clis() -> list[dict[str, Any]]:
    """Load custom CLI registrations from config file."""
    if not CUSTOM_CLIS_FILE.exists():
        return []
    try:
        with open(CUSTOM_CLIS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("custom_clis", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_custom_clis(clis: list[dict[str, Any]]) -> bool:
    """Persist custom CLI registrations to disk."""
    _ensure_config_dir()
    try:
        with open(CUSTOM_CLIS_FILE, "w", encoding="utf-8") as f:
            json.dump({"custom_clis": clis}, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(CUSTOM_CLIS_FILE, 0o600)
        except OSError:
            pass  # Windows doesn't support Unix permissions
        return True
    except OSError:
        return False