"""CinderACE Sessions v2 — Markdown conversation log parser.

Best-effort parsing of markdown-formatted conversation logs.
Detects common patterns: **User**: / **Assistant**: prefixes,
blockquote lines, code blocks, etc.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionMeta,
    SessionStats,
    Turn,
)


# Common patterns for role markers in markdown conversations
_USER_PATTERNS = [
    re.compile(r"^\*\*User\*\*:?[\s]*(.*)", re.IGNORECASE),
    re.compile(r"^# User[:\s]*(.*)", re.IGNORECASE),
    re.compile(r"^User:[:\s]*(.*)", re.IGNORECASE),
    re.compile(r"^>+[\s]*User:[:\s]*(.*)", re.IGNORECASE),
]

_ASSISTANT_PATTERNS = [
    re.compile(r"^\*\*Assistant\*\*:?[\s]*(.*)", re.IGNORECASE),
    re.compile(r"^\*\*AI\*\*:?[\s]*(.*)", re.IGNORECASE),
    re.compile(r"^# Assistant[:\s]*(.*)", re.IGNORECASE),
    re.compile(r"^Assistant:[:\s]*(.*)", re.IGNORECASE),
    re.compile(r"^>+[\s]*Assistant:[:\s]*(.*)", re.IGNORECASE),
]


def parse_markdown_conversation(filepath: str) -> list[Turn]:
    """Parse a markdown conversation log into Turn objects.

    Uses pattern matching to identify role markers. Lines between
    role markers are attributed to the current speaker. Lines that
    don't match any role pattern are attributed to the most recent
    speaker. If no speaker is set, defaults to 'user'.
    """
    turns: list[Turn] = []
    current_role = "user"
    current_blocks: list[ContentBlock] = []
    current_timestamp = ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return turns

    for line in content.split("\n"):
        # Check for role markers
        matched = False

        for pattern in _USER_PATTERNS:
            m = pattern.match(line)
            if m:
                # Flush previous turn
                if current_blocks:
                    turns.append(Turn(
                        role=current_role,
                        blocks=current_blocks,
                        timestamp=current_timestamp,
                        uuid=str(uuid4()),
                    ))
                current_role = "user"
                remainder = m.group(1).strip()
                current_blocks = []
                if remainder:
                    current_blocks.append(ContentBlock(type=BlockType.TEXT, text=remainder))
                matched = True
                break

        if matched:
            continue

        for pattern in _ASSISTANT_PATTERNS:
            m = pattern.match(line)
            if m:
                # Flush previous turn
                if current_blocks:
                    turns.append(Turn(
                        role=current_role,
                        blocks=current_blocks,
                        timestamp=current_timestamp,
                        uuid=str(uuid4()),
                    ))
                current_role = "assistant"
                remainder = m.group(1).strip()
                current_blocks = []
                if remainder:
                    current_blocks.append(ContentBlock(type=BlockType.TEXT, text=remainder))
                matched = True
                break

        if matched:
            continue

        # Regular content line — attribute to current speaker
        text = line.strip()
        if text:
            current_blocks.append(ContentBlock(type=BlockType.TEXT, text=text))

    # Flush final turn
    if current_blocks:
        turns.append(Turn(
            role=current_role,
            blocks=current_blocks,
            timestamp=current_timestamp,
            uuid=str(uuid4()),
        ))

    return turns


def markdown_extract_meta(filepath: str) -> SessionMeta:
    """Extract metadata from a markdown conversation file."""
    meta = SessionMeta()
    meta.session_id = Path(filepath).stem or "markdown-session"
    meta.entrypoint = SessionEntrypoint.UNKNOWN

    try:
        stat = Path(filepath).stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        meta.first_date = mtime.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        pass

    return meta