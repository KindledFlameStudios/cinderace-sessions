"""CinderACE Sessions v2 — JSONL (JSON Lines) export renderer.

One JSON object per turn, with a metadata header line.
"""

from __future__ import annotations

import json
from datetime import datetime

from cinderace_sessions.parser.base import (
    BlockType,
    RenderOptions,
    SessionMeta,
    SessionStats,
    Turn,
    clean_options,
)


def build_jsonl(
    turns: list[Turn],
    meta: SessionMeta,
    options: RenderOptions,
) -> str:
    """Export turns as JSONL — one JSON object per turn.

    First line is a metadata record. Each subsequent line is a turn.
    """
    lines: list[str] = []

    # First line: metadata
    lines.append(json.dumps({
        "type": "meta",
        "sessionId": meta.session_id,
        "slug": meta.slug,
        "date": meta.first_date,
        "exportedBy": "CinderACE Sessions",
        "exportedAt": datetime.now().isoformat(),
    }, ensure_ascii=False))

    for turn in turns:
        entry: dict = {
            "role": turn.role,
            "timestamp": turn.timestamp,
            "uuid": turn.uuid,
            "text": "\n".join(
                b.text for b in turn.blocks if b.type == BlockType.TEXT and b.text
            ),
        }

        if options.include_thinking:
            thinking = [b.thinking for b in turn.blocks if b.type == BlockType.THINKING and b.thinking]
            if thinking:
                entry["thinking"] = thinking

        if options.include_tools:
            tools = [
                {"name": b.name, "input": b.input}
                for b in turn.blocks if b.type == BlockType.TOOL_USE and b.name
            ]
            if tools:
                entry["tools"] = tools

        # Skip empty entries (no text, no thinking, no tools)
        if not entry.get("text") and not entry.get("thinking") and not entry.get("tools"):
            continue

        lines.append(json.dumps(entry, ensure_ascii=False))

    return "\n".join(lines)


def render_jsonl(
    turns: list[Turn],
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a session as JSONL."""
    if options is None:
        options = RenderOptions()
    return build_jsonl(turns, meta, options)


def render_jsonl_clean(
    turns: list[Turn],
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a clean JSONL export (thinking, no tools)."""
    if options is None:
        options = RenderOptions()
    return build_jsonl(turns, meta, clean_options(options))