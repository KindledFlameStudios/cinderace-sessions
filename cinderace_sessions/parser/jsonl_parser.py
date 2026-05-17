"""CinderACE Sessions v2 — JSONL session parser.

Parses JSONL session files used by Claude Code, Codex, and any CLI
that stores conversations as newline-delimited JSON records.

Ported from the TypeScript parser.ts with the same logic and edge cases.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionEntrypoint,
    SessionMeta,
    SessionStats,
    Turn,
)


def parse_jsonl_transcript(filepath: str) -> list[Turn]:
    """Parse a JSONL session file into a list of Turn objects.

    Supports both Claude Code format (type=user/assistant) and
    Codex format (type=response_item with payload).
    Empty lines are skipped. Malformed JSON lines are silently skipped.
    Content is normalized: string → [{type: 'text', text: str}].
    """
    turns: list[Turn] = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = record.get("type", "")

                # ── Claude Code format: type == "user" | "assistant" ──
                if record_type in ("user", "assistant"):
                    message = record.get("message", {})
                    role = message.get("role", "")
                    if role not in ("user", "assistant"):
                        continue
                    content = message.get("content")
                    blocks = _normalize_content(content)
                    timestamp = record.get("timestamp", "")
                    uuid = record.get("uuid", message.get("id", ""))

                    turns.append(Turn(
                        role=role,
                        blocks=blocks,
                        timestamp=timestamp,
                        uuid=uuid,
                    ))

                # ── Codex format: type == "response_item" with payload ──
                elif record_type == "response_item":
                    payload = record.get("payload", {})
                    role = payload.get("role", "")

                    # Map Codex roles to standard roles
                    if role == "developer":
                        role = "assistant"
                    elif role not in ("user", "assistant"):
                        continue

                    content = payload.get("content")
                    blocks = _normalize_content(content)
                    timestamp = record.get("timestamp", "")
                    uuid = record.get("id", "")

                    turns.append(Turn(
                        role=role,
                        blocks=blocks,
                        timestamp=timestamp,
                        uuid=uuid,
                    ))

                # Other record types (session_meta, event_msg, turn_context) are skipped

    except OSError:
        pass

    return turns


def _normalize_content(content) -> list[ContentBlock]:
    """Normalize content field to a list of ContentBlock objects.

    Content can be:
    - A plain string (compact summary format)
    - An array of typed content blocks
    - None / missing

    Supports both Claude Code types (text, thinking, tool_use)
    and Codex types (input_text, output_text).
    """
    if content is None:
        return []

    if isinstance(content, str):
        if content.strip():
            return [ContentBlock(type=BlockType.TEXT, text=content)]
        return []

    if isinstance(content, list):
        blocks: list[ContentBlock] = []
        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type", "")

            # Claude Code: text
            if block_type == "text":
                text = block.get("text", "")
                if text:
                    blocks.append(ContentBlock(type=BlockType.TEXT, text=text))

            # Codex: input_text → map to text
            elif block_type == "input_text":
                text = block.get("text", "")
                if text:
                    blocks.append(ContentBlock(type=BlockType.TEXT, text=text))

            # Codex: output_text → map to text
            elif block_type == "output_text":
                text = block.get("text", "")
                if text:
                    blocks.append(ContentBlock(type=BlockType.TEXT, text=text))

            # Claude Code: thinking
            elif block_type == "thinking":
                thinking = block.get("thinking", "")
                if thinking:
                    blocks.append(ContentBlock(type=BlockType.THINKING, thinking=thinking))

            # Claude Code: tool_use
            elif block_type == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                if name:
                    blocks.append(ContentBlock(
                        type=BlockType.TOOL_USE,
                        name=name,
                        input=inp if isinstance(inp, dict) else {},
                    ))

            # tool_result and image blocks are silently dropped

        return blocks

    return []


def build_stats(turns: list[Turn]) -> SessionStats:
    """Compute session statistics from parsed turns.

    A "message" is counted only if it has at least one text block.
    Turns with only thinking/tools don't count as messages.
    """
    stats = SessionStats()

    for turn in turns:
        has_text = False
        user_chars = 0
        assistant_chars = 0

        for block in turn.blocks:
            if block.type == BlockType.TEXT:
                has_text = True
                char_count = len(block.text) if block.text else 0
                if turn.role == "user":
                    user_chars += char_count
                else:
                    assistant_chars += char_count

            elif block.type == BlockType.THINKING:
                stats.thinking_blocks += 1

            elif block.type == BlockType.TOOL_USE:
                stats.tool_calls += 1

        if has_text:
            if turn.role == "user":
                stats.user_messages += 1
                stats.user_chars += user_chars
            else:
                stats.assistant_messages += 1
                stats.assistant_chars += assistant_chars

        # Track timestamp range
        if turn.timestamp:
            if stats.first_timestamp is None or turn.timestamp < stats.first_timestamp:
                stats.first_timestamp = turn.timestamp
            if stats.last_timestamp is None or turn.timestamp > stats.last_timestamp:
                stats.last_timestamp = turn.timestamp

    return stats


def extract_session_meta(filepath: str) -> SessionMeta:
    """Extract session metadata from the first records of a JSONL file.

    Reads the file header efficiently, stopping early once all metadata
    fields are found. Falls back to filename for session_id and today
    for first_date if fields are missing.
    """
    meta = SessionMeta()

    # Fallback: derive session_id from filename
    filename = Path(filepath).stem
    meta.session_id = filename

    try:
        stat = Path(filepath).stat()
        read_size = min(stat.st_size, 16384)  # Read first 16KB

        with open(filepath, "r", encoding="utf-8") as f:
            chunk = f.read(read_size)

        found = {"session_id": False, "slug": False, "first_date": False, "entrypoint": False}

        for line in chunk.split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Session ID
            if not found["session_id"] and "sessionId" in record:
                meta.session_id = record["sessionId"]
                found["session_id"] = True

            # Slug / cwd
            if not found["slug"]:
                if "slug" in record:
                    meta.slug = record["slug"]
                    found["slug"] = True
                elif "cwd" in record:
                    # Derive slug from cwd like Claude Code does
                    cwd = record["cwd"]
                    meta.slug = cwd.replace("/", "-")
                    found["slug"] = True

            # First date from timestamp
            if not found["first_date"] and "timestamp" in record:
                ts = record["timestamp"]
                if isinstance(ts, str) and len(ts) >= 10:
                    meta.first_date = ts[:10]
                    found["first_date"] = True

            # Entrypoint
            if not found["entrypoint"] and "entrypoint" in record:
                ep = record["entrypoint"]
                if ep == "cli":
                    meta.entrypoint = SessionEntrypoint.CLI
                elif ep == "claude-vscode":
                    meta.entrypoint = SessionEntrypoint.VSCODE
                else:
                    meta.entrypoint = SessionEntrypoint.UNKNOWN
                found["entrypoint"] = True

            # Early exit if all found
            if all(found.values()):
                break

        # Fallback for first_date
        if not meta.first_date:
            from datetime import date
            meta.first_date = date.today().isoformat()

    except OSError:
        pass

    return meta


def read_preview(filepath: str, max_chars: int = 100) -> str:
    """Read the first user message from a JSONL session for preview text.

    Strips HTML-like tags. Returns empty string if no user message found.
    """
    try:
        stat = Path(filepath).stat()
        read_size = min(stat.st_size, 16384)

        with open(filepath, "r", encoding="utf-8") as f:
            chunk = f.read(read_size)

        for line in chunk.split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") != "user":
                continue

            message = record.get("message", {})
            content = message.get("content", "")

            # Handle string content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Find first text block
                text = ""
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        break
            else:
                continue

            # Strip HTML-like tags and whitespace
            import re
            text = re.sub(r"<[^>]*>", "", text).strip()
            if text:
                return text[:max_chars]

    except OSError:
        pass

    return ""


def read_custom_title(filepath: str) -> str:
    """Read the custom title from a session JSONL file.

    Claude Code stores renames as {"type":"custom-title","customTitle":"..."}.
    Scans the tail for efficiency on large files, then falls back to a full scan.
    """
    try:
        stat = Path(filepath).stat()
        tail_size = 64 * 1024  # Last 64KB

        # For large files, try tail first
        if stat.st_size > tail_size:
            with open(filepath, "r", encoding="utf-8") as f:
                f.seek(stat.st_size - tail_size)
                chunk = f.read(tail_size)

            for line in reversed(chunk.split("\n")):
                if "custom-title" not in line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("type") == "custom-title" and record.get("customTitle"):
                        return record["customTitle"]
                except json.JSONDecodeError:
                    continue

        # Small file or not in tail — scan from start (capped at 256KB)
        read_size = min(stat.st_size, 256 * 1024)

        with open(filepath, "r", encoding="utf-8") as f:
            chunk = f.read(read_size)

        title = ""
        for line in chunk.split("\n"):
            if "custom-title" not in line:
                continue
            try:
                record = json.loads(line)
                if record.get("type") == "custom-title" and record.get("customTitle"):
                    title = record["customTitle"]  # Keep scanning — last one wins
            except json.JSONDecodeError:
                continue

        return title

    except OSError:
        return ""