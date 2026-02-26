import { ContentBlock, Turn, SessionStats, SessionMeta, RenderOptions } from './types';

/**
 * Format a tool_use block into a readable one-liner.
 * e.g. "Read: /home/seren/src/app.ts"
 *      "Edit: /home/seren/src/app.ts"
 *      "Bash: npm run build"
 *      "Grep: pattern 'useState' in *.tsx"
 */
function formatToolDetail(block: ContentBlock): string {
  const name = block.name ?? 'unknown';
  const input = block.input ?? {};

  switch (name) {
    case 'Read':
      return `**Read** \`${input.file_path ?? 'unknown'}\``;

    case 'Edit':
      return `**Edit** \`${input.file_path ?? 'unknown'}\``;

    case 'Write':
      return `**Write** \`${input.file_path ?? 'unknown'}\``;

    case 'Bash': {
      const cmd = String(input.command ?? '').trim();
      const preview = cmd.length > 120 ? cmd.substring(0, 120) + '...' : cmd;
      return `**Bash** \`${preview}\``;
    }

    case 'Grep': {
      const pattern = input.pattern ?? '';
      const glob = input.glob ? ` in ${input.glob}` : '';
      const path = input.path ? ` (${input.path})` : '';
      return `**Grep** \`${pattern}\`${glob}${path}`;
    }

    case 'Glob':
      return `**Glob** \`${input.pattern ?? ''}\``;

    case 'Task': {
      const desc = input.description ?? input.prompt ?? '';
      const preview = String(desc).substring(0, 80);
      return `**Task** ${preview}${String(desc).length > 80 ? '...' : ''}`;
    }

    case 'WebFetch':
      return `**WebFetch** \`${input.url ?? ''}\``;

    case 'WebSearch':
      return `**WebSearch** \`${input.query ?? ''}\``;

    case 'TodoWrite':
      return `**TodoWrite** updated task list`;

    case 'NotebookEdit':
      return `**NotebookEdit** \`${input.notebook_path ?? ''}\``;

    default: {
      // Generic fallback — show first string value from input
      const firstVal = Object.values(input).find((v) => typeof v === 'string');
      if (firstVal) {
        const preview = String(firstVal).substring(0, 80);
        return `**${name}** ${preview}`;
      }
      return `**${name}**`;
    }
  }
}

/**
 * Format ISO timestamp to readable HH:MM:SS.
 * Ported from transcript_digest.py — format_timestamp()
 */
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

/**
 * Format a short time for display (e.g. "2:45 PM").
 */
export function formatShortTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Build clean markdown digest from parsed turns.
 * Ported from transcript_digest.py — build_digest()
 *
 * @param turns - Parsed conversation turns
 * @param options - Render configuration (labels, emoji, thinking/tools inclusion)
 */
export function buildDigest(turns: Turn[], options: RenderOptions): string {
  const lines: string[] = [];

  for (const turn of turns) {
    const textBlocks = turn.blocks.filter((b) => b.type === 'text');
    const thinkingBlocks = turn.blocks.filter((b) => b.type === 'thinking');
    const toolBlocks = turn.blocks.filter((b) => b.type === 'tool_use');

    // Skip truly empty turns (keep if they have text, thinking we want, or tools we want)
    const hasText = textBlocks.length > 0;
    const hasWantedThinking = options.includeThinking && thinkingBlocks.length > 0;
    const hasWantedTools = options.includeTools && toolBlocks.length > 0;
    if (!hasText && !hasWantedThinking && !hasWantedTools) {
      continue;
    }

    const ts = formatTimestamp(turn.timestamp);

    // Role label with optional emoji
    const isUser = turn.role === 'user';
    const label = isUser ? options.userLabel : options.assistantLabel;
    const emoji = isUser ? options.userEmoji : options.assistantEmoji;
    const roleLabel = emoji ? `${emoji} ${label}` : label;
    const tsDisplay = ts ? ` *(${ts})*` : '';

    lines.push(`\n---\n\n### ${roleLabel}${tsDisplay}\n`);

    // Thinking blocks (collapsible)
    if (options.includeThinking && thinkingBlocks.length > 0) {
      for (const tb of thinkingBlocks) {
        let thinking = (tb.thinking ?? '').trim();
        if (!thinking) continue;

        // Truncate very long thinking blocks
        if (thinking.length > 1000) {
          thinking = thinking.substring(0, 1000) + '\n\n*(... truncated for brevity)*';
        }
        lines.push(
          `<details>\n<summary>Thinking</summary>\n\n${thinking}\n\n</details>\n`,
        );
      }
    }

    // Tool summaries with details
    if (options.includeTools && toolBlocks.length > 0) {
      for (const tb of toolBlocks) {
        const detail = formatToolDetail(tb);
        lines.push(`> ${detail}\n`);
      }
    }

    // Text content
    for (const tb of textBlocks) {
      const text = (tb.text ?? '').trim();
      if (text) {
        lines.push(`${text}\n`);
      }
    }
  }

  return lines.join('\n');
}

/**
 * Build the full markdown document with header, stats, and digest.
 * Ported from transcript_digest.py — process_file() header generation.
 */
export function buildDocument(
  turns: Turn[],
  stats: SessionStats,
  meta: SessionMeta,
  options: RenderOptions,
): string {
  const parts: string[] = [];

  // Header
  const title = meta.slug || meta.sessionId;
  parts.push(`# Session Digest: ${title}\n`);
  parts.push(`**Source:** \`${meta.sessionId}.jsonl\``);

  if (stats.firstTimestamp) {
    const firstTime = formatTimestamp(stats.firstTimestamp);
    const lastTime = formatTimestamp(stats.lastTimestamp ?? stats.firstTimestamp);
    parts.push(`**Date:** ${meta.firstDate}`);
    parts.push(`**Time:** ${firstTime} → ${lastTime}`);
  }

  // Stats dashboard
  parts.push('');
  parts.push('**Stats:**');
  const userPrefix = options.userEmoji ? `${options.userEmoji} ` : '';
  const assistantPrefix = options.assistantEmoji ? `${options.assistantEmoji} ` : '';
  parts.push(`- ${userPrefix}${options.userLabel} messages: ${stats.userMessages}`);
  parts.push(`- ${assistantPrefix}${options.assistantLabel} responses: ${stats.assistantMessages}`);

  if (options.includeThinking) {
    parts.push(`- Thinking blocks: ${stats.thinkingBlocks}`);
  }
  if (options.includeTools) {
    parts.push(`- Tool calls: ${stats.toolCalls}`);
  }

  parts.push(`- ${options.userLabel} text: ${stats.userChars.toLocaleString()} chars`);
  parts.push(`- ${options.assistantLabel} text: ${stats.assistantChars.toLocaleString()} chars`);
  parts.push('\n---');

  // Digest body
  const digest = buildDigest(turns, options);
  parts.push(digest);

  return parts.join('\n');
}

/**
 * Build a clean-mode render options override (keeps thinking, strips tools).
 */
export function cleanOptions(base: RenderOptions): RenderOptions {
  return {
    ...base,
    includeThinking: true,
    includeTools: false,
  };
}
