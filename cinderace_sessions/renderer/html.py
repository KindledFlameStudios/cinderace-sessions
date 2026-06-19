"""CinderACE Sessions v2 — HTML export renderer with three themes.

Ported from the TypeScript htmlRenderer.ts with identical theme palettes,
CSS structure, and rendering logic. Produces self-contained HTML documents
with inline CSS and collapsible thinking blocks.
"""

from __future__ import annotations

from cinderace_sessions.parser.base import (
    BlockType,
    ContentBlock,
    HtmlTheme,
    RenderOptions,
    SessionMeta,
    SessionStats,
    Turn,
    clean_options,
)
from cinderace_sessions.renderer.markdown import format_tool_detail, format_timestamp


def escape_html(text: str) -> str:
    """Escape HTML special characters including single quotes."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#x27;"))


# ── Theme Definitions (36 CSS variables each) ────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "ember": {
        "bg": "#0a0a08",
        "bg-secondary": "#1a1208",
        "bg-tertiary": "#241a0a",
        "bg-card": "#1e1508",
        "bg-hover": "#2a1f0a",
        "border": "#3d2e10",
        "border-light": "#5a4420",
        "text": "#e0dcd0",
        "text-secondary": "#a89e88",
        "text-muted": "#7a7060",
        "accent": "#FF7820",
        "accent-hover": "#FF9040",
        "accent-muted": "#c45a10",
        "user-bg": "#1a1200",
        "user-border": "#b8860b",
        "user-text": "#ffd966",
        "assistant-bg": "#0a1a28",
        "assistant-border": "#4a90d9",
        "assistant-text": "#a0c8f0",
        "thinking-bg": "#1a0a20",
        "thinking-border": "#8a5ab0",
        "thinking-text": "#c8a0e0",
        "tool-bg": "#0a1a10",
        "tool-border": "#3a8050",
        "tool-text": "#80c890",
        "code-bg": "#141008",
        "code-border": "#3a3018",
        "code-text": "#d4c8a0",
        "divider": "#3d2e10",
        "stat-label": "#8a7e68",
        "stat-value": "#e0dcd0",
        "header-color": "#FF7820",
        "powered-by": "#5a4420",
        "shadow": "rgba(0, 0, 0, 0.3)",
    },
    "dark": {
        "bg": "#0d1117",
        "bg-secondary": "#161b22",
        "bg-tertiary": "#1c2128",
        "bg-card": "#161b22",
        "bg-hover": "#21262d",
        "border": "#30363d",
        "border-light": "#484f58",
        "text": "#e6edf3",
        "text-secondary": "#8b949e",
        "text-muted": "#6e7681",
        "accent": "#58a6ff",
        "accent-hover": "#79c0ff",
        "accent-muted": "#388bfd",
        "user-bg": "#161b22",
        "user-border": "#3fb950",
        "user-text": "#7ee787",
        "assistant-bg": "#0d1117",
        "assistant-border": "#58a6ff",
        "assistant-text": "#a5d6ff",
        "thinking-bg": "#1c1326",
        "thinking-border": "#a371f7",
        "thinking-text": "#d2a8ff",
        "tool-bg": "#0d1a12",
        "tool-border": "#3fb950",
        "tool-text": "#7ee787",
        "code-bg": "#161b22",
        "code-border": "#30363d",
        "code-text": "#e6edf3",
        "divider": "#30363d",
        "stat-label": "#8b949e",
        "stat-value": "#e6edf3",
        "header-color": "#58a6ff",
        "powered-by": "#484f58",
        "shadow": "rgba(0, 0, 0, 0.4)",
    },
    "light": {
        "bg": "#ffffff",
        "bg-secondary": "#f6f8fa",
        "bg-tertiary": "#f0f2f5",
        "bg-card": "#f6f8fa",
        "bg-hover": "#e8ecf0",
        "border": "#d0d7de",
        "border-light": "#afb8c1",
        "text": "#1f2328",
        "text-secondary": "#656d76",
        "text-muted": "#8b949e",
        "accent": "#0969da",
        "accent-hover": "#0550ae",
        "accent-muted": "#0550ae",
        "user-bg": "#f0f7ff",
        "user-border": "#0969da",
        "user-text": "#0550ae",
        "assistant-bg": "#f6f8fa",
        "assistant-border": "#1f2328",
        "assistant-text": "#1f2328",
        "thinking-bg": "#f8f3ff",
        "thinking-border": "#8250df",
        "thinking-text": "#6e40c9",
        "tool-bg": "#f0f8f0",
        "tool-border": "#1a7f37",
        "tool-text": "#116329",
        "code-bg": "#f6f8fa",
        "code-border": "#d0d7de",
        "code-text": "#1f2328",
        "divider": "#d0d7de",
        "stat-label": "#656d76",
        "stat-value": "#1f2328",
        "header-color": "#0969da",
        "powered-by": "#8b949e",
        "shadow": "rgba(0, 0, 0, 0.1)",
    },
}


def build_css(theme_name: str) -> str:
    """Generate a complete <style> block from theme CSS variables."""
    theme = THEMES.get(theme_name, THEMES["ember"])

    # Build CSS custom properties from theme
    vars = "\n".join(f"  --{key}: {value};" for key, value in theme.items())

    return f"""<style>
