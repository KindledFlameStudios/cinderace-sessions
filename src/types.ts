/** A single content block within a message. */
export interface ContentBlock {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result' | 'image';
  text?: string;
  thinking?: string;
  name?: string; // tool name for tool_use blocks
  input?: Record<string, unknown>; // tool input for tool_use blocks
}

/** A parsed conversation turn (one user or assistant message). */
export interface Turn {
  role: 'user' | 'assistant';
  blocks: ContentBlock[];
  timestamp: string;
  uuid: string;
}

/** Session statistics computed from parsed turns. */
export interface SessionStats {
  userMessages: number;
  assistantMessages: number;
  thinkingBlocks: number;
  toolCalls: number;
  userChars: number;
  assistantChars: number;
  firstTimestamp: string | null;
  lastTimestamp: string | null;
}

/** Known Claude Code session entrypoints. */
export type SessionEntrypoint = 'cli' | 'claude-vscode' | 'unknown';

/** Metadata extracted from the first message of a session. */
export interface SessionMeta {
  sessionId: string;
  slug: string;
  firstDate: string; // YYYY-MM-DD
  entrypoint: SessionEntrypoint;
}

/** Export mode configuration. */
export type ExportMode = 'clean' | 'full' | 'both';

/** Available export formats (each produces both clean and full variants). */
export type ExportFormat = 'md' | 'html' | 'json' | 'jsonl' | 'zip';

/** HTML theme options. */
export type HtmlTheme = 'ember' | 'dark' | 'light';

/** Render options passed to the markdown renderer. */
export interface RenderOptions {
  includeThinking: boolean;
  includeTools: boolean;
  userLabel: string;
  assistantLabel: string;
  userEmoji: string;
  assistantEmoji: string;
}
