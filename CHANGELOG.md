# Changelog

## 2.0.0 — 2026-06-04

### Added
- **Desktop app** — rewritten as standalone desktop application using pywebview + pystray
- **4 built-in CLI sources** — Claude Code, Codex, Fire Forge, and Gemini CLI auto-detection
- **Custom CLI support** — register any directory with JSONL, JSON, Markdown, or text session files
- **LLM-powered summarizer** — OpenAI, Anthropic, OpenRouter, and Ollama providers with template system
- **ember-memory integration** — ingest sessions and summaries directly into ember-memory
- **5 export formats** — Markdown, HTML (3 themes), JSON, JSONL, ZIP with clean/full variants
- **Desktop GUI** — project-grouped session browser with filtering, search, and preview pane
- **System tray** — background operation with tray icon
- **Right-click context menu** — Copy/Cut/Paste/Select All in UI

### Changed
- Complete rewrite from VS Code extension to desktop application
- Architecture split into detector, parser, renderer, and summarizer modules
- Session discovery now scans multiple CLI directories instead of single transcript file
- Export system unified across all formats with clean/full variants

## 0.4.0 — 2026-03-20

### Added
- **Session picker** — choose which session to export from a searchable list
- **Session title display** — shows user-renamed session names (via `custom-title` records)
- **First message preview** — unnamed sessions show the opening message for easy identification
- Session date and size shown in picker for quick context
- `SessionEntrypoint` type tracking (cli, vscode, legacy)

### Fixed
- CLI sessions no longer hijack "Export Current" when running Claude Code in both terminal and VSCode
- Local command stubs (`<local-command-caveat>`) no longer appear as exportable sessions
- Content block array format now parsed correctly for preview extraction (was only handling string format)

### Changed
- `findActiveSession` now filters by entrypoint and content type
- `SessionMeta` includes `entrypoint` field in exports
- Increased head buffer from 8KB to 16KB for more reliable first-message detection

## 0.3.1 — 2026-02-25

### Added
- Every format now produces both **clean** and **full** variants
- Simplified format picker — one entry per format, both variants generated automatically

### Changed
- Clean exports include thinking blocks (previously stripped)
- Format picker consolidated from 6 items to 5

## 0.3.0 — 2026-02-25

### Added
- **HTML export** with 3 CinderACE themes (Ember, Dark, Light)
- **JSON export** — structured with metadata and stats
- **JSONL export** — one JSON object per turn
- **ZIP export** — all formats bundled into one file
- Multi-select **format picker** in export flow
- `cinderaceSessions.htmlTheme` setting

### Changed
- Upgraded from markdown-only to 5 export formats

## 0.2.0 — 2026-02-25

### Added
- **Custom naming** — input box prompts for export name on each export
- On-demand export via **status bar flame button**

### Removed
- File watcher system (replaced with on-demand export)
- `cinderaceSessions.enabled` and `cinderaceSessions.debounceSeconds` settings

### Changed
- Architecture simplified from background watcher to click-to-export

## 0.1.0 — 2026-02-25

### Added
- Initial release
- JSONL parser for Claude Code transcripts
- Markdown export (clean + full)
- Thinking block extraction (collapsible)
- Tool usage details (file paths, commands, search patterns)
- Session statistics dashboard
- Auto-detection of Claude Code transcripts directory
- Configurable role labels and emoji
- Status bar integration