:root {{
{vars}
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}}

h1 {{
  color: var(--header-color);
  font-size: 1.5em;
  margin-bottom: 8px;
}}

.meta {{
  color: var(--text-secondary);
  font-size: 0.9em;
  margin-bottom: 16px;
}}

.meta p {{
  margin: 2px 0;
}}

.stats {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 16px 0;
}}

.stats ul {{
  list-style: none;
  padding: 0;
}}

.stats li {{
  padding: 2px 0;
  color: var(--text-secondary);
  font-size: 0.9em;
}}

.stats .label {{
  color: var(--stat-label);
}}

.stats .value {{
  color: var(--stat-value);
  font-weight: 500;
}}

.divider {{
  border: none;
  border-top: 1px solid var(--divider);
  margin: 16px 0;
}}

.message {{
  margin: 12px 0;
  border-radius: 8px;
  padding: 12px 16px;
}}

.message.user {{
  background: var(--user-bg);
  border-left: 3px solid var(--user-border);
}}

.message.assistant {{
  background: var(--assistant-bg);
  border-left: 3px solid var(--assistant-border);
}}

.message-label {{
  font-weight: 600;
  font-size: 0.95em;
  margin-bottom: 6px;
}}

.message.user .message-label {{
  color: var(--user-text);
}}

.message.assistant .message-label {{
  color: var(--assistant-text);
}}

.message-time {{
  color: var(--text-muted);
  font-size: 0.8em;
  font-weight: 400;
  margin-left: 8px;
}}

.message-text {{
  color: var(--text);
  white-space: pre-wrap;
  word-wrap: break-word;
}}

.thinking {{
  background: var(--thinking-bg);
  border: 1px solid var(--thinking-border);
  border-radius: 6px;
  margin: 8px 0;
  cursor: pointer;
}}

.thinking-header {{
  padding: 8px 12px;
  color: var(--thinking-text);
  font-size: 0.85em;
  font-weight: 500;
  user-select: none;
}}

.thinking-content {{
  display: none;
  padding: 0 12px 12px;
  color: var(--text-secondary);
  font-size: 0.9em;
  white-space: pre-wrap;
  word-wrap: break-word;
}}

.thinking.open .thinking-content {{
  display: block;
}}

.tool-detail {{
  background: var(--tool-bg);
  border-left: 3px solid var(--tool-border);
  padding: 4px 8px;
  margin: 4px 0;
  font-size: 0.85em;
  color: var(--tool-text);
}}

.tool-detail strong {{
  color: var(--tool-text);
}}

.tool-detail code {{
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 0.9em;
  color: var(--code-text);
}}

