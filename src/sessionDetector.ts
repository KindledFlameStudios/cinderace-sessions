import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as vscode from 'vscode';
import { SessionEntrypoint } from './types';
import { getTranscriptsDirectory } from './config';

/**
 * Derive the Claude Code project slug from a filesystem path.
 * Claude Code converts absolute paths by replacing '/' with '-'.
 * e.g. /home/seren → -home-seren
 *      /home/seren/my-project → -home-seren-my-project
 */
export function deriveProjectSlug(workspacePath: string): string {
  // Normalize and remove trailing slash
  const normalized = path.resolve(workspacePath).replace(/\/+$/, '');
  // Replace all '/' with '-'
  return normalized.replace(/\//g, '-');
}

/**
 * Get the Claude Code projects base directory.
 * Default: ~/.claude/projects/
 */
function getProjectsBaseDir(): string {
  return path.join(os.homedir(), '.claude', 'projects');
}

/**
 * Find the transcripts directory for the current workspace.
 * Returns null if not found.
 */
export function findTranscriptsDir(): string | null {
  // Check for user override first
  const override = getTranscriptsDirectory();
  if (override && fs.existsSync(override)) {
    return override;
  }

  const baseDir = getProjectsBaseDir();
  if (!fs.existsSync(baseDir)) return null;

  // Try workspace-based detection
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (workspaceFolders && workspaceFolders.length > 0) {
    const workspacePath = workspaceFolders[0].uri.fsPath;
    const slug = deriveProjectSlug(workspacePath);
    const projectDir = path.join(baseDir, slug);

    if (fs.existsSync(projectDir)) {
      return projectDir;
    }
  }

  // Fallback: find the most recently active project directory
  return findMostRecentProjectDir(baseDir);
}

/**
 * Scan all project directories and return the one with the most recent activity.
 */
function findMostRecentProjectDir(baseDir: string): string | null {
  let bestDir: string | null = null;
  let bestMtime = 0;

  try {
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;

      const dirPath = path.join(baseDir, entry.name);
      const jsonlFiles = findJsonlFiles(dirPath);

      for (const f of jsonlFiles) {
        if (!isExportableSession(f)) continue;
        const stat = fs.statSync(f);
        if (stat.mtimeMs > bestMtime) {
          bestMtime = stat.mtimeMs;
          bestDir = dirPath;
        }
      }
    }
  } catch {
    // Directory not readable
  }

  return bestDir;
}

/**
 * List all .jsonl files in a directory (non-recursive, top-level only).
 */
export function findJsonlFiles(dir: string): string[] {
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith('.jsonl'))
      .map((f) => path.join(dir, f));
  } catch {
    return [];
  }
}

/**
 * Read the entrypoint from a JSONL session file's first record.
 * Returns 'cli', 'claude-vscode', or 'unknown' for legacy/untagged sessions.
 */
