import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import { ExportFormat } from './types';
import { parseJsonlTranscript, buildStats, extractSessionMeta } from './parser';
import { buildDocument, cleanOptions, formatShortTime } from './renderer';
import { buildHtml } from './htmlRenderer';
import { buildJson, buildJsonl, buildZip } from './formats';
import {
  findTranscriptsDir,
  findActiveSession,
  getRecentSessions,
} from './sessionDetector';
import {
  getOutputDirectory,
  setOutputDirectory,
  getRenderOptions,
  getHtmlTheme,
} from './config';

let outputChannel: vscode.OutputChannel;
let statusBar: vscode.StatusBarItem;

function log(message: string): void {
  const ts = new Date().toLocaleTimeString();
  outputChannel.appendLine(`[${ts}] ${message}`);
}

async function ensureOutputDir(): Promise<string | null> {
  let dir = getOutputDirectory();

  if (!dir) {
    const selected = await vscode.window.showOpenDialog({
      canSelectFolders: true,
      canSelectFiles: false,
      canSelectMany: false,
      openLabel: 'Select Output Directory',
      title: 'Where should CinderACE Sessions save session digests?',
    });

    if (!selected || selected.length === 0) {
      vscode.window.showWarningMessage('CinderACE Sessions: No output directory selected.');
      return null;
    }

    dir = selected[0].fsPath;
    await setOutputDirectory(dir);
    log(`Output directory set: ${dir}`);
  }

  return dir;
}

function atomicWrite(filepath: string, content: string | Buffer): void {
  const tmpPath = filepath + '.tmp';
  if (typeof content === 'string') {
    fs.writeFileSync(tmpPath, content, 'utf-8');
  } else {
    fs.writeFileSync(tmpPath, content);
  }
  fs.renameSync(tmpPath, filepath);
}

function sanitizeFilename(name: string): string {
  return name
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9_\-\.]/g, '');
}

/** Format picker items — each produces both clean and full variants. */
const FORMAT_ITEMS: Array<{ label: string; description: string; format: ExportFormat }> = [
  { label: '$(markdown) Markdown', description: 'Clean + full .md files', format: 'md' },
  { label: '$(code) HTML', description: 'Clean + full themed HTML with CinderACE styling', format: 'html' },
  { label: '$(json) JSON', description: 'Clean + full structured JSON with metadata', format: 'json' },
  { label: '$(list-flat) JSONL', description: 'Clean + full, one JSON object per turn', format: 'jsonl' },
  { label: '$(file-zip) ZIP (Everything)', description: 'All formats, both variants, in one ZIP', format: 'zip' },
];

/**
 * Show format picker and return selected formats.
 */
async function pickFormats(): Promise<ExportFormat[] | undefined> {
  const items = FORMAT_ITEMS.map((item) => ({
    ...item,
    picked: false,
  }));

  const selected = await vscode.window.showQuickPick(items, {
    canPickMany: true,
    placeHolder: 'Select export format(s)',
    title: 'CinderACE Sessions — Export Formats',
  });

  if (!selected || selected.length === 0) return undefined;

  return selected.map((s) => s.format);
}

/**
 * Export a single JSONL file in the selected formats.
 */