.powered-by {{
  text-align: center;
  color: var(--powered-by);
  font-size: 0.75em;
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid var(--divider);
}}
</style>"""


def build_html(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions,
    theme: str = "ember",
) -> str:
    """Build a complete HTML document from parsed turns.

    Produces a self-contained HTML file with inline CSS themed by
    the specified theme (ember, dark, or light).
    """
    theme_name = theme if theme in THEMES else "ember"
    title = escape_html(meta.slug or meta.session_id or "session")

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='en'>")
    parts.append("<head>")
    parts.append(f"<meta charset='UTF-8'>")
    parts.append(f"<title>Session Digest: {title}</title>")
    parts.append(build_css(theme_name))
    parts.append("</head>")
    parts.append("<body>")

    # Header
    parts.append(f"<h1>Session Digest: {title}</h1>")
    parts.append("<div class='meta'>")
    parts.append(f"<p><strong>Source:</strong> <code>{escape_html(meta.session_id)}</code></p>")

    if stats.first_timestamp:
        first_time = format_timestamp(stats.first_timestamp)
        last_time = format_timestamp(stats.last_timestamp or stats.first_timestamp)
        parts.append(f"<p><strong>Date:</strong> {escape_html(meta.first_date)}</p>")
        parts.append(f"<p><strong>Time:</strong> {escape_html(first_time)} → {escape_html(last_time)}</p>")

    parts.append("</div>")

    # Stats dashboard
    parts.append("<div class='stats'>")
    parts.append("<p><strong>Stats:</strong></p>")
    parts.append("<ul>")

    user_prefix = f"{escape_html(options.user_emoji)} " if options.user_emoji else ""
    assistant_prefix = f"{escape_html(options.assistant_emoji)} " if options.assistant_emoji else ""
    parts.append(f"<li><span class='label'>{user_prefix}{escape_html(options.user_label)} messages:</span> <span class='value'>{stats.user_messages}</span></li>")
    parts.append(f"<li><span class='label'>{assistant_prefix}{escape_html(options.assistant_label)} responses:</span> <span class='value'>{stats.assistant_messages}</span></li>")

    if options.include_thinking:
        parts.append(f"<li><span class='label'>Thinking blocks:</span> <span class='value'>{stats.thinking_blocks}</span></li>")
    if options.include_tools:
        parts.append(f"<li><span class='label'>Tool calls:</span> <span class='value'>{stats.tool_calls}</span></li>")

    parts.append(f"<li><span class='label'>{escape_html(options.user_label)} text:</span> <span class='value'>{stats.user_chars:,} chars</span></li>")
    parts.append(f"<li><span class='label'>{escape_html(options.assistant_label)} text:</span> <span class='value'>{stats.assistant_chars:,} chars</span></li>")
    parts.append("</ul>")
    parts.append("</div>")

    # Messages
    for turn in turns:
        text_blocks = [b for b in turn.blocks if b.type == BlockType.TEXT]
        thinking_blocks = [b for b in turn.blocks if b.type == BlockType.THINKING]
        tool_blocks = [b for b in turn.blocks if b.type == BlockType.TOOL_USE]

        has_text = len(text_blocks) > 0
        has_thinking = options.include_thinking and len(thinking_blocks) > 0
        has_tools = options.include_tools and len(tool_blocks) > 0

        if not has_text and not has_thinking and not has_tools:
            continue

        role_class = "user" if turn.role == "user" else "assistant"
        is_user = turn.role == "user"
        label = options.user_label if is_user else options.assistant_label
        emoji = options.user_emoji if is_user else options.assistant_emoji
        ts = format_timestamp(turn.timestamp)
        ts_html = f" <span class='message-time'>({escape_html(ts)})</span>" if ts else ""
        label_html = f"{escape_html(emoji)} {escape_html(label)}" if emoji else escape_html(label)

        parts.append(f"<div class='message {role_class}'>")
        parts.append(f"<div class='message-label'>{label_html}{ts_html}</div>")

        # Thinking blocks
        if options.include_thinking:
            for tb in thinking_blocks:
                thinking = (tb.thinking or "").strip()
                if not thinking:
                    continue
                if len(thinking) > 1000:
                    thinking = thinking[:1000] + "\n\n*(... truncated for brevity)*"
                parts.append("<div class='thinking' onclick=\"this.classList.toggle('open')\">")
                parts.append(f"<div class='thinking-header'>💭 Thinking (click to expand)</div>")
                parts.append(f"<div class='thinking-content'>{escape_html(thinking)}</div>")
                parts.append("</div>")

        # Tool details
        if options.include_tools:
            for tb in tool_blocks:
                detail = format_tool_detail(tb)
                parts.append(f"<div class='tool-detail'>{detail}</div>")

        # Text content
        for tb in text_blocks:
            text = (tb.text or "").strip()
            if text:
                parts.append(f"<div class='message-text'>{escape_html(text)}</div>")

        parts.append("</div>")

    # Footer
    parts.append("<div class='powered-by'>Exported by CinderACE Sessions</div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def render_html(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
    theme: str = "ember",
) -> str:
    """Convenience function: render a session as a full HTML document."""
    if options is None:
        options = RenderOptions()
    return build_html(turns, stats, meta, options, theme)


def render_html_clean(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
    theme: str = "ember",
) -> str:
    """Convenience function: render a clean HTML document (thinking, no tools)."""
    if options is None:
        options = RenderOptions()
    return build_html(turns, stats, meta, clean_options(options), theme)