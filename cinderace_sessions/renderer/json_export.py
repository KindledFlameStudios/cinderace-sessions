"""CinderACE Sessions v2 — JSON structured export renderer."""

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


def build_json(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions,
) -> str:
    """Export turns as structured JSON with metadata and stats."""
    doc = {
        "meta": {
            "sessionId": meta.session_id,
            "slug": meta.slug,
            "date": meta.first_date,
            "firstTimestamp": stats.first_timestamp,
            "lastTimestamp": stats.last_timestamp,
            "exportedBy": "CinderACE Sessions",
            "exportedAt": datetime.now().isoformat(),
        },
        "stats": {
            "userMessages": stats.user_messages,
            "assistantMessages": stats.assistant_messages,
            "thinkingBlocks": stats.thinking_blocks,
            "toolCalls": stats.tool_calls,
            "userChars": stats.user_chars,
            "assistantChars": stats.assistant_chars,
        },
        "settings": {
            "userLabel": options.user_label,
            "assistantLabel": options.assistant_label,
        },
        "turns": [],
    }

    for turn in turns:
        turn_data: dict = {
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
                turn_data["thinking"] = thinking

        if options.include_tools:
            tools = [
                {"name": b.name, "input": b.input}
                for b in turn.blocks if b.type == BlockType.TOOL_USE and b.name
            ]
            if tools:
                turn_data["tools"] = tools

        doc["turns"].append(turn_data)

    return json.dumps(doc, indent=2, ensure_ascii=False)


def render_json(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a session as JSON."""
    if options is None:
        options = RenderOptions()
    return build_json(turns, stats, meta, options)


def render_json_clean(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a clean JSON export (thinking, no tools)."""
    if options is None:
        options = RenderOptions()
    return build_json(turns, stats, meta, clean_options(options))