# Changelog

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
