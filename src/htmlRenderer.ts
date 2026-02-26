import { Turn, SessionStats, SessionMeta, RenderOptions, HtmlTheme } from './types';

/** CinderACE theme color palettes. */
const THEMES: Record<HtmlTheme, Record<string, string>> = {
  ember: {
    bodyBg: '#0a0a0a',
    bodyColor: '#e8e0d4',
    containerBg: '#141010',
    containerBorder: '#2a1a0a',
    containerShadow: 'rgba(232,114,12,0.08)',
    headerBorder: '#e8720c',
    headerTitle: '#f4a644',
    metaColor: '#8a7560',
    userBg: '#1a1208',
    userBorder: '#e8720c',
    userLabel: '#e8720c',
    aiBg: '#140e0a',
    aiBorder: '#5c3a1e',
    aiLabel: '#f4a644',
    codeBg: '#2a1a0a',
    codeColor: '#e8e0d4',
    preCodeBg: '#0a0604',
    preCodeColor: '#e8e0d4',
    thinkingBg: '#1a1400',
    thinkingBorder: '#b8860b',
    thinkingLabel: '#b8860b',
    thinkingContent: '#c9b896',
    toolBg: '#1a1208',
    toolBorder: '#5c3a1e',
    toolColor: '#8a7560',
    hrColor: '#2a1a0a',
  },
  dark: {
    bodyBg: '#0d1117',
    bodyColor: '#e6edf3',
    containerBg: '#161b22',
    containerBorder: '#30363d',
    containerShadow: 'rgba(0,0,0,0.3)',
    headerBorder: '#58a6ff',
    headerTitle: '#e6edf3',
    metaColor: '#8b949e',
    userBg: '#1c2a3f',
    userBorder: '#58a6ff',
    userBorder2: '#58a6ff',
    userLabel: '#58a6ff',
    aiBg: '#1c1c1c',
    aiBorder: '#484f58',
    aiLabel: '#8b949e',
    codeBg: '#30363d',
    codeColor: '#e6edf3',
    preCodeBg: '#0d1117',
    preCodeColor: '#e6edf3',
    thinkingBg: '#2d1f00',
    thinkingBorder: '#d29922',
    thinkingLabel: '#d29922',
    thinkingContent: '#c9d1d9',
    toolBg: '#161b22',
    toolBorder: '#484f58',
    toolColor: '#8b949e',
    hrColor: '#30363d',
  },
  light: {
    bodyBg: '#ffffff',
    bodyColor: '#1a1a2e',
    containerBg: '#ffffff',
    containerBorder: '#e5e7eb',
    containerShadow: 'rgba(0,0,0,0.05)',
    headerBorder: '#2563eb',
    headerTitle: '#1a1a2e',
    metaColor: '#6b7280',
    userBg: '#eff6ff',
    userBorder: '#2563eb',
    userLabel: '#2563eb',
    aiBg: '#f9fafb',
    aiBorder: '#9ca3af',
    aiLabel: '#4b5563',
    codeBg: '#f3f4f6',
    codeColor: '#1a1a2e',
    preCodeBg: '#1e293b',
    preCodeColor: '#e2e8f0',
    thinkingBg: '#fffbeb',
    thinkingBorder: '#f59e0b',
    thinkingLabel: '#f59e0b',
    thinkingContent: '#78716c',
    toolBg: '#f3f4f6',
    toolBorder: '#d1d5db',
    toolColor: '#6b7280',
    hrColor: '#e5e7eb',
  },
};

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatTimestamp(ts: string): string {
  if (!ts) return '';
  try {
    const dt = new Date(ts);
    return dt.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return ts.substring(0, 19);
  }
}

