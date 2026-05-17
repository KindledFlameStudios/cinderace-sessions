"""CinderACE Sessions v2 — Gemini CLI JSON session parser.

Gemini CLI stores sessions differently from Claude Code/Codex:
- logs.json: complete runtime session log (JSON array of messages)
- checkpoint-*.json: manually saved snapshots (JSON array of messages)

Messages use {role: 'user'|'model', parts: [...]} format.
Also processes tool calls and thinking blocks from the logs format.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionEntrypoint,
    SessionMeta,
    SessionStats,
    Turn,
)


def parse_gemini_session(filepath: str) -> list[Turn]:
    """Parse a Gemini CLI session file (JSON array format) into Turn objects.

    Handles both logs.json (runtime log) and checkpoint-*.json (saved snapshots).
    """
    turns: list[Turn] = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return turns

    # Data should be a list of session entries
    if not isinstance(data, list):
        return turns

    for entry in data:
        if not isinstance(entry, dict):
            continue

        role = entry.get("role", "")

        # Map Gemini's 'model' role to 'assistant'
        if role == "model":
            role = "assistant"
        elif role != "user":
            continue

        blocks = _parse_gemini_blocks(entry)
        if not blocks:
            continue

        timestamp = entry.get("timestamp", entry.get("createdAt", ""))
        turn_uuid = entry.get("id", str(uuid4()))

        turns.append(Turn(
            role=role,
            blocks=blocks,
            timestamp=timestamp,
            uuid=turn_uuid,
        ))

    return turns


def _parse_gemini_blocks(entry: dict) -> list[ContentBlock]:
    """Extract content blocks from a Gemini CLI message entry.

    Gemini uses a 'parts' array. Each part can be:
    - text: {text: "..."}
    - function_call / tool_use: {functionCall: {name: "...", args: {...}}}
    - function_response: {functionResponse: {name: "...", response: {...}}}
    - thought: {thought: True, text: "..."} (Gemini's thinking format)
    """
    blocks: list[ContentBlock] = []
    parts = entry.get("parts", [])

    if not parts:
        # Some entries use 'content' as a string directly
        content = entry.get("content", "")
        if isinstance(content, str) and content.strip():
            blocks.append(ContentBlock(type=BlockType.TEXT, text=content))
        return blocks

    if not isinstance(parts, list):
        return blocks

    for part in parts:
        if not isinstance(part, dict):
            continue

        # Thinking block
        if part.get("thought"):
            text = part.get("text", "")
            if text:
                blocks.append(ContentBlock(type=BlockType.THINKING, thinking=text))
            continue

        # Text block
        text = part.get("text", "")
        if text:
            blocks.append(ContentBlock(type=BlockType.TEXT, text=text))
            continue

        # Tool/function call
        func_call = part.get("functionCall")
        if func_call and isinstance(func_call, dict):
            name = func_call.get("name", "")
            args = func_call.get("args", {})
            if name:
                if isinstance(args, dict):
                    args_display = args
                elif isinstance(args, str):
                    args_display = {"args": args}
                else:
                    args_display = {}
                blocks.append(ContentBlock(
                    type=BlockType.TOOL_USE,
                    name=name,
                    input=args_display,
                ))
            continue

        # Function response (tool result) — skip in export, but we track it
        func_resp = part.get("functionResponse")
        if func_resp:
            # We don't include tool results in the turn blocks
            continue

    return blocks


def gemini_build_stats(turns: list[Turn]) -> SessionStats:
    """Compute stats for Gemini sessions. Same logic as JSONL build_stats."""
    # Reuse the shared stats logic
    from cinderace_sessions.parser.jsonl_parser import build_stats
    return build_stats(turns)


def gemini_extract_meta(filepath: str) -> SessionMeta:
    """Extract metadata from a Gemini CLI session file.

    Gemini doesn't store session IDs or entrypoints in the same way.
    We derive what we can and leave the rest as defaults.
    """
    meta = SessionMeta()
    filename = Path(filepath).stem

    # For logs.json, the session ID comes from the parent directory hash
    # For checkpoints, the name is in the filename
    if filename.startswith("checkpoint-"):
        meta.session_id = filename.replace("checkpoint-", "")
        meta.slug = meta.session_id
    else:
        # Use the parent directory hash as part of the ID
        parent = Path(filepath).parent.name
        meta.session_id = f"{parent}-{filename}"
        meta.slug = parent

    meta.entrypoint = SessionEntrypoint.UNKNOWN
    meta.first_date = ""

    try:
        stat = Path(filepath).stat()
        # Use file modification time as a fallback date
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime)
        meta.first_date = mtime.strftime("%Y-%m-%d")

        # Try to get the actual first date from the session data
        read_size = min(stat.st_size, 65536)  # First 64KB
        with open(filepath, "r", encoding="utf-8") as f:
            chunk = f.read(read_size)

        try:
            data = json.loads(chunk)
            if isinstance(data, list) and data:
                first = data[0]
                ts = first.get("timestamp", first.get("createdAt", ""))
                if isinstance(ts, str) and len(ts) >= 10:
                    meta.first_date = ts[:10]
        except json.JSONDecodeError:
            pass

    except OSError:
        pass

    return meta