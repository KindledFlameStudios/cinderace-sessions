import * as vscode from 'vscode';
import { ExportMode, RenderOptions, HtmlTheme } from './types';

const SECTION = 'cinderaceSessions';

function get<T>(key: string): T | undefined {
  return vscode.workspace.getConfiguration(SECTION).get<T>(key);
}

export function getOutputDirectory(): string {
  return get<string>('outputDirectory') ?? '';
}

export async function setOutputDirectory(dir: string): Promise<void> {
  await vscode.workspace.getConfiguration(SECTION).update(
    'outputDirectory',
    dir,
    vscode.ConfigurationTarget.Global,
  );
}

export function getExportMode(): ExportMode {
  return (get<string>('exportMode') as ExportMode) ?? 'both';
}

export function getTranscriptsDirectory(): string {
  return get<string>('transcriptsDirectory') ?? '';
}

export function getHtmlTheme(): HtmlTheme {
  return (get<string>('htmlTheme') as HtmlTheme) ?? 'ember';
}

export function getRenderOptions(): RenderOptions {
  return {
    includeThinking: get<boolean>('includeThinking') ?? true,
    includeTools: get<boolean>('includeTools') ?? true,
    userLabel: get<string>('userLabel') ?? 'User',
    assistantLabel: get<string>('assistantLabel') ?? 'Assistant',
    userEmoji: get<string>('userEmoji') ?? '',
    assistantEmoji: get<string>('assistantEmoji') ?? '',
  };
}
