import * as fs from 'fs';
import { ContentBlock, Turn, SessionStats, SessionMeta } from './types';

/**
 * Parse a Claude Code JSONL transcript file into structured turns.
 * Ported from transcript_digest.py — parse_jsonl_transcript()
 */
export function parseJsonlTranscript(filepath: string): Turn[] {
  const content = fs.readFileSync(filepath, 'utf-8');
  const lines = content.split('\n');
  const turns: Turn[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let record: Record<string, unknown>;
    try {
      record = JSON.parse(trimmed);
    } catch {
      continue;
    }

    // Only process user and assistant message records
    const recordType = record.type as string | undefined;
    if (recordType !== 'user' && recordType !== 'assistant') continue;

    const message = record.message as Record<string, unknown> | undefined;
    if (!message) continue;

    const role = message.role as string | undefined;
    if (role !== 'user' && role !== 'assistant') continue;

    const rawContent = message.content;
    const timestamp = (record.timestamp as string) ?? '';

    // Content can be a string (compact summaries) or array of blocks
    let blocks: ContentBlock[] = [];

    if (typeof rawContent === 'string') {
      blocks = [{ type: 'text', text: rawContent }];
    } else if (Array.isArray(rawContent)) {
      for (const block of rawContent) {
        if (typeof block !== 'object' || block === null) continue;
        const b = block as Record<string, unknown>;
        const blockType = b.type as string | undefined;

        if (blockType === 'text' && typeof b.text === 'string') {
          blocks.push({ type: 'text', text: b.text });
        } else if (blockType === 'thinking' && typeof b.thinking === 'string') {
          blocks.push({ type: 'thinking', thinking: b.thinking });
        } else if (blockType === 'tool_use') {
          blocks.push({
            type: 'tool_use',
            name: (b.name as string) ?? 'unknown',
            input: (b.input as Record<string, unknown>) ?? {},
          });
        }
      }
    }

    if (blocks.length === 0) continue;

    turns.push({
      role: role as 'user' | 'assistant',
      blocks,
      timestamp,
      uuid: (record.uuid as string) ?? '',
    });
  }

  return turns;
}

/**
 * Generate session statistics from parsed turns.
 * Ported from transcript_digest.py — build_stats()
 */
export function buildStats(turns: Turn[]): SessionStats {
  let userMessages = 0;
  let assistantMessages = 0;
  let thinkingBlocks = 0;
  let toolCalls = 0;
  let userChars = 0;
  let assistantChars = 0;
  let firstTimestamp: string | null = null;
  let lastTimestamp: string | null = null;

  for (const turn of turns) {
    if (turn.timestamp) {
      if (!firstTimestamp) firstTimestamp = turn.timestamp;
      lastTimestamp = turn.timestamp;
    }

    const hasText = turn.blocks.some((b) => b.type === 'text');

    if (turn.role === 'user' && hasText) userMessages++;
    else if (turn.role === 'assistant' && hasText) assistantMessages++;

    for (const block of turn.blocks) {
      if (block.type === 'text') {
        const len = (block.text ?? '').length;
        if (turn.role === 'user') userChars += len;
        else assistantChars += len;
      } else if (block.type === 'thinking') {
        thinkingBlocks++;
      } else if (block.type === 'tool_use') {
        toolCalls++;
      }
    }
  }

  return {
    userMessages,
    assistantMessages,
    thinkingBlocks,
    toolCalls,
    userChars,
    assistantChars,
    firstTimestamp,
    lastTimestamp,
  };
}

/**
 * Extract session metadata from the JSONL file (reads first few lines).
 */
export function extractSessionMeta(filepath: string): SessionMeta {
  const content = fs.readFileSync(filepath, 'utf-8');
  const lines = content.split('\n');

  let sessionId = '';
  let slug = '';
  let firstDate = '';

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    try {
      const record = JSON.parse(trimmed);
      if (!sessionId && record.sessionId) {
        sessionId = record.sessionId;
      }
      if (!slug && record.slug) {
        slug = record.slug;
      }
      if (!firstDate && record.timestamp) {
        firstDate = record.timestamp.substring(0, 10); // YYYY-MM-DD
      }
      // Stop once we have all metadata
      if (sessionId && slug && firstDate) break;
    } catch {
      continue;
    }
  }

  // Fallback: use filename as sessionId
  if (!sessionId) {
    const basename = filepath.split('/').pop() ?? '';
    sessionId = basename.replace('.jsonl', '');
  }

  if (!firstDate) {
    firstDate = new Date().toISOString().substring(0, 10);
  }

  return { sessionId, slug, firstDate };
}
