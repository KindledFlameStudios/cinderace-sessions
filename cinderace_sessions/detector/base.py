"""CinderACE Sessions v2 — base CLI detector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from cinderace_sessions.parser.base import SessionInfo


class CLIDetector(ABC):
    """Abstract base class for CLI session detectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this CLI (e.g. 'claude-code', 'codex')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for display (e.g. 'Claude Code')."""
        ...

    @property
    @abstractmethod
    def color(self) -> str:
        """Badge color for this CLI source (hex, e.g. '#FF7820')."""
        ...

    @abstractmethod
    def detect(self) -> bool:
        """Check if this CLI's session directory exists on disk."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this CLI's sessions were found on the system."""
        return self._available

    @abstractmethod
    def find_sessions(self) -> list[SessionInfo]:
        """Find all available sessions for this CLI.

        Returns a list of SessionInfo objects with file paths and metadata.
        """
        ...

    def __init__(self):
        self._available = False