async function exportFile(
  filepath: string,
  outputDir: string,
  formats: ExportFormat[],
  customName?: string,
): Promise<boolean> {
  log(`Exporting: ${path.basename(filepath)} → [${formats.join(', ')}]`);

  const turns = parseJsonlTranscript(filepath);
  if (turns.length === 0) {
    log('No messages found, skipping.');
    return false;
  }

  const stats = buildStats(turns);
  const meta = extractSessionMeta(filepath);
  const renderOpts = getRenderOptions();

  const displayName = customName || meta.slug || meta.sessionId;
  const fileName = customName ? sanitizeFilename(customName) : (meta.slug || meta.sessionId);
  const baseName = `${meta.firstDate}_${fileName}`;
  const exportMeta = { ...meta, slug: displayName };

  fs.mkdirSync(outputDir, { recursive: true });

  const clean = cleanOptions(renderOpts);
  const theme = getHtmlTheme();

  for (const format of formats) {
    switch (format) {
      case 'md': {
        atomicWrite(path.join(outputDir, `${baseName}_clean.md`), buildDocument(turns, stats, exportMeta, clean));
        atomicWrite(path.join(outputDir, `${baseName}_full.md`), buildDocument(turns, stats, exportMeta, renderOpts));
        log(`Saved: ${baseName}_clean.md + ${baseName}_full.md`);
        break;
      }
      case 'html': {
        atomicWrite(path.join(outputDir, `${baseName}_clean.html`), buildHtml(turns, stats, exportMeta, clean, theme));
        atomicWrite(path.join(outputDir, `${baseName}_full.html`), buildHtml(turns, stats, exportMeta, renderOpts, theme));
        log(`Saved: ${baseName}_clean.html + ${baseName}_full.html (${theme} theme)`);
        break;
      }
      case 'json': {
        atomicWrite(path.join(outputDir, `${baseName}_clean.json`), buildJson(turns, stats, exportMeta, clean));
        atomicWrite(path.join(outputDir, `${baseName}_full.json`), buildJson(turns, stats, exportMeta, renderOpts));
        log(`Saved: ${baseName}_clean.json + ${baseName}_full.json`);
        break;
      }
      case 'jsonl': {
        atomicWrite(path.join(outputDir, `${baseName}_clean.jsonl`), buildJsonl(turns, exportMeta, clean));
        atomicWrite(path.join(outputDir, `${baseName}_full.jsonl`), buildJsonl(turns, exportMeta, renderOpts));
        log(`Saved: ${baseName}_clean.jsonl + ${baseName}_full.jsonl`);
        break;
      }
      case 'zip': {
        const zipBuffer = await buildZip(turns, stats, exportMeta, renderOpts, baseName);
        atomicWrite(path.join(outputDir, `${baseName}.zip`), zipBuffer);
        log(`Saved: ${baseName}.zip (all formats, both variants)`);
        break;
      }
    }
  }

  return true;
}

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('CinderACE Sessions');
  context.subscriptions.push(outputChannel);

  statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    50,
  );
  statusBar.command = 'cinderaceSessions.exportCurrent';
  statusBar.text = '$(flame) CinderACE';
  statusBar.tooltip = 'Export current Claude Code session';
  statusBar.show();
  context.subscriptions.push(statusBar);

  // --- Commands ---

  // Export Current Session
  context.subscriptions.push(
    vscode.commands.registerCommand('cinderaceSessions.exportCurrent', async () => {
      const transcriptsDir = findTranscriptsDir();
      if (!transcriptsDir) {
        vscode.window.showWarningMessage(
          'CinderACE Sessions: No Claude Code transcripts found for this workspace.',
        );
        return;
      }

      const active = findActiveSession(transcriptsDir);
      if (!active) {
        vscode.window.showWarningMessage('CinderACE Sessions: No active session found.');
        return;
      }

      // Step 1: Custom name
      const meta = extractSessionMeta(active);
      const defaultName = meta.slug || meta.sessionId;

      const customName = await vscode.window.showInputBox({
        prompt: 'Name this export (or press Enter for default)',
        placeHolder: defaultName,
        value: '',
      });

      if (customName === undefined) return;

      // Step 2: Pick formats
      const formats = await pickFormats();
      if (!formats) return;

      // Step 3: Ensure output dir
      const outputDir = await ensureOutputDir();
      if (!outputDir) return;

      // Step 4: Export
      statusBar.text = '$(sync~spin) Exporting...';

      const success = await exportFile(active, outputDir, formats, customName || undefined);

      if (success) {
        const timeStr = formatShortTime(new Date());
        const formatList = formats.join(', ');
        statusBar.text = `$(check) Exported ${timeStr}`;
        vscode.window.showInformationMessage(
          `CinderACE Sessions: Exported [${formatList}] to ${outputDir}`,
        );
        setTimeout(() => {
          statusBar.text = '$(flame) CinderACE';
        }, 5000);
      } else {
        statusBar.text = '$(flame) CinderACE';
        vscode.window.showWarningMessage('CinderACE Sessions: No messages found in session.');
      }
    }),
  );

  // Export Recent Sessions (uses markdown both by default for batch)
  context.subscriptions.push(
    vscode.commands.registerCommand('cinderaceSessions.exportRecent', async () => {
      const transcriptsDir = findTranscriptsDir();
      if (!transcriptsDir) {
        vscode.window.showWarningMessage(
          'CinderACE Sessions: No Claude Code transcripts found.',
        );
        return;
      }

      const countStr = await vscode.window.showInputBox({
        prompt: 'How many recent sessions to export?',
        value: '5',
        validateInput: (v) => {
          const n = parseInt(v, 10);
          return isNaN(n) || n < 1 ? 'Enter a positive number' : null;
        },
      });

      if (!countStr) return;

      const formats = await pickFormats();
      if (!formats) return;

      const count = parseInt(countStr, 10);
      const sessions = getRecentSessions(transcriptsDir, count);

      if (sessions.length === 0) {
        vscode.window.showWarningMessage('CinderACE Sessions: No sessions found.');
        return;
      }

      const outputDir = await ensureOutputDir();
      if (!outputDir) return;

      statusBar.text = '$(sync~spin) Exporting...';

      let exported = 0;
      for (const session of sessions) {
        const success = await exportFile(session, outputDir, formats);
        if (success) exported++;
      }

      statusBar.text = '$(flame) CinderACE';
      vscode.window.showInformationMessage(
        `CinderACE Sessions: Exported ${exported} of ${sessions.length} session(s).`,
      );
    }),
  );

  // Open Output Directory
  context.subscriptions.push(
    vscode.commands.registerCommand('cinderaceSessions.openOutput', async () => {
      const outputDir = getOutputDirectory();
      if (!outputDir) {
        vscode.window.showWarningMessage(
          'CinderACE Sessions: No output directory configured. Run an export first.',
        );
        return;
      }
      const uri = vscode.Uri.file(outputDir);
      await vscode.commands.executeCommand('revealFileInOS', uri);
    }),
  );

  // Select Output Directory
  context.subscriptions.push(
    vscode.commands.registerCommand('cinderaceSessions.selectOutput', async () => {
      const selected = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectFiles: false,
        canSelectMany: false,
        openLabel: 'Select Output Directory',
        title: 'Where should CinderACE Sessions save session digests?',
      });

      if (selected && selected.length > 0) {
        await setOutputDirectory(selected[0].fsPath);
        vscode.window.showInformationMessage(
          `CinderACE Sessions: Output directory set to ${selected[0].fsPath}`,
        );
      }
    }),
  );

  log('CinderACE Sessions v0.3.1 activated.');
}

export function deactivate(): void {
  // Nothing to clean up in on-demand mode
}
