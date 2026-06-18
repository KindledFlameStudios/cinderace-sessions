"""CinderACE Sessions v2 — Fire Forge session detector.

Detects sessions stored in the Fire Forge SQLite database (forge.db).
Reads sessions, messages, and their structured parts (text, reasoning,
tool calls, tool results) and exposes them as SessionInfo objects.

The forge.db lives at ~/.local/share/forge/forge.db by default.
"""

from __future__ import annotations

import logging
from contextlib import closing
from pathlib import Path

from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.parser.base import SessionInfo

logger = logging.getLogger(__name__)

# Default forge database location
FORGE_DB_PATH = Path.home() / ".local" / "share" / "forge" / "forge.db"


class ForgeDetector(CLIDetector):
    """Detector for Fire Forge session database."""

    @property
    def name(self) -> str:
        return "fire-forge"

    @property
    def display_name(self) -> str:
        return "Fire Forge"

    @property
    def color(self) -> str:
        return "#E85D2C"

    def detect(self) -> bool:
        self._available = FORGE_DB_PATH.exists() and FORGE_DB_PATH.is_file()
        return self._available

    def find_sessions(self) -> list[SessionInfo]:
        if not self._available and not self.detect():
            return []

        try:
            import sqlite3
            with closing(sqlite3.connect(str(FORGE_DB_PATH))) as conn:
                # Handle emoji and other non-ASCII in titles (forge stores them raw)
                conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Only top-level sessions (no parent), ordered by most recent first
                cursor.execute(
                    "SELECT id, title, message_count, identity, created_at "
                    "FROM sessions "
                    "WHERE parent_session_id IS NULL "
                    "ORDER BY created_at DESC"
                )
                rows = cursor.fetchall()

                sessions = []
                for row in rows:
                    # Convert identity field to a clean source label
                    identity = row["identity"] or "unknown"

                    # Forge stores timestamps in seconds (not milliseconds)
                    created_sec = row["created_at"] or 0
                    created_iso = ""
                    if created_sec > 0:
                        try:
                            from datetime import datetime
                            created_iso = datetime.fromtimestamp(
                                created_sec
                            ).strftime("%Y-%m-%d")
                        except (OSError, ValueError):
                            pass

                    sessions.append(SessionInfo(
                        filepath=f"{FORGE_DB_PATH}::{row['id']}",
                        cli_source=f"forge-{identity}",
                        date=created_iso,
                        title=row["title"] or "(untitled)",
                        preview="",  # Populated on demand via get_session_detail
                        message_count=row["message_count"] or 0,
                        file_size=0,  # Single database, not per-file
                        mtime=float(created_sec) if created_sec else 0.0,
                        entrypoint="forge",
                        project=identity,
                    ))

                return sessions

        except Exception:
            logger.debug("Failed to read forge.db", exc_info=True)
            return []