import JSZip from 'jszip';
import { Turn, SessionStats, SessionMeta, RenderOptions } from './types';
import { buildDocument, cleanOptions } from './renderer';
import { buildHtml } from './htmlRenderer';
import { getHtmlTheme } from './config';

/**
 * Export turns as structured JSON.
 */
export function buildJson(
  turns: Turn[],
  stats: SessionStats,
  meta: SessionMeta,
  options: RenderOptions,
): string {
  const doc = {
    meta: {
      sessionId: meta.sessionId,
      slug: meta.slug,
      date: meta.firstDate,
      firstTimestamp: stats.firstTimestamp,
      lastTimestamp: stats.lastTimestamp,
      exportedBy: 'CinderACE Code',
      exportedAt: new Date().toISOString(),
    },
    stats: {
      userMessages: stats.userMessages,
      assistantMessages: stats.assistantMessages,
      thinkingBlocks: stats.thinkingBlocks,
      toolCalls: stats.toolCalls,
      userChars: stats.userChars,
      assistantChars: stats.assistantChars,
    },
    settings: {
      userLabel: options.userLabel,
      assistantLabel: options.assistantLabel,
    },
    turns: turns.map((turn) => ({
      role: turn.role,
      timestamp: turn.timestamp,
      uuid: turn.uuid,
      text: turn.blocks
        .filter((b) => b.type === 'text')
        .map((b) => b.text)
        .join('\n'),
      thinking: options.includeThinking
        ? turn.blocks
            .filter((b) => b.type === 'thinking')
            .map((b) => b.thinking)
        : undefined,
      tools: options.includeTools
        ? turn.blocks
            .filter((b) => b.type === 'tool_use')
            .map((b) => ({ name: b.name, input: b.input }))
        : undefined,
    })),
  };

  return JSON.stringify(doc, null, 2);
}

/**
 * Export turns as JSONL (one JSON object per turn).
 */
export function buildJsonl(
  turns: Turn[],
  meta: SessionMeta,
  options: RenderOptions,
): string {
  const lines: string[] = [];

  // First line: metadata
  lines.push(JSON.stringify({
    type: 'meta',
    sessionId: meta.sessionId,
    slug: meta.slug,
    date: meta.firstDate,
    exportedBy: 'CinderACE Code',
    exportedAt: new Date().toISOString(),
  }));

  for (const turn of turns) {
    const entry: Record<string, unknown> = {
      role: turn.role,
      timestamp: turn.timestamp,
      uuid: turn.uuid,
      text: turn.blocks
        .filter((b) => b.type === 'text')
        .map((b) => b.text)
        .join('\n'),
    };

    if (options.includeThinking) {
      const thinking = turn.blocks
        .filter((b) => b.type === 'thinking')
        .map((b) => b.thinking);
      if (thinking.length > 0) entry.thinking = thinking;
    }

    if (options.includeTools) {
      const tools = turn.blocks
        .filter((b) => b.type === 'tool_use')
        .map((b) => ({ name: b.name, input: b.input }));
      if (tools.length > 0) entry.tools = tools;
    }

    // Skip empty entries (no text, no thinking, no tools)
    if (!entry.text && !entry.thinking && !entry.tools) continue;

    lines.push(JSON.stringify(entry));
  }

  return lines.join('\n');
}

/**
 * Build a ZIP file containing all export formats (clean + full variants of each).
 * Returns a Buffer of the ZIP file.
 */
export async function buildZip(
  turns: Turn[],
  stats: SessionStats,
  meta: SessionMeta,
  options: RenderOptions,
  baseName: string,
): Promise<Buffer> {
  const zip = new JSZip();
  const theme = getHtmlTheme();
  const clean = cleanOptions(options);

  // Markdown
  zip.file(`${baseName}_clean.md`, buildDocument(turns, stats, meta, clean));
  zip.file(`${baseName}_full.md`, buildDocument(turns, stats, meta, options));

  // HTML
  zip.file(`${baseName}_clean.html`, buildHtml(turns, stats, meta, clean, theme));
  zip.file(`${baseName}_full.html`, buildHtml(turns, stats, meta, options, theme));

  // JSON
  zip.file(`${baseName}_clean.json`, buildJson(turns, stats, meta, clean));
  zip.file(`${baseName}_full.json`, buildJson(turns, stats, meta, options));

  // JSONL
  zip.file(`${baseName}_clean.jsonl`, buildJsonl(turns, meta, clean));
  zip.file(`${baseName}_full.jsonl`, buildJsonl(turns, meta, options));

  return zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }) as Promise<Buffer>;
}
