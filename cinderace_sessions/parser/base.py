"""CinderACE Sessions v2 — core data types for session parsing and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Content blocks ────────────────────────────────────────────────────

class BlockType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"


@dataclass
class ContentBlock:
    """A single content block within a message."""
    type: BlockType
    text: str | None = None
    thinking: str | None = None
    name: str | None = None          # tool name for tool_use blocks
    input: dict | None = None         # tool input for tool_use blocks


# ── Parsed session structure ──────────────────────────────────────────

@dataclass
class Turn:
    """A parsed conversation turn (one user or assistant message)."""
    role: str              # 'user' or 'assistant'
    blocks: list[ContentBlock]
    timestamp: str
    uuid: str = ""


@dataclass
class SessionStats:
    """Statistics computed from parsed turns."""
    user_messages: int = 0
    assistant_messages: int = 0
    thinking_blocks: int = 0
    tool_calls: int = 0
    user_chars: int = 0
    assistant_chars: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None


class SessionEntrypoint(str, Enum):
    CLI = "cli"
    VSCODE = "claude-vscode"
    UNKNOWN = "unknown"


@dataclass
class SessionMeta:
    """Metadata extracted from the first records of a session file."""
    session_id: str = ""
    slug: str = ""
    first_date: str = ""           # YYYY-MM-DD
    entrypoint: SessionEntrypoint = SessionEntrypoint.UNKNOWN


# ── Export / render options ────────────────────────────────────────────

class ExportFormat(str, Enum):
    MD = "md"
    HTML = "html"
    JSON = "json"
    JSONL = "jsonl"
    ZIP = "zip"


class HtmlTheme(str, Enum):
    EMBER = "ember"
    DARK = "dark"
    LIGHT = "light"


@dataclass
class RenderOptions:
    """Options controlling how sessions are rendered for export."""
    include_thinking: bool = True
    include_tools: bool = True
    user_label: str = "User"
    assistant_label: str = "Assistant"
    user_emoji: str = ""
    assistant_emoji: str = ""


def clean_options(options: RenderOptions) -> RenderOptions:
    """Return a copy of options with thinking=True, tools=False ('clean' mode)."""
    return RenderOptions(
        include_thinking=True,
        include_tools=False,
        user_label=options.user_label,
        assistant_label=options.assistant_label,
        user_emoji=options.user_emoji,
        assistant_emoji=options.assistant_emoji,
    )


# ── Session summary (for detector results) ───────────────────────────

@dataclass
class SessionInfo:
    """Lightweight session metadata returned by detectors for the session list."""
    filepath: str
    cli_source: str              # 'claude-code', 'codex', 'gemini-cli', or custom name
    date: str = ""               # YYYY-MM-DD
    title: str = ""              # custom title or first user message preview
    preview: str = ""            # first user message preview text (truncated)
    message_count: int = 0
    file_size: int = 0           # bytes
    mtime: float = 0.0           # modification time for sorting
    entrypoint: str = "unknown"
    project: str = ""            # project slug or name