export function readEntrypoint(filepath: string): SessionEntrypoint {
  try {
    const fd = fs.openSync(filepath, 'r');
    const buf = Buffer.alloc(2048);
    const bytesRead = fs.readSync(fd, buf, 0, 2048, 0);
    fs.closeSync(fd);

    const firstLine = buf.toString('utf-8', 0, bytesRead).split('\n')[0];
    const record = JSON.parse(firstLine);

    if (record.entrypoint === 'cli') return 'cli';
    if (record.entrypoint === 'claude-vscode') return 'claude-vscode';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

/**
 * Check if a session is a local-command stub rather than a real conversation.
 * VSCode creates tiny sessions for inline commands — these start with
 * `<local-command-caveat>` in the first user message and should be skipped.
 */
function isCommandStub(filepath: string): boolean {
  try {
    const fd = fs.openSync(filepath, 'r');
    const buf = Buffer.alloc(4096);
    const bytesRead = fs.readSync(fd, buf, 0, 4096, 0);
    fs.closeSync(fd);

    const chunk = buf.toString('utf-8', 0, bytesRead);
    return chunk.includes('<local-command-caveat>');
  } catch {
    return false;
  }
}

/**
 * Check if a session file is a real conversation exportable by the extension.
 * Excludes CLI sessions and local-command stubs.
 */
function isExportableSession(filepath: string): boolean {
  if (readEntrypoint(filepath) === 'cli') return false;
  if (isCommandStub(filepath)) return false;
  return true;
}

/**
 * Find the most recently modified .jsonl file in a directory.
 * This is the "active" session.
 * Filters out CLI sessions when running inside VSCode — only considers
 * vscode-originated and legacy (untagged) sessions.
 */
export function findActiveSession(dir: string): string | null {
  const files = findJsonlFiles(dir);
  if (files.length === 0) return null;

  let best: string | null = null;
  let bestMtime = 0;

  for (const f of files) {
    try {
      if (!isExportableSession(f)) continue;

      const stat = fs.statSync(f);
      if (stat.mtimeMs > bestMtime) {
        bestMtime = stat.mtimeMs;
        best = f;
      }
    } catch {
      continue;
    }
  }

  return best;
}

/** Info for a session picker item. */
export interface SessionPickerItem {
  filepath: string;
  date: string;
  size: string;
  preview: string;
  title: string;
  entrypoint: SessionEntrypoint;
  mtime: number;
}

/**
 * Read the custom title from a session JSONL file.
 * Claude Code stores renames as {"type":"custom-title","customTitle":"..."} records.
 * Takes the last one found (most recent rename). Scans the tail of the file first
 * for efficiency on large sessions, then falls back to a full scan.
 */
function readSessionTitle(filepath: string): string {
  try {
    const stat = fs.statSync(filepath);
    const TAIL_SIZE = 64 * 1024; // Read last 64KB

    // For large files, try tail first (titles are often written after session start)
    if (stat.size > TAIL_SIZE) {
      const fd = fs.openSync(filepath, 'r');
      const buf = Buffer.alloc(TAIL_SIZE);
      const offset = stat.size - TAIL_SIZE;
      fs.readSync(fd, buf, 0, TAIL_SIZE, offset);
      fs.closeSync(fd);

      const chunk = buf.toString('utf-8');
      const lines = chunk.split('\n').reverse();
      for (const line of lines) {
        if (!line.includes('custom-title')) continue;
        try {
          const record = JSON.parse(line);
          if (record.type === 'custom-title' && record.customTitle) {
            return record.customTitle;
          }
        } catch {
          continue;
        }
      }
    }

    // Small file or title not in tail — scan from start (capped at 256KB)
    const fd = fs.openSync(filepath, 'r');
    const readSize = Math.min(stat.size, 256 * 1024);
    const buf = Buffer.alloc(readSize);
    fs.readSync(fd, buf, 0, readSize, 0);
    fs.closeSync(fd);

    const chunk = buf.toString('utf-8');
    let title = '';
    for (const line of chunk.split('\n')) {
      if (!line.includes('custom-title')) continue;
      try {
        const record = JSON.parse(line);
        if (record.type === 'custom-title' && record.customTitle) {
          title = record.customTitle; // Keep scanning — last one wins
        }
      } catch {
        continue;
      }
    }
    return title;
  } catch {
    return '';
  }
}

/**
 * Build a list of exportable sessions with metadata for a picker UI.
 * Reads session title, first user message, and date from each session.
 */
export function getExportableSessions(dir: string, count: number): SessionPickerItem[] {
  const files = findJsonlFiles(dir);

  const items: SessionPickerItem[] = [];

  for (const f of files) {
    try {
      if (!isExportableSession(f)) continue;

      const stat = fs.statSync(f);
      const sizeMB = (stat.size / (1024 * 1024)).toFixed(1);
      const sizeStr = stat.size < 1024 * 1024
        ? `${(stat.size / 1024).toFixed(0)}KB`
        : `${sizeMB}MB`;

      // Read session title (user rename)
      const title = readSessionTitle(f);

      // Read first ~16KB to find date and first user message
      // (hook progress and queue records can push the first user message further in)
      const fd = fs.openSync(f, 'r');
      const readHead = Math.min(stat.size, 16384);
      const buf = Buffer.alloc(readHead);
      const bytesRead = fs.readSync(fd, buf, 0, readHead, 0);
      fs.closeSync(fd);

      const chunk = buf.toString('utf-8', 0, bytesRead);
      const lines = chunk.split('\n');

      let date = '';
      let preview = '';
      let entrypoint: SessionEntrypoint = 'unknown';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const record = JSON.parse(line);
          if (!date && record.timestamp) {
            date = record.timestamp.substring(0, 10);
          }
          if (entrypoint === 'unknown' && record.entrypoint) {
            entrypoint = record.entrypoint === 'cli' ? 'cli'
              : record.entrypoint === 'claude-vscode' ? 'claude-vscode'
              : 'unknown';
          }
          if (!preview && record.type === 'user' && record.message?.content) {
            let content = '';
            if (typeof record.message.content === 'string') {
              content = record.message.content;
            } else if (Array.isArray(record.message.content)) {
              // Content blocks array — find first text block
              for (const block of record.message.content) {
                if (block?.type === 'text' && typeof block.text === 'string') {
                  content = block.text;
                  break;
                }
              }
            }
            content = content.replace(/<[^>]*>/g, '').trim();
            if (content) {
              preview = content.substring(0, 100);
            }
          }
          if (date && preview) break;
        } catch {
          continue;
        }
      }

      items.push({
        filepath: f,
        date: date || 'Unknown',
        size: sizeStr,
        preview: preview || '(no preview)',
        title,
        entrypoint,
        mtime: stat.mtimeMs,
      });
    } catch {
      continue;
    }
  }

  items.sort((a, b) => b.mtime - a.mtime);
  return items.slice(0, count);
}

/**
 * Get the list of recent sessions sorted by modification time (newest first).
 * Filters out CLI sessions — only includes vscode and legacy sessions.
 */
export function getRecentSessions(dir: string, count: number): string[] {
  const files = findJsonlFiles(dir);

  const withMtime = files
    .map((f) => {
      try {
        if (!isExportableSession(f)) return null;
        return { path: f, mtime: fs.statSync(f).mtimeMs };
      } catch {
        return null;
      }
    })
    .filter((x): x is { path: string; mtime: number } => x !== null);

  withMtime.sort((a, b) => b.mtime - a.mtime);

  return withMtime.slice(0, count).map((x) => x.path);
}
