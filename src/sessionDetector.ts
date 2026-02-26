import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import * as vscode from 'vscode';
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
 * Find the most recently modified .jsonl file in a directory.
 * This is the "active" session.
 */
export function findActiveSession(dir: string): string | null {
  const files = findJsonlFiles(dir);
  if (files.length === 0) return null;

  let best: string | null = null;
  let bestMtime = 0;

  for (const f of files) {
    try {
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

/**
 * Get the list of recent sessions sorted by modification time (newest first).
 */
export function getRecentSessions(dir: string, count: number): string[] {
  const files = findJsonlFiles(dir);

  const withMtime = files
    .map((f) => {
      try {
        return { path: f, mtime: fs.statSync(f).mtimeMs };
      } catch {
        return null;
      }
    })
    .filter((x): x is { path: string; mtime: number } => x !== null);

  withMtime.sort((a, b) => b.mtime - a.mtime);

  return withMtime.slice(0, count).map((x) => x.path);
}
