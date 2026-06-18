"""CinderACE Sessions v2 — Markdown export renderer.

Ported from the TypeScript renderer.ts with the same formatting logic,
edge cases, and truncation behavior.
"""

from __future__ import annotations

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    RenderOptions,
    SessionMeta,
    SessionStats,
    Turn,
    clean_options,
)


def format_tool_detail(block: ContentBlock) -> str:
    """Format a tool_use block into a readable one-liner.

    e.g. "Read: ~/src/app.ts"
         "Edit: ~/src/app.ts"
         "Bash: npm run build"
    """
    name = block.name or "unknown"
    inp = block.input or {}

    if name == "Read":
        return f"**Read** `{inp.get('file_path', 'unknown')}`"

    elif name == "Edit":
        return f"**Edit** `{inp.get('file_path', 'unknown')}`"

    elif name == "Write":
        return f"**Write** `{inp.get('file_path', 'unknown')}`"

    elif name == "Bash":
        cmd = str(inp.get("command", "")).strip()
        preview = cmd[:120] + "..." if len(cmd) > 120 else cmd
        return f"**Bash** `{preview}`"

    elif name == "Grep":
        pattern = inp.get("pattern", "")
        glob_suffix = f" in {inp['glob']}" if inp.get("glob") else ""
        path_suffix = f" ({inp['path']})" if inp.get("path") else ""
        return f"**Grep** `{pattern}`{glob_suffix}{path_suffix}"

    elif name == "Glob":
        return f"**Glob** `{inp.get('pattern', '')}`"

    elif name == "Task":
        desc = str(inp.get("description", inp.get("prompt", "")))
        preview = desc[:80]
        suffix = "..." if len(desc) > 80 else ""
        return f"**Task** {preview}{suffix}"

    elif name == "WebFetch":
        return f"**WebFetch** `{inp.get('url', '')}`"

    elif name == "WebSearch":
        return f"**WebSearch** `{inp.get('query', '')}`"

    elif name == "TodoWrite":
        return "**TodoWrite** updated task list"

    elif name == "NotebookEdit":
        return f"**NotebookEdit** `{inp.get('notebook_path', '')}`"

    else:
        # Generic fallback — show first string value from input
        for value in inp.values():
            if isinstance(value, str):
                preview = value[:80]
                return f"**{name}** {preview}"
        return f"**{name}**"


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable HH:MM:SS (24h)."""
    if not ts:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except (ValueError, AttributeError):
        return ts[:19] if len(ts) >= 19 else ts


def build_digest(turns: list[Turn], options: RenderOptions) -> str:
    """Build clean markdown digest from parsed turns.

    Ported from the TypeScript buildDigest() with identical formatting:
    - Role labels with optional emoji and timestamp
    - Thinking blocks in collapsible <details> (truncated at 1000 chars)
    - Tool calls as blockquote summaries
    - Text content as-is
    """
    lines: list[str] = []

    for turn in turns:
        text_blocks = [b for b in turn.blocks if b.type == BlockType.TEXT]
        thinking_blocks = [b for b in turn.blocks if b.type == BlockType.THINKING]
        tool_blocks = [b for b in turn.blocks if b.type == BlockType.TOOL_USE]

        # Skip truly empty turns
        has_text = len(text_blocks) > 0
        has_thinking = options.include_thinking and len(thinking_blocks) > 0
        has_tools = options.include_tools and len(tool_blocks) > 0

        if not has_text and not has_thinking and not has_tools:
            continue

        ts = format_timestamp(turn.timestamp)

        # Role label with optional emoji
        is_user = turn.role == "user"
        label = options.user_label if is_user else options.assistant_label
        emoji = options.user_emoji if is_user else options.assistant_emoji
        role_label = f"{emoji} {label}" if emoji else label
        ts_display = f" *({ts})*" if ts else ""

        lines.append(f"\n---\n\n### {role_label}{ts_display}\n")

        # Thinking blocks (collapsible)
        if options.include_thinking:
            for tb in thinking_blocks:
                thinking = (tb.thinking or "").strip()
                if not thinking:
                    continue
                if len(thinking) > 1000:
                    thinking = thinking[:1000] + "\n\n*(... truncated for brevity)*"
                lines.append(f"<details>\n<summary>Thinking</summary>\n\n{thinking}\n\n</details>\n")

        # Tool summaries
        if options.include_tools:
            for tb in tool_blocks:
                detail = format_tool_detail(tb)
                lines.append(f"> {detail}\n")

        # Text content
        for tb in text_blocks:
            text = (tb.text or "").strip()
            if text:
                lines.append(f"{text}\n")

    return "\n".join(lines)


def build_document(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions,
) -> str:
    """Build the full markdown document with header, stats, and digest.

    Ported from the TypeScript buildDocument() with identical structure.
    """
    parts: list[str] = []

    # Header
    title = meta.slug or meta.session_id or "session"
    parts.append(f"# Session Digest: {title}\n")
    parts.append(f"**Source:** `{meta.session_id}`")

    if stats.first_timestamp:
        first_time = format_timestamp(stats.first_timestamp)
        last_time = format_timestamp(stats.last_timestamp or stats.first_timestamp)
        parts.append(f"**Date:** {meta.first_date}")
        parts.append(f"**Time:** {first_time} → {last_time}")

    # Stats dashboard
    parts.append("")
    parts.append("**Stats:**")
    user_prefix = f"{options.user_emoji} " if options.user_emoji else ""
    assistant_prefix = f"{options.assistant_emoji} " if options.assistant_emoji else ""
    parts.append(f"- {user_prefix}{options.user_label} messages: {stats.user_messages}")
    parts.append(f"- {assistant_prefix}{options.assistant_label} responses: {stats.assistant_messages}")

    if options.include_thinking:
        parts.append(f"- Thinking blocks: {stats.thinking_blocks}")
    if options.include_tools:
        parts.append(f"- Tool calls: {stats.tool_calls}")

    parts.append(f"- {options.user_label} text: {stats.user_chars:,} chars")
    parts.append(f"- {options.assistant_label} text: {stats.assistant_chars:,} chars")
    parts.append("\n---")

    # Digest body
    digest = build_digest(turns, options)
    parts.append(digest)

    return "\n".join(parts)


def render_markdown(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a session as a full markdown document."""
    if options is None:
        options = RenderOptions()
    return build_document(turns, stats, meta, options)


def render_markdown_clean(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
) -> str:
    """Convenience function: render a session as a clean markdown document
    (thinking included, tools excluded)."""
    if options is None:
        options = RenderOptions()
    return build_document(turns, stats, meta, clean_options(options))