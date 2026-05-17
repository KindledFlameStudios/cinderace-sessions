"""CinderACE Sessions v2 — plain text conversation parser.

Very loose parsing: splits on common delimiters (blank lines, ---, ===)
and assigns alternating user/assistant roles. Each chunk becomes a Turn
with a single text block.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionEntrypoint,
    SessionMeta,
    Turn,
)

# Delimiter patterns
_DELIMITERS = re.compile(r"^(---+|===+|\*\*\*+)\s*$")


def parse_text_conversation(filepath: str) -> list[Turn]:
    """Parse a plain text conversation log into Turn objects.

    Splits on blank lines and horizontal rule patterns. Alternating
    chunks are assigned user/assistant roles.
    """
    turns: list[Turn] = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return turns

    # Split into chunks
    chunks: list[str] = []
    current_lines: list[str] = []

    for line in content.split("\n"):
        if _DELIMITERS.match(line.strip()) or (not line.strip() and current_lines):
            chunk = "\n".join(current_lines).strip()
            if chunk:
                chunks.append(chunk)
            current_lines = []
        else:
            current_lines.append(line)

    # Flush remaining
    if current_lines:
        chunk = "\n".join(current_lines).strip()
        if chunk:
            chunks.append(chunk)

    # Assign alternating roles
    for i, chunk in enumerate(chunks):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append(Turn(
            role=role,
            blocks=[ContentBlock(type=BlockType.TEXT, text=chunk)],
            timestamp="",
            uuid=str(uuid4()),
        ))

    return turns


def text_extract_meta(filepath: str) -> SessionMeta:
    """Extract metadata from a text conversation file."""
    meta = SessionMeta()
    p = Path(filepath)
    meta.session_id = p.stem
    meta.entrypoint = SessionEntrypoint.UNKNOWN

    try:
        stat = p.stat()
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime)
        meta.first_date = mtime.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        pass

    return meta