"""CinderACE Sessions v2 — Codex CLI session detector.

Detects sessions stored at ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
Also checks ~/.codex/history.jsonl for command history.
Supports CODEX_HOME env var override.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.parser.base import SessionInfo
from cinderace_sessions.parser.jsonl_parser import extract_session_meta, read_preview


class CodexDetector(CLIDetector):
    """Detector for OpenAI Codex CLI session files."""

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex"

    @property
    def color(self) -> str:
        return "#4A90D9"

    @property
    def base_dir(self) -> Path:
        """Get the Codex home directory, respecting CODEX_HOME env var."""
        codex_home = os.environ.get("CODEX_HOME")
        if codex_home:
            return Path(codex_home)
        return Path.home() / ".codex"

    def detect(self) -> bool:
        sessions_dir = self.base_dir / "sessions"
        self._available = sessions_dir.exists() and sessions_dir.is_dir()
        return self._available

    def find_sessions(self) -> list[SessionInfo]:
        if not self._available and not self.detect():
            return []

        sessions_dir = self.base_dir / "sessions"
        sessions: list[SessionInfo] = []

        try:
            # Walk YYYY/MM/DD directory structure
            for jsonl_file in sessions_dir.rglob("rollout-*.jsonl"):
                try:
                    info = self._build_session_info(str(jsonl_file))
                    if info:
                        sessions.append(info)
                except Exception:
                    continue
        except OSError:
            pass

        return sessions

    def _build_session_info(self, filepath: str) -> SessionInfo | None:
        """Build SessionInfo from a Codex rollout file."""
        try:
            stat = Path(filepath).stat()
        except OSError:
            return None

        meta = extract_session_meta(filepath)
        preview = read_preview(filepath)

        # Extract date from the directory structure (YYYY/MM/DD pattern)
        parts = Path(filepath).parts
        date_from_path = ""
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].isdigit() and len(parts[i]) == 4:  # Year
                if i + 2 < len(parts):
                    month = parts[i + 1] if parts[i + 1].isdigit() else ""
                    day = parts[i + 2].split("-")[0] if i + 2 < len(parts) else ""
                    if month and day:
                        date_from_path = f"{parts[i]}-{month.zfill(2)}-{day.zfill(2)}"
                break

        # Derive project from the filename (Codex doesn't use project slugs the same way)
        project = "codex"

        return SessionInfo(
            filepath=filepath,
            cli_source=self.name,
            date=meta.first_date or date_from_path,
            title=meta.session_id,
            preview=preview or "(no preview)",
            message_count=0,  # Will count on demand
            file_size=stat.st_size,
            mtime=stat.st_mtime,
            entrypoint="cli",
            project=project,
        )