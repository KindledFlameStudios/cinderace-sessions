"""CinderACE Sessions v2 — Gemini CLI session detector.

Detects sessions stored at ~/.gemini/tmp/<project_hash>/logs.json
and ~/.gemini/tmp/<project_hash>/chats/ (session-*.json, session-*.jsonl,
and nested UUID directories).
Also scans for checkpoints.

Supports GEMINI_CLI_HOME env var override.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.parser.base import SessionInfo
from cinderace_sessions.parser.gemini_parser import gemini_extract_meta

# Maximum file size to fully load for preview extraction (32MB)
MAX_PREVIEW_SIZE = 32 * 1024 * 1024


class GeminiCLIDetector(CLIDetector):
    """Detector for Google Gemini CLI session files."""

    @property
    def name(self) -> str:
        return "gemini-cli"

    @property
    def display_name(self) -> str:
        return "Gemini CLI"

    @property
    def color(self) -> str:
        return "#D94444"

    @property
    def base_dir(self) -> Path:
        """Get the Gemini CLI home directory, respecting GEMINI_CLI_HOME env var."""
        gemini_home = os.environ.get("GEMINI_CLI_HOME")
        if gemini_home:
            return Path(gemini_home)
        return Path.home() / ".gemini"

    def detect(self) -> bool:
        tmp_dir = self.base_dir / "tmp"
        self._available = tmp_dir.exists() and tmp_dir.is_dir()
        return self._available

    def find_sessions(self) -> list[SessionInfo]:
        if not self._available and not self.detect():
            return []

        tmp_dir = self.base_dir / "tmp"
        sessions: list[SessionInfo] = []
        seen_paths: set[str] = set()  # Deduplicate by filepath

        try:
            for project_dir in tmp_dir.iterdir():
                if not project_dir.is_dir():
                    continue

                project_hash = project_dir.name

                # Collect candidate files (deduplicated)
                candidates: list[tuple[str, str]] = []  # (filepath, source_type)

                # logs.json — the runtime session log
                logs_file = project_dir / "logs.json"
                if logs_file.exists():
                    candidates.append((str(logs_file), "logs"))

                # checkpoints/
                checkpoint_dir = project_dir / "checkpoints"
                if checkpoint_dir.exists():
                    for cp_file in checkpoint_dir.glob("checkpoint-*.json"):
                        candidates.append((str(cp_file), "checkpoint"))

                # chats/ — all session formats
                chats_dir = project_dir / "chats"
                if chats_dir.exists():
                    # Top-level session .json files
                    for f in chats_dir.glob("session-*.json"):
                        candidates.append((str(f), "chat"))

                    # Top-level session .jsonl files
                    for f in chats_dir.glob("session-*.jsonl"):
                        candidates.append((str(f), "chat"))

                    # Nested UUID directories
                    for uuid_dir in chats_dir.iterdir():
                        if not uuid_dir.is_dir() or uuid_dir.name.startswith("."):
                            continue
                        for nested in uuid_dir.glob("*.json"):
                            if nested.stat().st_size > 100:
                                candidates.append((str(nested), "chat"))
                        for nested in uuid_dir.glob("*.jsonl"):
                            if nested.stat().st_size > 100:
                                candidates.append((str(nested), "chat"))

                # Build session info for each unique file
                for filepath, source_type in candidates:
                    if filepath in seen_paths:
                        continue
                    seen_paths.add(filepath)

                    try:
                        info = self._build_session_info(filepath, project_hash, source_type)
                        if info:
                            sessions.append(info)
                    except Exception:
                        logger.debug("Failed to build session info for %s", filepath, exc_info=True)
                        pass

        except OSError:
            pass

        return sessions

    def _build_session_info(self, filepath: str, project_hash: str, source_type: str) -> SessionInfo | None:
        """Build SessionInfo from a Gemini CLI session file."""
        try:
            stat = Path(filepath).stat()
        except OSError:
            return None

        file_size = stat.st_size
        meta = gemini_extract_meta(filepath)
        preview = self._read_gemini_preview(filepath) if file_size < MAX_PREVIEW_SIZE else "(large session)"

        # Derive a friendly project name
        project_display = f"gemini-{project_hash[:8]}"
        project_root_file = Path(filepath).parent.parent / ".project_root"
        if project_root_file.exists():
            try:
                project_name = project_root_file.read_text(encoding="utf-8").strip()
                if project_name:
                    project_display = project_name
            except OSError:
                pass

        return SessionInfo(
            filepath=filepath,
            cli_source=self.name,
            date=meta.first_date,
            title=meta.session_id or Path(filepath).stem,
            preview=preview or "(no preview)",
            message_count=0,
            file_size=file_size,
            mtime=stat.st_mtime,
            entrypoint="cli",
            project=project_display,
        )

    def _read_gemini_preview(self, filepath: str, max_chars: int = 100) -> str:
        """Read the first user message from a Gemini session file for preview.

        Handles both formats:
        - logs.json: [{type, message, timestamp}]
        - Chat files: {messages: [{type, content, ...}]}
        """
        try:
            file_size = Path(filepath).stat().st_size
            if file_size > MAX_PREVIEW_SIZE:
                return ""

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, MemoryError):
            return ""

        import re

        def clean_text(text: str) -> str:
            text = re.sub(r"<[^>]*>", "", text).strip()
            return text[:max_chars] if text else ""

        if isinstance(data, dict):
            # Chat file format: {messages: [...]}
            messages = data.get("messages", [])
            for msg in messages:
                if not isinstance(msg, dict) or msg.get("type") != "user":
                    continue
                content = msg.get("content", "")
                if isinstance(content, str):
                    result = clean_text(content)
                    if result:
                        return result
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text", "")
                            if text and not part.get("thought"):
                                result = clean_text(text)
                                if result:
                                    return result
            return ""

        elif isinstance(data, list):
            # logs.json format: [{type, message}]
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "user":
                    continue
                content = entry.get("message", "")
                if isinstance(content, str):
                    result = clean_text(content)
                    if result:
                        return result
            return ""

        return ""