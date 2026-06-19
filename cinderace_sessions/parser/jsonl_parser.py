"""CinderACE Sessions v2 — JSONL session parser.

Parses JSONL session files used by Claude Code, Codex, and any CLI
that stores conversations as newline-delimited JSON records.

Ported from the TypeScript parser.ts with the same logic and edge cases.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionEntrypoint,
    SessionMeta,
    SessionStats,
    Turn,
)

logger = logging.getLogger(__name__)


def parse_jsonl_transcript(filepath: str) -> list[Turn]:
    """Parse a JSONL session file into a list of Turn objects.

    Supports both Claude Code format (type=user/assistant) and
    Codex format (type=response_item with payload).
    Empty lines are skipped. Malformed JSON lines are silently skipped.
    Content is normalized: string → [{type: 'text', text: str}].
    """
    turns: list[Turn] = []
    skipped_lines = 0

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    skipped_lines += 1
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

    if skipped_lines:
        logger.warning("Skipped %d malformed JSON lines in %s", skipped_lines, filepath)

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

            # Codex format: session_meta has payload with id and cwd
            if record.get("type") == "session_meta":
                payload = record.get("payload", {})
                if isinstance(payload, dict):
                    if not found["session_id"] and "id" in payload:
                        meta.session_id = payload["id"]
                        found["session_id"] = True
                    if not found["slug"] and "cwd" in payload:
                        cwd = payload["cwd"]
                        meta.slug = cwd.replace("/", "-")
                        found["slug"] = True

            # Codex format: response_item has timestamp at top level
            if record.get("type") == "response_item":
                if not found["first_date"] and "timestamp" in record:
                    ts = record["timestamp"]
                    if isinstance(ts, str) and len(ts) >= 10:
                        meta.first_date = ts[:10]
                        found["first_date"] = True
                # Also extract cwd from payload for slug
                payload = record.get("payload", {})
                if isinstance(payload, dict) and not found["slug"] and "cwd" in payload:
                    meta.slug = payload["cwd"].replace("/", "-")
                    found["slug"] = True

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
    """Read the first human-meaningful user message from a JSONL session for preview text.

    Handles both Claude Code format (type=user/assistant) and Codex format
    (type=response_item). Skips system context blocks (AGENTS.md, env XML, etc.)
    and finds the first piece of actual human-written text.
    """
    import re

    # Heuristics for identifying system/context content
    CONTEXT_PREFIXES = (
        "# AGENTS.md",
        "# 🏠 Kindled Flame",
        "Filesystem sandboxing",
        "Collaboration Mode:",
        "<permissions",
        "You are Codex",
        "You are an AI",
        "# 🏠",
    )

    CONTEXT_PATTERNS = (
        # Codex: environment context block
        "<environment_context>",
        # Codex: collaboration mode instructions
        "<collaboration_mode>",
        # Codex: permission/plugin blocks
        "<permissions instructions>",
        "<apps_instructions>",
        "<skills_instructions>",
        "<plugins_instructions>",
        "<ember-memory>",
        # Codex: instruction wrapper
        "<INSTRUCTIONS>",
    )

    def _is_context(text: str) -> bool:
        """Return True if this text is system context, not human input."""
        clean = re.sub(r"<[^>]*>", "", text).strip()
        if not clean:
            return True
        # Very short messages (< 3 chars) are ambiguous — err on the side of
        # showing them. Only skip empty or whitespace-only content.
        if len(clean) < 2:
            return True
        # Very long blocks are almost always system instructions
        if len(clean) > 2000:
            return True
        for prefix in CONTEXT_PREFIXES:
            if clean.startswith(prefix):
                return True
        # Check for context patterns in the raw text
        for pattern in CONTEXT_PATTERNS:
            if pattern in text:
                return True
        # XML-heavy content (env context like <cwd>, <shell>, etc.)
        if clean.count("<") > 3 and clean.count(">") > 3:
            return True
        # Codex instruction blocks: start with "You are" and contain "##"
        if clean.startswith("You are") and "##" in clean:
            return True
        # Multi-line instruction blocks that contain directive markers
        directive_count = clean.count("##") + clean.count("- **") + clean.count("NEVER ") + clean.count("ALWAYS ")
        if directive_count >= 3:
            return True
        return False

    try:
        stat = Path(filepath).stat()
        # Read up to 128KB to find human content past system context
        read_size = min(stat.st_size, 131072)

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

            record_type = record.get("type", "")

            # ── Claude Code format: type == "user" ──
            if record_type == "user":
                message = record.get("message", {})
                content = message.get("content", "")

                if isinstance(content, str):
                    if not _is_context(content):
                        text = re.sub(r"<[^>]*>", "", content).strip()
                        if text:
                            return text[:max_chars]
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if not _is_context(text):
                                clean = re.sub(r"<[^>]*>", "", text).strip()
                                if clean:
                                    return clean[:max_chars]

            # ── Codex format: type == "response_item" ──
            elif record_type == "response_item":
                payload = record.get("payload", {})
                role = payload.get("role", "")

                # Skip developer/system messages
                if role in ("developer", "system"):
                    continue
                # Only use real user messages
                if role != "user":
                    continue

                content = payload.get("content", "")
                if isinstance(content, str):
                    if not _is_context(content):
                        text = re.sub(r"<[^>]*>", "", content).strip()
                        if text:
                            return text[:max_chars]
                elif isinstance(content, list):
                    # Walk all blocks looking for human text
                    for block in content:
                        if isinstance(block, dict):
                            block_type = block.get("type", "")
                            block_text = block.get("text", "")
                            if block_type not in ("input_text", "text") or not block_text:
                                continue
                            if not _is_context(block_text):
                                clean = re.sub(r"<[^>]*>", "", block_text).strip()
                                if clean:
                                    return clean[:max_chars]

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