function buildCss(t: Record<string, string>): string {
  return `
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      background: ${t.bodyBg};
      color: ${t.bodyColor};
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      font-size: 15px;
      line-height: 1.6;
    }
    .container {
      max-width: 900px;
      margin: 2rem auto;
      padding: 2rem;
      background: ${t.containerBg};
      border: 1px solid ${t.containerBorder};
      border-radius: 12px;
      box-shadow: 0 2px 12px ${t.containerShadow};
    }
    .header {
      border-bottom: 3px solid ${t.headerBorder};
      padding-bottom: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .header h1 {
      color: ${t.headerTitle};
      font-size: 1.6rem;
      margin-bottom: 0.5rem;
    }
    .meta { color: ${t.metaColor}; font-size: 0.9rem; line-height: 1.8; }
    .meta strong { color: ${t.bodyColor}; }
    .stats { margin: 1rem 0; padding: 0; list-style: none; }
    .stats li { padding: 0.15rem 0; }
    hr {
      border: none;
      border-top: 1px solid ${t.hrColor};
      margin: 1.5rem 0;
    }
    .message { margin: 1.5rem 0; padding: 1rem 1.2rem; border-radius: 8px; border-left: 4px solid; }
    .message.user { background: ${t.userBg}; border-left-color: ${t.userBorder}; }
    .message.assistant { background: ${t.aiBg}; border-left-color: ${t.aiBorder}; }
    .message-label {
      font-weight: 700;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 0.5rem;
    }
    .message.user .message-label { color: ${t.userLabel}; }
    .message.assistant .message-label { color: ${t.aiLabel}; }
    .timestamp { font-weight: 400; opacity: 0.7; font-size: 0.8rem; margin-left: 0.5rem; }
    .message-text { white-space: pre-wrap; word-wrap: break-word; }
    .message-text p { margin: 0.5rem 0; }
    code {
      background: ${t.codeBg};
      color: ${t.codeColor};
      padding: 0.15rem 0.4rem;
      border-radius: 4px;
      font-size: 0.9em;
      font-family: 'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace;
    }
    pre {
      background: ${t.preCodeBg};
      color: ${t.preCodeColor};
      padding: 1rem;
      border-radius: 6px;
      overflow-x: auto;
      margin: 0.75rem 0;
    }
    pre code { background: none; padding: 0; }
    .thinking {
      background: ${t.thinkingBg};
      border-left: 3px solid ${t.thinkingBorder};
      padding: 0.75rem 1rem;
      margin: 0.5rem 0;
      border-radius: 4px;
    }
    .thinking-label {
      color: ${t.thinkingLabel};
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      user-select: none;
    }
    .thinking-content {
      color: ${t.thinkingContent};
      font-size: 0.9rem;
      white-space: pre-wrap;
      margin-top: 0.5rem;
      display: none;
    }
    .thinking.open .thinking-content { display: block; }
    .tool-detail {
      background: ${t.toolBg};
      border-left: 3px solid ${t.toolBorder};
      color: ${t.toolColor};
      padding: 0.4rem 0.8rem;
      margin: 0.3rem 0;
      border-radius: 4px;
      font-size: 0.85rem;
      font-family: 'Fira Code', 'Cascadia Code', monospace;
    }
    .tool-detail strong { color: ${t.bodyColor}; }
    .powered-by {
      text-align: center;
      color: ${t.metaColor};
      font-size: 0.8rem;
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid ${t.hrColor};
    }
  `;
}

function formatToolDetailHtml(block: { name?: string; input?: Record<string, unknown> }): string {
  const name = block.name ?? 'unknown';
  const input = block.input ?? {};

  switch (name) {
    case 'Read':
      return `<strong>Read</strong> <code>${escapeHtml(String(input.file_path ?? 'unknown'))}</code>`;
    case 'Edit':
      return `<strong>Edit</strong> <code>${escapeHtml(String(input.file_path ?? 'unknown'))}</code>`;
    case 'Write':
      return `<strong>Write</strong> <code>${escapeHtml(String(input.file_path ?? 'unknown'))}</code>`;
    case 'Bash': {
      const cmd = String(input.command ?? '').trim();
      const preview = cmd.length > 120 ? cmd.substring(0, 120) + '...' : cmd;
      return `<strong>Bash</strong> <code>${escapeHtml(preview)}</code>`;
    }
    case 'Grep':
      return `<strong>Grep</strong> <code>${escapeHtml(String(input.pattern ?? ''))}</code>${input.glob ? ` in ${escapeHtml(String(input.glob))}` : ''}`;
    case 'Glob':
      return `<strong>Glob</strong> <code>${escapeHtml(String(input.pattern ?? ''))}</code>`;
    case 'Task': {
      const desc = String(input.description ?? input.prompt ?? '').substring(0, 80);
      return `<strong>Task</strong> ${escapeHtml(desc)}`;
    }
    default:
      return `<strong>${escapeHtml(name)}</strong>`;
  }
}

