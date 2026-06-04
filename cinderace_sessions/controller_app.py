"""CinderACE Sessions v2 — controller app (pywebview desktop GUI).

Main application window with the SessionsAPI backend exposed
to the JavaScript frontend via pywebview's bridge.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import webview

from cinderace_sessions import __version__
from cinderace_sessions.config import load_config, save_settings, load_custom_clis, save_custom_clis
from cinderace_sessions.detector.registry import DetectorRegistry
from cinderace_sessions.parser.base import (
    ExportFormat,
    HtmlTheme,
    RenderOptions,
    SessionInfo,
)
from cinderace_sessions.parser.jsonl_parser import (
    build_stats,
    extract_session_meta,
    parse_jsonl_transcript,
)
from cinderace_sessions.parser.gemini_parser import parse_gemini_session, gemini_extract_meta

logger = logging.getLogger(__name__)


def _load_asset(filename: str) -> str:
    """Load a UI asset file from the controller_assets package."""
    assets_dir = Path(__file__).parent / "controller_assets"
    filepath = assets_dir / filename
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return f"<!-- Asset not found: {filename} -->"


def _get_html() -> str:
    """Load the UI HTML and inline CSS/JS templates."""
    html = _load_asset("ui.html")
    css = _load_asset("ui.css")
    js = _load_asset("ui.js")

    html = html.replace("{{CAS_CSS}}", css)
    html = html.replace("{{CAS_JS}}", js)
    return html


class SessionsAPI:
    """Backend API exposed to the JS frontend via pywebview bridge."""

    def __init__(self):
        self._registry = DetectorRegistry()
        self._sessions_cache: list[dict] = []
        self._window = None

    # ── Config ─────────────────────────────────────────────────────

    def get_config(self) -> dict:
        """Return config for the JS frontend, with sensitive fields redacted."""
        config = load_config()
        # Never send API keys to the frontend — they don't need them.
        # The backend handles all LLM calls; JS only needs the key's presence state.
        has_key = bool(config.get("summarizer_api_key", ""))
        config["has_api_key"] = has_key
        config["summarizer_api_key"] = ""  # Redact — never send to JS
        return config

    def save_settings(self, settings: dict) -> bool:
        """Save user settings, preserving API key if the frontend sent an empty one.

        The frontend redacts the API key (sends '' when unchanged). We must
        preserve the existing key rather than overwriting it with ''.
        """
        # If the frontend sent an empty API key, preserve the existing one
        if not settings.get("summarizer_api_key"):
            current = load_config()
            settings["summarizer_api_key"] = current.get("summarizer_api_key", "")

        result = save_settings(settings)
        if result:
            # Also refresh registry if custom CLIs changed
            self._registry.reload_custom_clis()
        return result

    def get_version(self) -> str:
        return __version__

    # ── CLI Detection ──────────────────────────────────────────────

    def get_cli_status(self) -> list[dict]:
        """Return status of all CLI detectors (built-in + custom)."""
        return self._registry.all_detectors_with_status

    def refresh_sessions(self) -> bool:
        """Force rescan all CLIs."""
        self._registry.reload_custom_clis()
        self._sessions_cache = []
        return True

    # ── Session Listing ────────────────────────────────────────────

    def get_sessions(self) -> list[dict]:
        """Return all discovered sessions with metadata."""
        sessions = self._registry.scan_all()
        self._sessions_cache = [self._session_info_to_dict(s) for s in sessions]
        return self._sessions_cache

    # ── Filepath Validation ────────────────────────────────────────

    def _validate_filepath(self, filepath: str) -> str | None:
        """Validate that a filepath exists in the session cache.

        Prevents arbitrary file access via the JS bridge — only filepaths
        that came from a real detector scan are accepted.
        Returns the validated filepath, or None if not found.
        """
        for s in self._sessions_cache:
            if s.get("filepath") == filepath:
                return filepath
        logger.warning("Rejected filepath not in session cache: %s", filepath)
        return None

    def get_session_detail(self, filepath: str) -> dict | None:
        """Return full parsed session data for preview."""
        if not self._validate_filepath(filepath):
            logger.error("get_session_detail: unvalidated filepath rejected")
            return None

        # Find the session info to determine source
        source = "unknown"
        for s in self._sessions_cache:
            if s.get("filepath") == filepath:
                source = s.get("cli_source", "unknown")
                break

        # Parse based on source
        turns, meta = self._parse_session(filepath, source)
        if turns is None:
            return None

        stats = build_stats(turns)

        return {
            "filepath": filepath,
            "cli_source": source,
            "meta": {
                "session_id": meta.session_id,
                "slug": meta.slug,
                "first_date": meta.first_date,
                "entrypoint": meta.entrypoint.value if hasattr(meta.entrypoint, "value") else str(meta.entrypoint),
            },
            "stats": {
                "user_messages": stats.user_messages,
                "assistant_messages": stats.assistant_messages,
                "thinking_blocks": stats.thinking_blocks,
                "tool_calls": stats.tool_calls,
                "user_chars": stats.user_chars,
                "assistant_chars": stats.assistant_chars,
            },
            "turns": [
                {
                    "role": t.role,
                    "timestamp": t.timestamp,
                    "uuid": t.uuid,
                    "blocks": [
                        {"type": b.type.value if hasattr(b.type, "value") else str(b.type),
                         "text": b.text, "thinking": b.thinking, "name": b.name}
                        for b in t.blocks
                    ],
                }
                for t in turns
            ],
        }

    # ── Export ──────────────────────────────────────────────────────

    def export_session(self, filepath: str, format: str) -> str | None:
        """Export a session to the specified format. Returns output file path."""
        if not self._validate_filepath(filepath):
            logger.error("export_session: unvalidated filepath rejected")
            return None

        source = "unknown"
        for s in self._sessions_cache:
            if s.get("filepath") == filepath:
                source = s.get("cli_source", "unknown")
                break

        turns, meta = self._parse_session(filepath, source)
        if turns is None:
            return None

        stats = build_stats(turns)
        config = load_config()
        options = RenderOptions(
            include_thinking=config.get("include_thinking", True),
            include_tools=config.get("include_tools", True),
            user_label=config.get("user_label", "User"),
            assistant_label=config.get("assistant_label", "Assistant"),
            user_emoji=config.get("user_emoji", ""),
            assistant_emoji=config.get("assistant_emoji", ""),
        )
        theme = config.get("html_theme", "ember")

        # Determine output directory
        output_dir = config.get("output_directory", "")
        if not output_dir:
            output_dir = os.path.join(os.path.expanduser("~"), "CinderACE-Exports")
        os.makedirs(output_dir, exist_ok=True)

        base_name = Path(filepath).stem

        try:
            if format == "md":
                from cinderace_sessions.renderer.markdown import build_document
                content = build_document(turns, stats, meta, options)
                out_path = os.path.join(output_dir, f"{base_name}.md")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

            elif format == "html":
                from cinderace_sessions.renderer.html import build_html
                content = build_html(turns, stats, meta, options, theme)
                out_path = os.path.join(output_dir, f"{base_name}.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

            elif format == "json":
                from cinderace_sessions.renderer.json_export import build_json
                content = build_json(turns, stats, meta, options)
                out_path = os.path.join(output_dir, f"{base_name}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

            elif format == "jsonl":
                from cinderace_sessions.renderer.jsonl_export import build_jsonl
                content = build_jsonl(turns, meta, options)
                out_path = os.path.join(output_dir, f"{base_name}.jsonl")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

            elif format == "zip":
                from cinderace_sessions.renderer.zip_export import build_zip
                zip_bytes = build_zip(turns, stats, meta, options, base_name, theme)
                out_path = os.path.join(output_dir, f"{base_name}.zip")
                with open(out_path, "wb") as f:
                    f.write(zip_bytes)

            else:
                return None

            return out_path

        except Exception as e:
            logger.error("Export failed for %s: %s", filepath, e, exc_info=True)
            return f"Error: {str(e)}"

    # ── ember-memory Bridge ──────────────────────────────────────────

    def get_ember_status(self) -> str | None:
        """Check if ember-memory is available.

        ember-memory runs as a stdio MCP server (not HTTP), so we check:
        1. Can we import the Python library? (ember-memory installed locally)
        2. Is the MCP server binary available?
        """
        # Try library import (ember_memory installed in same environment)
        try:
            from ember_memory.core.backends.loader import get_backend_v2
            return "library"
        except ImportError:
            pass

        # Check if the ember-memory MCP server is available as a command
        import shutil
        if shutil.which("ember-memory") or shutil.which("ember_memory"):
            return "mcp"

        return None

    def ingest_session(self, filepath: str, collection: str = "general", tags: str = "") -> bool:
        """Ingest a session into ember-memory via HTTP MCP server."""
        if not self._validate_filepath(filepath):
            logger.error("ingest_session: unvalidated filepath rejected")
            return False

        source = "unknown"
        for s in self._sessions_cache:
            if s.get("filepath") == filepath:
                source = s.get("cli_source", "unknown")
                break

        turns, meta = self._parse_session(filepath, source)
        if turns is None:
            return False

        config = load_config()
        options = RenderOptions(
            include_thinking=config.get("include_thinking", True),
            include_tools=config.get("include_tools", True),
        )

        from cinderace_sessions.renderer.markdown import build_document
        from cinderace_sessions.parser.jsonl_parser import build_stats

        stats = build_stats(turns)
        content = build_document(turns, stats, meta, options)

        # Use HTTP MCP server for ingest
        try:
            import requests

            config = load_config()
            ember_url = config.get("ember_memory_url", "http://localhost:2214").rstrip("/")
            tags_str = tags or f"cli:{source},project:{meta.slug or 'unknown'},date:{meta.first_date}"
            source_str = f"cinderace-sessions:{source}"

            resp = requests.post(
                f"{ember_url}/tools/memory_store",
                json={
                    "content": content[:8000],
                    "collection": collection,
                    "tags": tags_str,
                    "source": source_str,
                },
                timeout=30,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("ember-memory ingest failed for %s: %s", filepath, e, exc_info=True)
            return False

    # ── Custom CLIs ─────────────────────────────────────────────────

    def add_custom_cli(self, name: str, directory: str, fmt: str, color: str = "#888888") -> bool:
        return self._registry.add_custom_cli(name, directory, fmt, color, enabled=True)

    def remove_custom_cli(self, name: str) -> bool:
        return self._registry.remove_custom_cli(name)

    # ── File Dialog ─────────────────────────────────────────────────

    def browse_directory(self) -> str | None:
        """Open a directory picker dialog."""
        if self._window:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=os.path.expanduser("~"),
            )
            if result and len(result) > 0:
                return result[0]
        return None

    # ── Summarizer ──────────────────────────────────────────────────

    def get_default_template(self) -> str:
        """Return the default summary template."""
        from cinderace_sessions.summarizer.template import load_template
        return load_template("default")

    def load_template(self, name: str = "default") -> str:
        """Load a template by name."""
        from cinderace_sessions.summarizer.template import load_template
        return load_template(name)

    def save_template(self, name: str, content: str) -> bool:
        """Save a summary template."""
        from cinderace_sessions.summarizer.template import save_template
        return save_template(name, content)

    def list_templates(self) -> list[str]:
        """List all available template names."""
        from cinderace_sessions.summarizer.template import list_templates
        return list_templates()

    def delete_template(self, name: str) -> bool:
        """Delete a custom template (cannot delete default)."""
        from cinderace_sessions.summarizer.template import delete_template
        return delete_template(name)

    def test_summarizer_connection(self) -> dict:
        """Test the configured LLM endpoint. Returns a result dict."""
        config = load_config()
        provider_name = config.get("summarizer_provider", "")
        api_key = config.get("summarizer_api_key", "")
        model = config.get("summarizer_model", "")
        custom_url = config.get("summarizer_custom_url", "")

        # Handle Ollama separately (no API key needed)
        if provider_name == "ollama":
            from cinderace_sessions.summarizer.ollama import OllamaProvider
            prov = OllamaProvider(model=model)
            success = prov.test_connection()
            return {
                "success": success,
                "provider": "ollama",
                "model": prov._model,
                "error": "" if success else "Ollama not running or model not found",
            }

        if not provider_name or not api_key:
            return {
                "success": False,
                "provider": provider_name,
                "model": model,
                "error": "Provider and API key required",
            }

        try:
            from cinderace_sessions.summarizer.engine import get_provider
            prov = get_provider(provider_name, api_key, model, custom_url)
            success = prov.test_connection()
            return {
                "success": success,
                "provider": provider_name,
                "model": prov._model,
                "error": "" if success else "Connection test failed — check API key and endpoint",
            }
        except ValueError as e:
            return {"success": False, "provider": provider_name, "model": model, "error": str(e)}
        except Exception as e:
            return {"success": False, "provider": provider_name, "model": model, "error": str(e)}

    def get_provider_models(self, provider: str = "", api_key: str = "") -> dict:
        """Fetch available chat models for a provider.

        If api_key is empty, uses the saved config key.
        Returns: {ok, models: [{id, name, description, free}], live, msg}
        """
        from cinderace_sessions.summarizer.model_catalog import get_provider_models as _get_models
        config = load_config()
        provider = provider or config.get("summarizer_provider", "")
        api_key = api_key or config.get("summarizer_api_key", "")
        return _get_models(provider, api_key)

    def summarize_session(self, filepath: str, template_name: str = "default") -> dict:
        """Summarize a session using the configured LLM provider.

        Returns a dict with: success, content/error, model, tokens_used.
        """
        if not self._validate_filepath(filepath):
            logger.error("summarize_session: unvalidated filepath rejected")
            return {"success": False, "error": "Invalid session filepath", "content": ""}

        from cinderace_sessions.summarizer.engine import get_provider, SummarizeResult
        from cinderace_sessions.summarizer.template import load_template
        from cinderace_sessions.summarizer.ollama import OllamaProvider

        config = load_config()
        provider_name = config.get("summarizer_provider", "")
        api_key = config.get("summarizer_api_key", "")
        model = config.get("summarizer_model", "")
        custom_url = config.get("summarizer_custom_url", "")

        # Find and parse the session
        source = "unknown"
        for s in self._sessions_cache:
            if s.get("filepath") == filepath:
                source = s.get("cli_source", "unknown")
                break

        turns, meta = self._parse_session(filepath, source)
        if turns is None:
            return {"success": False, "error": "Failed to parse session", "content": ""}

        stats = build_stats(turns)

        # Build the content for summarization (truncate if too long)
        options = RenderOptions(
            include_thinking=config.get("include_thinking", True),
            include_tools=config.get("include_tools", False),  # Skip tools in summaries for brevity
        )
        from cinderace_sessions.renderer.markdown import build_document
        content = build_document(turns, stats, meta, options)

        # Truncate to ~120k chars to stay within most LLM context windows
        MAX_CONTENT = 120000
        if len(content) > MAX_CONTENT:
            content = content[:MAX_CONTENT] + "\n\n[... session truncated for length ...]"

        # Load template
        template = load_template(template_name)

        # Create provider and call
        try:
            if provider_name == "ollama":
                prov = OllamaProvider(model=model)
            else:
                if not provider_name or not api_key:
                    return {
                        "success": False,
                        "error": "Configure a provider and API key in the Summarizer tab",
                        "content": "",
                    }
                prov = get_provider(provider_name, api_key, model, custom_url)

            result: SummarizeResult = prov.summarize(content, template)

            # Save to history
            if result.success:
                self._save_summary_history(filepath, source, result, provider_name)

            return result.to_dict()

        except ValueError as e:
            return {"success": False, "error": str(e), "content": ""}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "content": ""}

    def get_summary_history(self) -> list[dict]:
        """Return past summaries from the history file."""
        history_path = Path.home() / ".cinderace-sessions" / "summary_history.json"
        if not history_path.exists():
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    # ── Internal: Summary History ─────────────────────────────────────

    def _save_summary_history(self, filepath: str, source: str,
                              result, provider_name: str) -> None:
        """Append a summary to the history file."""
        history_path = Path.home() / ".cinderace-sessions" / "summary_history.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)

        history = []
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Summary history load failed: %s", e)
                history = []

        history.append({
            "filepath": filepath,
            "session_slug": Path(filepath).stem,
            "cli_source": source,
            "provider": provider_name,
            "model": result.model,
            "tokens_used": result.tokens_used,
            "summary_preview": result.content[:200] + ("..." if len(result.content) > 200 else ""),
            "full_summary": result.content,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep last 100 summaries
        history = history[-100:]

        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save summary history: %s", e)
            # Non-fatal — summary was generated, just not persisted

    # ── Summary Export & Ingest ──────────────────────────────────────

    def export_summary_markdown(self, content: str, model: str = "") -> str | None:
        """Export a summary as a markdown file. Returns the output path."""
        config = load_config()
        output_dir = config.get("output_directory", "")
        if not output_dir:
            output_dir = os.path.join(os.path.expanduser("~"), "CinderACE-Exports")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"summary_{timestamp}.md"
        out_path = os.path.join(output_dir, filename)

        header = f"# Session Summary\n\n"
        if model:
            header += f"*Summarized by {model}*\n\n"
        header += "---\n\n"

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(header + content)
            return out_path
        except OSError as e:
            return f"Error: {str(e)}"

    def ingest_summary(self, content: str, collection: str = "general",
                       filepath: str = "") -> bool:
        """Ingest a summary into ember-memory via HTTP MCP server."""
        import requests as req

        try:
            config = load_config()
            ember_url = config.get("ember_memory_url", "http://localhost:2214").rstrip("/")
            tags = "summary,cinderace-sessions"
            if filepath:
                tags += f",{Path(filepath).stem}"
            source = "cinderace-sessions:summarizer"

            resp = req.post(
                f"{ember_url}/tools/memory_store",
                json={
                    "content": content[:8000],
                    "collection": collection,
                    "tags": tags,
                    "source": source,
                },
                timeout=30,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("ember-memory summary ingest failed: %s", e, exc_info=True)
            return False

    # ── Internal Helpers ─────────────────────────────────────────────

    def _parse_session(self, filepath: str, source: str):
        """Parse a session file based on its source CLI and file extension."""
        try:
            filepath_lower = filepath.lower()

            if source == "gemini-cli":
                # All Gemini files go through the Gemini parser (handles both JSON and JSONL)
                turns = parse_gemini_session(filepath)
                meta = gemini_extract_meta(filepath)
            elif filepath_lower.endswith("/logs.json") or "/chats/" in filepath_lower:
                # Gemini session files found by path
                turns = parse_gemini_session(filepath)
                meta = gemini_extract_meta(filepath)
            else:
                # Claude Code and Codex both use JSONL
                turns = parse_jsonl_transcript(filepath)
                meta = extract_session_meta(filepath)

            if not turns:
                return None, None
            return turns, meta

        except Exception as e:
            logger.error("Parse session failed for %s (%s): %s", filepath, source, e, exc_info=True)
            return None, None

    @staticmethod
    def _session_info_to_dict(s: SessionInfo) -> dict:
        """Convert a SessionInfo to a JSON-serializable dict."""
        return {
            "filepath": s.filepath,
            "cli_source": s.cli_source,
            "date": s.date,
            "title": s.title,
            "preview": s.preview,
            "message_count": s.message_count,
            "file_size": s.file_size,
            "mtime": s.mtime,
            "entrypoint": s.entrypoint,
            "project": s.project,
        }


def run_gui():
    """Create and run the pywebview window."""
    from cinderace_sessions.single_instance import acquire_instance_lock

    lock = acquire_instance_lock("controller")
    if not lock:
        print("CinderACE Sessions is already running.")
        return

    api = SessionsAPI()
    html = _get_html()

    window = webview.create_window(
        title="CinderACE Sessions",
        html=html,
        js_api=api,
        width=840,
        height=660,
        min_size=(700, 550),
        background_color="#050505",
        text_select=True,
    )

    # Enable native context menus: WebView2 ties AreDefaultContextMenusEnabled
    # to the debug flag, suppressing even the DOM contextmenu event when False.
    # OPEN_DEVTOOLS_IN_DEBUG=False prevents the F12 DevTools popup.
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    api._window = window
    webview.start(debug=True)


def main():
    """Entry point for the controller."""
    try:
        run_gui()
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down")
    except Exception as e:
        logger.critical("Unhandled exception in controller", exc_info=True)
        raise


if __name__ == "__main__":
    main()