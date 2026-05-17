"""CinderACE Sessions v2 — controller app (pywebview desktop GUI).

Main application window with the SessionsAPI backend exposed
to the JavaScript frontend via pywebview's bridge.
"""

from __future__ import annotations

import json
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
        return load_config()

    def save_settings(self, settings: dict) -> bool:
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

    def get_session_detail(self, filepath: str) -> dict | None:
        """Return full parsed session data for preview."""
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
            return f"Error: {str(e)}"

    # ── ember-memory Bridge ──────────────────────────────────────────

    def get_ember_status(self) -> str | None:
        """Check if ember-memory is available."""
        try:
            from ember_memory.core.backends import get_backend_v2
            from ember_memory.core.embeddings import get_embedding_provider
            backend = get_backend_v2()
            embedder = get_embedding_provider()
            if backend and embedder:
                return "library"
        except ImportError:
            pass

        try:
            import requests
            resp = requests.get("http://localhost:2214/health", timeout=2)
            if resp.status_code == 200:
                return "server"
        except Exception:
            pass

        return None

    def ingest_session(self, filepath: str, collection: str = "general", tags: str = "") -> bool:
        """Ingest a session into ember-memory."""
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

        try:
            # Try library import first
            from ember_memory.core.backends import get_backend_v2
            from ember_memory.core.embeddings import get_embedding_provider

            backend = get_backend_v2()
            embedder = get_embedding_provider()

            # Create collection if it doesn't exist
            try:
                backend.create_collection(collection, dimension=embedder.dimension())
            except Exception:
                pass

            # Store memory
            from datetime import datetime
            doc_id = f"cas_{Path(filepath).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            embedding = embedder.embed(content)
            tags_str = tags or f"cli:{source},project:{meta.slug or 'unknown'},date:{meta.first_date}"
            backend.insert(
                collection=collection,
                doc_id=doc_id,
                content=content,
                embedding=embedding,
                metadata={
                    "source": f"cinderace-sessions:{source}",
                    "tags": tags_str,
                    "ingested_at": datetime.now().isoformat(),
                },
            )
            return True

        except ImportError:
            # Fall back to HTTP API
            try:
                import requests
                import json

                resp = requests.post(
                    "http://localhost:2214/tools/memory_store",
                    json={
                        "content": content[:8000],  # Limit for API
                        "collection": collection,
                        "tags": tags or f"cli:{source},project:{meta.slug}",
                        "source": f"cinderace-sessions:{source}",
                    },
                    timeout=30,
                )
                return resp.status_code == 200
            except Exception:
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

    # ── Summarizer (stubs for Phase 5) ─────────────────────────────

    def test_summarizer_connection(self) -> bool:
        """Test the configured LLM endpoint. Returns True if reachable."""
        # Will be implemented in Phase 5
        return False

    def get_default_template(self) -> str:
        """Return the default summary template."""
        from cinderace_sessions.summarizer.template import load_template
        return load_template("default")

    def save_template(self, name: str, content: str) -> bool:
        """Save a summary template."""
        from cinderace_sessions.summarizer.template import save_template
        return save_template(name, content)

    # ── Internal Helpers ─────────────────────────────────────────────

    def _parse_session(self, filepath: str, source: str):
        """Parse a session file based on its source CLI."""
        try:
            if source == "gemini-cli":
                turns = parse_gemini_session(filepath)
                meta = gemini_extract_meta(filepath)
            else:
                # Claude Code and Codex both use JSONL
                turns = parse_jsonl_transcript(filepath)
                meta = extract_session_meta(filepath)

            if not turns:
                return None, None
            return turns, meta

        except Exception:
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

    api._window = window
    webview.start(debug=True)


def main():
    """Entry point for the controller."""
    run_gui()


if __name__ == "__main__":
    main()