/**
 * Build a complete HTML document from parsed turns.
 */
export function buildHtml(
  turns: Turn[],
  stats: SessionStats,
  meta: SessionMeta,
  options: RenderOptions,
  theme: HtmlTheme = 'ember',
): string {
  const t = THEMES[theme];
  const title = meta.slug || meta.sessionId;
  const firstTime = stats.firstTimestamp ? formatTimestamp(stats.firstTimestamp) : '';
  const lastTime = stats.lastTimestamp ? formatTimestamp(stats.lastTimestamp) : '';

  const userPrefix = options.userEmoji ? `${options.userEmoji} ` : '';
  const assistantPrefix = options.assistantEmoji ? `${options.assistantEmoji} ` : '';

  let messagesHtml = '';

  for (const turn of turns) {
    const textBlocks = turn.blocks.filter((b) => b.type === 'text');
    const thinkingBlocks = turn.blocks.filter((b) => b.type === 'thinking');
    const toolBlocks = turn.blocks.filter((b) => b.type === 'tool_use');

    const hasText = textBlocks.length > 0;
    const hasThinking = options.includeThinking && thinkingBlocks.length > 0;
    const hasTools = options.includeTools && toolBlocks.length > 0;

    if (!hasText && !hasThinking && !hasTools) continue;

    const isUser = turn.role === 'user';
    const label = isUser
      ? `${userPrefix}${options.userLabel}`
      : `${assistantPrefix}${options.assistantLabel}`;
    const ts = formatTimestamp(turn.timestamp);

    messagesHtml += `<div class="message ${turn.role}">`;
    messagesHtml += `<div class="message-label">${escapeHtml(label)}`;
    if (ts) messagesHtml += `<span class="timestamp">${ts}</span>`;
    messagesHtml += `</div>`;

    // Thinking blocks (collapsible)
    if (hasThinking) {
      for (const tb of thinkingBlocks) {
        let thinking = (tb.thinking ?? '').trim();
        if (!thinking) continue;
        if (thinking.length > 1000) {
          thinking = thinking.substring(0, 1000) + '\n\n(... truncated for brevity)';
        }
        messagesHtml += `<div class="thinking" onclick="this.classList.toggle('open')">`;
        messagesHtml += `<div class="thinking-label">💭 Thinking (click to expand)</div>`;
        messagesHtml += `<div class="thinking-content">${escapeHtml(thinking)}</div>`;
        messagesHtml += `</div>`;
      }
    }

    // Tool details
    if (hasTools) {
      for (const tb of toolBlocks) {
        messagesHtml += `<div class="tool-detail">${formatToolDetailHtml(tb)}</div>`;
      }
    }

    // Text content
    for (const tb of textBlocks) {
      const text = (tb.text ?? '').trim();
      if (text) {
        messagesHtml += `<div class="message-text">${escapeHtml(text)}</div>`;
      }
    }

    messagesHtml += `</div>`;
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session Digest: ${escapeHtml(title)}</title>
<style>${buildCss(t)}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Session Digest: ${escapeHtml(title)}</h1>
    <div class="meta">
      <strong>Source:</strong> ${escapeHtml(meta.sessionId)}.jsonl<br>
      ${meta.firstDate ? `<strong>Date:</strong> ${meta.firstDate}<br>` : ''}
      ${firstTime ? `<strong>Time:</strong> ${firstTime} → ${lastTime}<br>` : ''}
    </div>
    <ul class="stats">
      <li>${userPrefix}${options.userLabel} messages: ${stats.userMessages}</li>
      <li>${assistantPrefix}${options.assistantLabel} responses: ${stats.assistantMessages}</li>
      ${options.includeThinking ? `<li>Thinking blocks: ${stats.thinkingBlocks}</li>` : ''}
      ${options.includeTools ? `<li>Tool calls: ${stats.toolCalls}</li>` : ''}
      <li>${options.userLabel} text: ${stats.userChars.toLocaleString()} chars</li>
      <li>${options.assistantLabel} text: ${stats.assistantChars.toLocaleString()} chars</li>
    </ul>
  </div>
  <hr>
  ${messagesHtml}
  <div class="powered-by">Exported by CinderACE Code</div>
</div>
</body>
</html>`;
}
