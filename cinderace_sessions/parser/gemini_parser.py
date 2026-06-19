"""CinderACE Sessions v2 — Gemini CLI JSON session parser.

Gemini CLI stores sessions in two formats:

1. logs.json — flat runtime session log (JSON array of messages):
   [{type: 'user'|'model', message: 'string', timestamp, sessionId}, ...]

2. Chat files (in chats/ directory) — structured session objects:
   {sessionId, messages: [{type: 'user'|'gemini'|'info', content: list|string,
    thoughts: [...], toolCalls: [...], tokens, model}], ...}

Also processes checkpoints (same format as chat files).

Both formats are handled transparently based on the structure detected.

For very large files (>8MB), only the first 8MB is read for parsing
to avoid memory spikes on systems with many large sessions. The
metadata extraction already skips full parsing for files over 2MB.
"""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

# Maximum file size to read entirely for parsing.
# Files larger than this are scanned line-by-line for JSONL format
# or rejected for JSON format.
_MAX_PARSE_SIZE = 8 * 1024 * 1024  # 8MB


def parse_gemini_session(filepath: str) -> list[Turn]:
    """Parse a Gemini CLI session file into Turn objects.

    Handles both formats:
    - logs.json: flat array of {type, message, timestamp}
    - Chat files: {messages: [{type, content, thoughts, toolCalls}]}
    - Checkpoint files: same as chat files

    For files larger than _MAX_PARSE_SIZE, only JSONL line-by-line
    parsing is attempted (no full json.loads) to avoid memory spikes.
    """
    turns: list[Turn] = []

    try:
        stat = Path(filepath).stat()
        file_size = stat.st_size
    except OSError:
        return turns

    # For very large files, skip to JSONL-only parsing to avoid memory spikes
    if file_size > _MAX_PARSE_SIZE:
        logger.info("Large file (%dMB), using JSONL-only parsing: %s",
                     file_size // (1024 * 1024), filepath)
        return _parse_jsonl_large(filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return turns

    # Try JSON first (chat format and logs format)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try JSONL — Gemini stores some sessions as line-delimited JSON
        # First line may be session metadata ({sessionId, projectHash, ...})
        # Subsequent lines are individual chat messages ({type, content, ...})
        messages = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(entry, dict):
                # Skip metadata entries like {sessionId, projectHash, kind}
                if "kind" in entry and "sessionId" in entry:
                    continue
                # Skip $set entries (live update patches)
                if "$set" in entry and len(entry) == 1:
                    continue
                # Collect message entries
                if "type" in entry:
                    messages.append(entry)

        if messages:
            # Parse as chat messages (Gemini format with type/content)
            return _parse_chat_messages(messages)
        return turns  # No valid JSON found

    if not isinstance(data, (list, dict)):
        return turns

    # Determine format and extract message list
    if isinstance(data, dict):
        # Chat / checkpoint format: {sessionId, messages: [...]}
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return turns
        return _parse_chat_messages(messages)
    elif isinstance(data, list):
        # Could be logs.json (flat array) or a chat array
        if data and isinstance(data[0], dict):
            # Check if it's a chat-style format or flat logs
            first = data[0]
            if "messages" in first and isinstance(first.get("messages"), list):
                # Array of chat objects — take the first one
                messages = first.get("messages", [])
                return _parse_chat_messages(messages)
            elif "type" in first and "message" in first:
                # logs.json format: flat array of {type, message}
                return _parse_logs_entries(data)
            elif "type" in first and "content" in first:
                # Already a message array (chat-style but without wrapper)
                return _parse_chat_messages(data)

    return turns


def _parse_logs_entries(entries: list[dict]) -> list[Turn]:
    """Parse logs.json format: flat array of {type, message, timestamp}.

    In logs.json, entries use:
    - type: 'user' or 'model'
    - message: string content
    - timestamp: ISO timestamp
    - sessionId: session identifier
    """
    turns: list[Turn] = []
    fallback_uuid = str(uuid4())  # One UUID for all turns that lack a sessionId

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get("type", "")

        # Map types to roles
        if entry_type == "user":
            role = "user"
        elif entry_type == "model":
            role = "assistant"
        else:
            continue

        # Content is in the 'message' field as a string
        content = entry.get("message", "")
        if isinstance(content, str):
            content = content.strip()

        if not content:
            continue

        timestamp = entry.get("timestamp", "")
        turn_uuid = entry.get("sessionId", fallback_uuid)

        turns.append(Turn(
            role=role,
            blocks=[ContentBlock(type=BlockType.TEXT, text=content)],
            timestamp=timestamp,
            uuid=turn_uuid,
        ))

    return turns


def _parse_chat_messages(messages: list[dict]) -> list[Turn]:
    """Parse chat-format messages: [{type, content, thoughts, toolCalls}].

    In chat files, messages use:
    - type: 'user', 'gemini', or 'info'
    - content: string or list of {text: '...'} objects
    - thoughts: [{subject, description, timestamp}] (thinking blocks)
    - toolCalls: [{name, args, result, status}] (tool use)
    - tokens: {input, output} (token usage)
    - model: model name
    """
    turns: list[Turn] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        msg_type = msg.get("type", "")

        # Map types to roles
        if msg_type == "user":
            role = "user"
        elif msg_type == "gemini":
            role = "assistant"
        elif msg_type == "info":
            # Info messages (e.g., model switches) — skip, not conversation
            continue
        else:
            continue

        blocks: list[ContentBlock] = []

        # ── Parse thoughts (thinking blocks) ──
        thoughts = msg.get("thoughts", [])
        if isinstance(thoughts, list):
            for thought in thoughts:
                if not isinstance(thought, dict):
                    continue
                subject = thought.get("subject", "")
                description = thought.get("description", "")
                if subject or description:
                    text = f"[{subject}] {description}" if subject else description
                    blocks.append(ContentBlock(type=BlockType.THINKING, thinking=text))

        # ── Parse content ──
        content = msg.get("content", "")
        content_blocks = _parse_content_field(content)

        # For gemini/assistant messages, put thinking before content
        if role == "assistant":
            blocks.extend(content_blocks)
        else:
            # For user messages, content first
            blocks = content_blocks + blocks

        # ── Parse tool calls ──
        tool_calls = msg.get("toolCalls", [])
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                name = tc.get("name", "")
                if not name:
                    continue
                args = tc.get("args", {})
                if not isinstance(args, dict):
                    args = {"args": str(args)}
                blocks.append(ContentBlock(
                    type=BlockType.TOOL_USE,
                    name=name,
                    input=args,
                ))

        if not blocks:
            continue

        timestamp = msg.get("timestamp", "")
        turn_uuid = msg.get("id", str(uuid4()))

        turns.append(Turn(
            role=role,
            blocks=blocks,
            timestamp=timestamp,
            uuid=turn_uuid,
        ))

    return turns


def _parse_content_field(content) -> list[ContentBlock]:
    """Parse a content field which can be:
    - A plain string
    - A list of {text: '...'} objects
    - A list of mixed objects (text, functionCall, functionResponse)
    - None/empty
    """
    if content is None or content == "":
        return []

    if isinstance(content, str):
        text = content.strip()
        if text:
            return [ContentBlock(type=BlockType.TEXT, text=text)]
        return []

    if isinstance(content, list):
        blocks: list[ContentBlock] = []
        for part in content:
            if not isinstance(part, dict):
                continue

            # Text block
            text = part.get("text", "")
            if text and not part.get("thought"):
                blocks.append(ContentBlock(type=BlockType.TEXT, text=text))
                continue

            # Thinking block (in content, not the separate thoughts field)
            if part.get("thought") and text:
                blocks.append(ContentBlock(type=BlockType.THINKING, thinking=text))
                continue

            # Function call (tool use)
            func_call = part.get("functionCall")
            if func_call and isinstance(func_call, dict):
                name = func_call.get("name", "")
                args = func_call.get("args", {})
                if name:
                    blocks.append(ContentBlock(
                        type=BlockType.TOOL_USE,
                        name=name,
                        input=args if isinstance(args, dict) else {},
                    ))
                continue

            # Function response — skip
            if part.get("functionResponse"):
                continue

        return blocks

    return []


def _parse_jsonl_large(filepath: str) -> list[Turn]:
    """Parse a large Gemini session file using line-by-line JSONL parsing.

    Reads the file incrementally without loading it all into memory.
    Only extracts message entries (chat format), skipping metadata
    and session_meta lines.
    """
    messages: list[dict] = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue
                # Skip metadata entries
                if "kind" in entry and "sessionId" in entry:
                    continue
                if "$set" in entry and len(entry) == 1:
                    continue
                # Skip session_meta records
                if entry.get("type") == "session_meta":
                    continue
                # Collect message entries
                if "type" in entry:
                    messages.append(entry)
    except OSError:
        pass

    if messages:
        return _parse_chat_messages(messages)
    return []


def gemini_extract_meta(filepath: str) -> SessionMeta:
    """Extract metadata from a Gemini CLI session file.

    Handles both logs.json and chat file formats.
    """
    meta = SessionMeta()
    filename = Path(filepath).stem

    # For logs.json, derive ID from parent directory hash
    # For chat files, use the session ID from the data
    # For checkpoints, extract from filename
    if filename.startswith("checkpoint-"):
        meta.session_id = filename.replace("checkpoint-", "")
        meta.slug = meta.session_id
    elif filename == "logs":
        # logs.json — use parent directory as slug
        parent = Path(filepath).parent.name
        meta.session_id = f"{parent}-{filename}"
        meta.slug = parent
    elif filename.startswith("session-"):
        # Chat file — use filename as ID
        meta.session_id = filename
        # Try to extract a readable slug from the date portion
        # session-2026-04-20T21-37-1312ff22 → 2026-04-20
        parts = filename.split("T")
        if len(parts) >= 1 and "-" in parts[0]:
            date_part = parts[0].replace("session-", "")
            if len(date_part) >= 10:
                meta.slug = date_part[:10]
            else:
                meta.slug = date_part
        else:
            meta.slug = filename
    else:
        parent = Path(filepath).parent.name
        meta.session_id = f"{parent}-{filename}"
        meta.slug = parent

    meta.entrypoint = SessionEntrypoint.UNKNOWN
    meta.first_date = ""

    # Try to extract date from the filename for session files
    if filename.startswith("session-"):
        date_str = filename.replace("session-", "").split("T")[0]
        if len(date_str) >= 10:
            meta.first_date = date_str[:10]

    # Try to get date and session ID from file data
    # For small files, parse the JSON. For large files, use filename-derived metadata.
    try:
        stat = Path(filepath).stat()
        file_size = stat.st_size

        if file_size <= 2 * 1024 * 1024:  # 2MB — safe to fully parse
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                # Chat format — extract from top-level fields
                if "sessionId" in data:
                    meta.session_id = data["sessionId"]
                if "startTime" in data:
                    ts = data["startTime"]
                    if isinstance(ts, str) and len(ts) >= 10:
                        meta.first_date = ts[:10]

            elif isinstance(data, list) and data:
                # Logs format — extract from first entry
                first = data[0] if isinstance(data[0], dict) else {}
                ts = first.get("timestamp", "")
                if isinstance(ts, str) and len(ts) >= 10:
                    meta.first_date = ts[:10]
                if "sessionId" in first:
                    meta.session_id = first["sessionId"]

        # For larger files, filename-derived metadata is already set above

        # Fallback: use file modification time if no date yet
        if not meta.first_date:
            from datetime import datetime
            mtime = datetime.fromtimestamp(stat.st_mtime)
            meta.first_date = mtime.strftime("%Y-%m-%d")

    except (json.JSONDecodeError, OSError, MemoryError):
        if not meta.first_date:
            try:
                from datetime import datetime
                mtime = datetime.fromtimestamp(Path(filepath).stat().st_mtime)
                meta.first_date = mtime.strftime("%Y-%m-%d")
            except OSError:
                from datetime import date
                meta.first_date = date.today().isoformat()

    return meta