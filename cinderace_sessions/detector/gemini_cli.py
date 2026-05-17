"""CinderACE Sessions v2 — Gemini CLI session detector.

Detects sessions stored at ~/.gemini/tmp/<project_hash>/logs.json
and ~/.gemini/tmp/<project_hash>/checkpoints/checkpoint-*.json
Also scans ~/.gemini/tmp/<project_hash>/chats/ for additional session files.
Supports GEMINI_CLI_HOME env var override.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.parser.base import SessionInfo
from cinderace_sessions.parser.gemini_parser import gemini_extract_meta


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

        try:
            # Each subdirectory of tmp is a project hash
            for project_dir in tmp_dir.iterdir():
                if not project_dir.is_dir():
                    continue

                project_hash = project_dir.name

                # logs.json — the runtime session log
                logs_file = project_dir / "logs.json"
                if logs_file.exists():
                    try:
                        info = self._build_session_info(str(logs_file), project_hash, "logs")
                        if info:
                            sessions.append(info)
                    except Exception:
                        pass

                # checkpoints/ — manually saved snapshots
                checkpoint_dir = project_dir / "checkpoints"
                if checkpoint_dir.exists():
                    for cp_file in checkpoint_dir.glob("checkpoint-*.json"):
                        try:
                            info = self._build_session_info(str(cp_file), project_hash, "checkpoint")
                            if info:
                                sessions.append(info)
                        except Exception:
                            pass

                # chats/ — additional session files
                chats_dir = project_dir / "chats"
                if chats_dir.exists():
                    for chat_file in chats_dir.glob("*.json"):
                        try:
                            info = self._build_session_info(str(chat_file), project_hash, "chat")
                            if info:
                                sessions.append(info)
                        except Exception:
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

        meta = gemini_extract_meta(filepath)
        preview = self._read_gemini_preview(filepath)

        # Display name for the project
        project_display = f"gemini-{project_hash[:8]}"

        return SessionInfo(
            filepath=filepath,
            cli_source=self.name,
            date=meta.first_date,
            title=meta.session_id or Path(filepath).stem,
            preview=preview or "(no preview)",
            message_count=0,  # Will count on demand
            file_size=stat.st_size,
            mtime=stat.st_mtime,
            entrypoint="cli",
            project=project_display,
        )

    def _read_gemini_preview(self, filepath: str, max_chars: int = 100) -> str:
        """Read the first user message from a Gemini JSON session for preview."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return ""

        if not isinstance(data, list):
            return ""

        for entry in data:
            if not isinstance(entry, dict):
                continue
            if entry.get("role") != "user":
                continue

            parts = entry.get("parts", [])
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text", "")
                    if text and not part.get("thought"):
                        import re
                        text = re.sub(r"<[^>]*>", "", text).strip()
                        if text:
                            return text[:max_chars]

        return ""