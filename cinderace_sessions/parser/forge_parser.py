"""CinderACE Sessions v2 — Fire Forge SQLite session parser.

Reads session data from the forge.db SQLite database used by the Fire Forge CLI.
The forge stores conversations (with Seren, Kael, Solace) in a structured database
with rich message parts (text, reasoning, tool_call, tool_result, channel_meta,
binary, finish).

This parser converts those structured messages into the same Turn/ContentBlock
format used by the JSONL and Gemini parsers, so they feed directly into the
existing render pipeline (Markdown, HTML, JSON, JSONL, ZIP).

Filepath convention: forge sessions are identified by ``forge.db::session_id``
in the filepath field. The parser splits on ``::`` to locate the database and
select the correct session rows.
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    SessionEntrypoint,
    SessionMeta,
    Turn,
)

logger = logging.getLogger(__name__)

# ── Part type → BlockType mapping ──────────────────────────────────────

_PART_TYPE_MAP: dict[str, BlockType] = {
    "text": BlockType.TEXT,
    "reasoning": BlockType.THINKING,
    "tool_call": BlockType.TOOL_USE,
    "tool_result": BlockType.TOOL_RESULT,
}

# ── Role mapping ──────────────────────────────────────────────────────
# Forge uses 'user', 'assistant', 'tool', 'system'.
# We map 'tool' and 'system' to 'assistant' so they render under the
# assistant's turn, matching how other parsers handle tool interleaving.


def _map_role(role: str) -> str:
    """Map a forge message role to a standard render role."""
    if role == "user":
        return "user"
    # assistant, tool, system → all render under assistant
    return "assistant"


# ── Fingerprint for detecting forge sessions ──────────────────────────

FORGE_FILEPATH_RE = re.compile(r"::([a-f0-9\-]{36})$")


def split_forge_filepath(filepath: str) -> tuple[str, str]:
    """Split a ``forge.db::session_id`` filepath into (db_path, session_id).

    Returns (filepath_unchanged, "") if the filepath doesn't contain ``::``.
    """
    m = FORGE_FILEPATH_RE.search(filepath)
    if m:
        db_path = filepath[: m.start()]
        session_id = m.group(1)
        return db_path, session_id
    # Fallback: no session ID encoded — caller must handle
    return filepath, ""


# ── Core parser ────────────────────────────────────────────────────────


def parse_forge_session(filepath: str, source: str = "") -> list[Turn]:
    """Parse a Fire Forge session into a list of Turn objects.

    Parameters
    ----------
    filepath:
        Either a plain path to ``forge.db`` (first session used) or, preferably,
        ``forge.db::<session_id>`` as produced by the detector.
    source:
        The ``cli_source`` string (e.g. ``"forge-seren"``). Not currently used
        for parsing but reserved for future filtering.
    """
    import sqlite3

    db_path, session_id = split_forge_filepath(filepath)
    if not session_id:
        # No session ID — can't parse. Return empty.
        logger.warning("Forge parser: no session ID in filepath %r", filepath)
        return []

    turns: list[Turn] = []

    try:
        import sqlite3
        with closing(sqlite3.connect(str(db_path))) as conn:
            # Handle emoji and other non-ASCII in message content
            conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, role, parts, created_at FROM messages "
                "WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            rows = cursor.fetchall()
    except Exception:
        logger.error("Forge parser: failed to query forge.db %r", db_path, exc_info=True)
        return []

    for row in rows:
        msg_id = row["id"]
        role = row["role"]
        parts_raw = row["parts"]
        created_sec = row["created_at"] or 0

        # Parse parts JSON
        try:
            parts = json.loads(parts_raw) if isinstance(parts_raw, str) else parts_raw
        except json.JSONDecodeError:
            logger.debug("Forge parser: bad parts JSON for message %s", msg_id)
            continue

        if not isinstance(parts, list):
            continue

        # Build content blocks from parts
        blocks: list[ContentBlock] = []
        for part in parts:
            if not isinstance(part, dict):
                continue

            ptype = part.get("type", "")
            data = part.get("data", {})

            # ── text ──────────────────────────────────────────────
            if ptype == "text":
                text = data.get("text", "")
                if text:
                    blocks.append(ContentBlock(type=BlockType.TEXT, text=text))

            # ── reasoning → THINKING ──────────────────────────────
            elif ptype == "reasoning":
                thinking = data.get("thinking", "")
                if thinking:
                    blocks.append(ContentBlock(type=BlockType.THINKING, thinking=thinking))

            # ── tool_call → TOOL_USE ─────────────────────────────
            elif ptype == "tool_call":
                name = data.get("name", "")
                inp = data.get("input", {})
                if isinstance(inp, str):
                    # Forge stores tool input as a JSON string sometimes
                    try:
                        inp = json.loads(inp)
                    except json.JSONDecodeError:
                        inp = {"raw_input": inp}
                if name:
                    blocks.append(ContentBlock(
                        type=BlockType.TOOL_USE,
                        name=name,
                        input=inp if isinstance(inp, dict) else {},
                    ))

            # ── tool_result → TOOL_RESULT ─────────────────────────
            elif ptype == "tool_result":
                name = data.get("name", "")
                content = data.get("content", "")
                # tool_result content can be very long; we store it as text
                # on a TOOL_RESULT block for the render pipeline
                is_error = data.get("is_error", False)
                # Prepend error marker if the tool reported an error
                result_text = content
                if is_error and content:
                    result_text = f"❌ Error: {content}"
                blocks.append(ContentBlock(
                    type=BlockType.TOOL_RESULT,
                    name=name or "",
                    text=result_text,
                ))

            # ── channel_meta → skip (metadata, not content) ──────
            elif ptype == "channel_meta":
                continue

            # ── binary → skip (would need base64 handling) ───────
            elif ptype == "binary":
                # Binary parts contain file data (images, etc.)
                # For now we skip them in text exports.
                # A future renderer could embed them as images.
                path = data.get("Path", "")
                mime = data.get("MIMEType", "")
                if path:
                    blocks.append(ContentBlock(
                        type=BlockType.TEXT,
                        text=f"[📎 {path}]",
                    ))
                continue

            # ── finish → preserve error messages, skip normal stops ──
            elif ptype == "finish":
                reason = data.get("reason", "")
                msg = data.get("message", "")
                if reason == "error" and msg:
                    # Error-only messages were being silently dropped,
                    # causing confusing consecutive user turns in the export.
                    # Preserve them so the conversation flow makes sense.
                    blocks.append(ContentBlock(
                        type=BlockType.TEXT,
                        text=f"⚠️ Provider error: {msg}",
                    ))

        # Skip messages that have no content at all
        # (e.g. system messages with only a finish/stop part)
        if not blocks:
            continue

        # Derive timestamp (forge stores seconds, not milliseconds)
        timestamp = ""
        if created_sec > 0:
            try:
                dt = datetime.fromtimestamp(created_sec, tz=timezone.utc)
                timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (OSError, ValueError):
                pass

        # Map role — tool/system messages become assistant turns
        mapped_role = _map_role(role)

        turns.append(Turn(
            role=mapped_role,
            blocks=blocks,
            timestamp=timestamp,
            uuid=msg_id,
        ))

    # ── Merge consecutive same-role turns ──────────────────────────
    # Forge interleaves tool_call (role=tool) between assistant turns.
    # The pipeline expects tool results to appear as blocks within
    # assistant turns, not as separate turns. We merge consecutive
    # assistant turns so that reasoning → tool_call → tool_result
    # → text all appear as blocks in one logical turn.
    merged = _merge_consecutive_assistant_turns(turns)

    return merged


def _merge_consecutive_assistant_turns(turns: list[Turn]) -> list[Turn]:
    """Merge consecutive assistant-role turns into single turns.

    The forge database stores tool result messages with role='tool' as
    separate rows.  When mapped to 'assistant', they would create
    multiple consecutive assistant turns, which breaks the render
    pipeline.  This function squashes them: consecutive assistant turns
    are merged by appending their blocks together.
    """
    if not turns:
        return []

    merged: list[Turn] = [turns[0]]

    for turn in turns[1:]:
        prev = merged[-1]
        if turn.role == "assistant" and prev.role == "assistant":
            # Merge: append this turn's blocks to the previous turn
            prev.blocks.extend(turn.blocks)
            # Update timestamp to the latest block's timestamp
            if turn.timestamp:
                prev.timestamp = turn.timestamp
            # Keep the first turn's UUID
        else:
            merged.append(turn)

    # Merge user turns that are consecutive too (rare but possible with
    # channel_meta-bridged messages). Actually — only merge assistant
    # turns. Consecutive user turns should stay separate (they're
    # genuinely different messages).

    return merged


# ── Metadata extraction ────────────────────────────────────────────────


def forge_extract_meta(filepath: str, source: str = "") -> SessionMeta:
    """Extract session metadata from a forge.db session.

    Parameters
    ----------
    filepath:
        ``forge.db::<session_id>`` format string.
    source:
        The ``cli_source`` string (e.g. ``"forge-seren"``).
    """
    import sqlite3

    meta = SessionMeta()

    db_path, session_id = split_forge_filepath(filepath)
    if not session_id:
        return meta

    meta.session_id = session_id

    try:
        import sqlite3
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, title, identity, created_at FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
    except Exception:
        logger.error("Forge meta: failed to query session %r", session_id, exc_info=True)
        return meta

    if not row:
        return meta

    # Build slug from title
    title = row["title"] or ""
    if title:
        # Slugify: lowercase, replace non-alnum with hyphens, collapse repeats
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        slug = slug[:80]  # Cap slug length
        meta.slug = slug
    else:
        meta.slug = session_id[:8]

    # Extract date from created_at (seconds, not milliseconds)
    created_sec = row["created_at"] or 0
    if created_sec > 0:
        try:
            dt = datetime.fromtimestamp(created_sec, tz=timezone.utc)
            meta.first_date = dt.strftime("%Y-%m-%d")
        except (OSError, ValueError):
            pass

    meta.entrypoint = SessionEntrypoint.CLI

    return meta