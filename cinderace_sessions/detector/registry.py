"""CinderACE Sessions v2 — detector registry.

Manages built-in and custom CLI detectors. Provides a unified scan_all()
method that discovers sessions from all enabled sources.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from cinderace_sessions.config import load_custom_clis, save_custom_clis
from cinderace_sessions.detector.base import CLIDetector
from cinderace_sessions.detector.claude_code import ClaudeCodeDetector
from cinderace_sessions.detector.codex import CodexDetector
from cinderace_sessions.detector.forge import ForgeDetector
from cinderace_sessions.detector.gemini_cli import GeminiCLIDetector
from cinderace_sessions.parser.base import SessionInfo


class CustomCLIDetector(CLIDetector):
    """A user-defined CLI detector that scans a specific directory."""

    def __init__(self, name: str, display_name: str, directory: str,
                 fmt: str, color: str, enabled: bool = True):
        super().__init__()
        self._name = name
        self._display_name = display_name
        self._directory = directory
        self._format = fmt
        self._color = color
        self._enabled = enabled

    @property
    def name(self) -> str:
        return f"custom-{self._name.lower().replace(' ', '-')}"

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def color(self) -> str:
        return self._color

    @property
    def directory(self) -> str:
        return self._directory

    @property
    def format(self) -> str:
        return self._format

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def detect(self) -> bool:
        dir_path = Path(self._directory).expanduser()
        self._available = dir_path.exists() and dir_path.is_dir()
        return self._available

    def find_sessions(self) -> list[SessionInfo]:
        if not self._enabled:
            return []
        if not self._available and not self.detect():
            return []

        dir_path = Path(self._directory).expanduser()
        sessions: list[SessionInfo] = []

        # Scan based on format
        if self._format == "jsonl":
            pattern = "*.jsonl"
        elif self._format == "json":
            pattern = "*.json"
        elif self._format == "markdown":
            pattern = "*.md"
        elif self._format == "text":
            pattern = "*.txt"
        else:
            pattern = "*.jsonl"  # default fallback

        try:
            for session_file in dir_path.rglob(pattern):
                try:
                    stat = session_file.stat()
                    sessions.append(SessionInfo(
                        filepath=str(session_file),
                        cli_source=self.name,
                        date="",  # Extracted on demand
                        title=session_file.stem,
                        preview="(custom CLI session)",
                        message_count=0,
                        file_size=stat.st_size,
                        mtime=stat.st_mtime,
                        entrypoint="unknown",
                        project=self._display_name,
                    ))
                except PermissionError:
                    logger.warning("Permission denied accessing %s", session_file)
                    continue
                except OSError as e:
                    logger.debug("Skipping %s: %s", session_file, e)
                    continue
        except PermissionError:
            logger.warning("Permission denied scanning directory %s", dir_path)
        except OSError as e:
            logger.warning("Error scanning custom CLI directory %s: %s", dir_path, e)

        return sessions


class DetectorRegistry:
    """Manages all CLI detectors and provides unified session scanning."""

    def __init__(self):
        self._built_in: list[CLIDetector] = [
            ClaudeCodeDetector(),
            CodexDetector(),
            ForgeDetector(),
            GeminiCLIDetector(),
        ]
        self._custom: list[CustomCLIDetector] = []
        self._load_custom_clis()

    def _load_custom_clis(self):
        """Load custom CLI registrations from config."""
        clis = load_custom_clis()
        self._custom = []
        for cli in clis:
            detector = CustomCLIDetector(
                name=cli.get("name", "Unknown"),
                display_name=cli.get("name", "Unknown"),
                directory=cli.get("directory", ""),
                fmt=cli.get("format", "jsonl"),
                color=cli.get("color", "#888888"),
                enabled=cli.get("enabled", True),
            )
            self._custom.append(detector)

    def reload_custom_clis(self):
        """Reload custom CLIs from config (e.g. after settings change)."""
        self._load_custom_clis()

    @property
    def all_detectors(self) -> list[CLIDetector]:
        """All detectors (built-in + custom, enabled only)."""
        return [d for d in self._built_in if d.is_available] + \
               [d for d in self._custom if d.enabled]

    @property
    def all_detectors_with_status(self) -> list[dict[str, Any]]:
        """All detectors with availability info for the CLI Status tab."""
        result = []
        for d in self._built_in:
            d.detect()  # Refresh availability
            result.append({
                "name": d.name,
                "display_name": d.display_name,
                "color": d.color,
                "available": d.is_available,
                "custom": False,
            })
        for d in self._custom:
            d.detect()
            result.append({
                "name": d.name,
                "display_name": d.display_name,
                "color": d.color,
                "available": d.is_available,
                "custom": True,
                "directory": d.directory,
                "format": d.format,
                "enabled": d.enabled,
            })
        return result

    def scan_all(self) -> list[SessionInfo]:
        """Run all enabled detectors and return a unified session list.

        Calls detect() on each detector before scanning to ensure
        availability is current. Skips detectors that aren't found
        and custom detectors that are disabled.
        Results are sorted by modification time (newest first).
        """
        all_sessions: list[SessionInfo] = []

        for detector in self._built_in:
            try:
                detector.detect()
                if not detector.is_available:
                    continue
                sessions = detector.find_sessions()
                all_sessions.extend(sessions)
            except PermissionError as e:
                logger.warning("Permission error scanning %s: %s", detector.display_name, e)
                continue
            except Exception as e:
                logger.warning("Error scanning %s: %s: %s", detector.display_name, type(e).__name__, e)
                continue

        for detector in self._custom:
            try:
                if not detector.enabled:
                    continue
                detector.detect()
                if not detector.is_available:
                    continue
                sessions = detector.find_sessions()
                all_sessions.extend(sessions)
            except PermissionError as e:
                logger.warning("Permission error scanning custom CLI %s: %s", detector.display_name, e)
                continue
            except Exception as e:
                logger.warning("Error scanning custom CLI %s: %s: %s", detector.display_name, type(e).__name__, e)
                continue

        # Sort by mtime descending (newest first)
        all_sessions.sort(key=lambda s: s.mtime, reverse=True)
        return all_sessions

    def add_custom_cli(self, name: str, directory: str, fmt: str,
                       color: str = "#888888", enabled: bool = True) -> bool:
        """Register a custom CLI and persist it to config."""
        clis = load_custom_clis()

        # Check for duplicate name
        for existing in clis:
            if existing.get("name", "").lower() == name.lower():
                return False  # Name already exists

        clis.append({
            "name": name,
            "directory": directory,
            "format": fmt,
            "color": color,
            "enabled": enabled,
        })

        if save_custom_clis(clis):
            self._load_custom_clis()
            return True
        return False

    def remove_custom_cli(self, name: str) -> bool:
        """Remove a custom CLI registration by name."""
        clis = load_custom_clis()
        original_count = len(clis)
        clis = [c for c in clis if c.get("name", "").lower() != name.lower()]

        if len(clis) == original_count:
            return False  # Not found

        if save_custom_clis(clis):
            self._load_custom_clis()
            return True
        return False