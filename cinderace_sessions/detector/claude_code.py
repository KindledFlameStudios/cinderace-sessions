"""CinderACE Sessions v2 — Claude Code session detector.

Detects sessions stored at ~/.claude/projects/{workspace-slug}/*.jsonl
with filtering for command stubs and entrypoint types.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.parser.base import SessionInfo
from cinderace_sessions.parser.jsonl_parser import extract_session_meta, read_preview, read_custom_title

logger = logging.getLogger(__name__)


class ClaudeCodeDetector(CLIDetector):
    """Detector for Claude Code session files."""

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    @property
    def color(self) -> str:
        return "#FF7820"

    def detect(self) -> bool:
        base_dir = Path.home() / ".claude" / "projects"
        self._available = base_dir.exists() and base_dir.is_dir()
        return self._available

    def find_sessions(self) -> list[SessionInfo]:
        if not self._available and not self.detect():
            return []

        base_dir = Path.home() / ".claude" / "projects"
        sessions: list[SessionInfo] = []

        try:
            for project_dir in base_dir.iterdir():
                if not project_dir.is_dir():
                    continue

                project_slug = project_dir.name

                for jsonl_file in project_dir.glob("*.jsonl"):
                    try:
                        info = self._build_session_info(str(jsonl_file), project_slug)
                        if info:
                            sessions.append(info)
                    except Exception:
                        logger.debug("Failed to build session info for %s", jsonl_file, exc_info=True)
                        continue
        except OSError:
            pass

        return sessions

    def _build_session_info(self, filepath: str, project_slug: str) -> SessionInfo | None:
        """Build SessionInfo from a single JSONL file."""
        try:
            stat = Path(filepath).stat()
        except OSError:
            return None

        # Skip command stubs
        if self._is_command_stub(filepath):
            return None

        meta = extract_session_meta(filepath)
        title = read_custom_title(filepath)
        preview = read_preview(filepath)

        # Count messages from file size heuristic
        # (full parse is deferred until user selects a session)
        message_count = self._estimate_message_count(filepath)

        return SessionInfo(
            filepath=filepath,
            cli_source=self.name,
            date=meta.first_date,
            title=title or meta.slug or meta.session_id,
            preview=preview or "(no preview)",
            message_count=message_count,
            file_size=stat.st_size,
            mtime=stat.st_mtime,
            entrypoint=meta.entrypoint.value,
            project=project_slug,
        )

    def _is_command_stub(self, filepath: str) -> bool:
        """Check if a session is a VS Code local-command stub.

        These are tiny sessions for inline commands that start with
        '<local-command-caveat>' in the first user message.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                chunk = f.read(4096)
            return "<local-command-caveat>" in chunk
        except OSError:
            return False

    def _estimate_message_count(self, filepath: str) -> int:
        """Quick estimate of message count without full parsing.

        Counts lines with '"type":"user"' or '"type":"assistant"' patterns.
        """
        count = 0
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if '"type":"user"' in line or '"type":"assistant"' in line:
                        count += 1
        except OSError:
            pass
        return count