# CinderACE-Sessions v2 — Design Document

**Date:** 2026-05-16  
**Status:** Approved  
**Authors:** Justin & Solace  

## Overview

CinderACE-Sessions v2 is a complete rebirth of the original VS Code extension. It becomes a standalone desktop application for discovering, browsing, exporting, and summarizing AI CLI conversation sessions. Built on the same architectural DNA as ember-memory, it pairs naturally with it — CinderACE-Sessions provides clean data, ember-memory provides persistent memory.

**Purpose:** We need this for ourselves first. A real tool to manage our own growing session data across multiple CLIs, extract value from it, and feed it into our memory system. Free for everyone, paired with ember-memory, visibility for KFS.

## Architecture

### Stack

| Layer | Technology |
|-------|-----------|
| Shell | Python 3.10+ / pywebview 5+ (native OS WebView) |
| Frontend | Vanilla HTML + CSS + JavaScript (no framework, no build step) |
| Backend | Python (`SessionsAPI` class, 30+ methods exposed via pywebview bridge) |
| System Tray | PyQt6 (primary, Linux) / pystray (fallback, cross-platform) |
| Packaging | setuptools via pyproject.toml; PyInstaller for binary; .desktop file |
| Entry Points | `cinderace-sessions` (console), `cinderace-sessions-controller` (gui-script) |
| Singleton | Custom `acquire_instance_lock()` — prevents duplicate instances |

### Rationale

Mirrors ember-memory's architecture exactly. Same patterns, same packaging story, same "feel" when both tools are installed. When someone uses both, they recognize them as a pair.

The pywebview stack was chosen over:
- **Web dashboard (Flask/FastAPI):** Loses the app-like presence. A tab you open, not a tool you live in.
- **Tauri (Rust + React):** Adds Rust IPC complexity for no benefit — we're not doing real-time audio or needing the security sandbox. Every new feature would need both a Rust command and a React component. The Python backend handles filesystem parsing naturally; no sidecar needed.

### Directory Structure

```
CinderACE-Sessions/
  cinderace_sessions/
    __init__.py
    __main__.py              # CLI dispatcher (controller, tray, setup, install-desktop)
    controller_app.py        # SessionsAPI backend + pywebview window
    config.py                # App config, paths, settings persistence
    detector/
      __init__.py
      base.py                # Base CLIDetector class
      claude_code.py         # ~/.claude/projects/ scanner
      codex.py               # Codex session scanner
      gemini_cli.py          # Gemini CLI session scanner
      registry.py            # Detector registration + custom CLI management
    parser/
      __init__.py
      base.py                # Base SessionParser class
      jsonl_parser.py         # JSONL format (Claude Code, Codex, Gemini)
      markdown_parser.py     # Markdown conversation logs
      text_parser.py          # Plain text / generic logs
    renderer/
      __init__.py
      markdown.py            # Markdown export
      html.py                # HTML export (themed: ember/dark/light)
      json_export.py         # JSON structured export
      jsonl_export.py         # JSONL export
      zip_export.py           # ZIP bundle exporter
    summarizer/
      __init__.py
      engine.py              # LLM API client (OpenAI, Anthropic, OpenRouter)
      template.py             # Template prompt management + defaults
      ollama.py               # Local model support
    ember_bridge.py           # ember-memory ingestion bridge
    controller_assets/
      ui.html
      ui.css
      ui.js
  controller/
    __init__.py
    __main__.py
    tray.py                  # System tray (Qt6 primary, pystray fallback)
  tests/
    conftest.py
    test_detector.py
    test_parser.py
    test_renderer.py
    test_summarizer.py
    test_ember_bridge.py
  pyproject.toml
  requirements.txt
  LICENSE
  README.md
  docs/
    ARCHITECTURE.md
    CONFIGURATION.md
```

### Key Design Decisions

1. **Detector / Parser separation** — A detector *finds* sessions on disk. A parser *reads* them. Different CLIs may share the same parser format (Claude Code, Codex, and Gemini CLI all use JSONL, but with different directory structures). This separation lets custom CLI registrations specify "use this parser" without writing code.

2. **Summarizer is opt-in and explicit** — No background API calls, no surprise token spend. User selects a session, hits "Summarize," confirms the action. The template prompt is editable and saved locally.

3. **ember_bridge uses library import when available, HTTP API when not** — If ember-memory is installed as a Python package, direct import. If running as a server on port 2214, HTTP calls. If neither, graceful disable with tooltip.

## UI Design

**Window:** 840×660 (min 700×550), dark theme (#050505 background), ember-orange accent (#FF7820). Same visual identity as ember-memory.

### Tab 1: Sessions (default, timeline-first)

The primary view. Lands here on open.

- **Top bar:** Date range filter (Today / This Week / This Month / All) + CLI source filter dropdown (All / Claude Code / Codex / Gemini CLI / Custom...) + text search
- **Left panel:** Session list, sorted most-recent-first. Each item shows:
  - First message preview (truncated)
  - Date + time
  - CLI source badge (color-coded icon)
  - Project slug or custom title
  - Message count + file size
- **Right panel:** Selected session preview — rendered markdown view, collapsible thinking blocks
- **Session actions:** Export (format dropdown), Summarize, Ingest to ember-memory, Open in file manager

CLI source badge colors:
- Claude Code = orange
- Codex = blue
- Gemini CLI = red
- Custom = user-configurable

### Tab 2: Projects (secondary, project-first grouping)

Groups sessions by project/repository.

- **Left panel:** Project list sorted by most recent activity. Each shows project slug, CLI sources found, session count, last active date
- **Right panel:** Sessions within the selected project, same list format as Tab 1

### Tab 3: Summarizer (LLM workspace)

- **Provider config:** Endpoint selector (OpenAI / Anthropic / OpenRouter / Ollama / Custom URL), API key input (stored locally only), model selector
- **Template editor:** Default prompt template provided with extraction categories (key decisions, emotional moments, growth/learning, action items, technical insights). User can edit and save custom templates.
- **History:** Past summaries with session reference, one-click re-view

### Tab 4: Settings

- **General:** Output directory, default export format, auto-detect on launch
- **Display:** HTML theme (ember/dark/light), thinking blocks, tool calls, custom labels
- **Custom CLIs:** Add/remove/edit CLI registrations (name, directory path, format, icon color)
- **ember-memory:** Connection status, default collection for ingestion

### Tab 5: CLI Status

- Detected CLIs with their session directories and file counts
- Health of each scanner (last scan time, files found, any parse errors)
- Quick actions: rescan, open directory

### Cross-cutting Behavior

- Sessions refresh on app launch + manual refresh button + auto-poll every 30s when a CLI is actively running (detected by file modification timestamps)
- Any tab can trigger an export via session context (right-click or action button)
- CLI source badges are consistent across all views

## Tier Plan

### Tier 1: Core (build first — what we need for ourselves)

- Multi-CLI detection (Claude Code, Codex, Gemini CLI)
- Custom CLI registration (GUI form + config file)
- Session browser — timeline view with project grouping as secondary axis
- Session preview (rendered markdown)
- Export formats — Markdown, HTML (themed), JSON, JSONL, ZIP bundle
- Per-session LLM summarization (API key config, template prompt editor, OpenAI/Anthropic/OpenRouter endpoints)
- ember-memory bridge — one-click ingest into a collection
- System tray + desktop launcher
- Singleton instance lock

### Tier 2: Polish & Reach

- Cloud export destinations (Google Drive, Notion, Dropbox) with OAuth flows
- Batch summarization (select multiple sessions, summarize in series)
- Ollama/local model support for summarization
- Tag/collection system for manual session organization
- Full-text search across all session content (not just first-message preview)
- Auto-ingest — watch for new sessions, optionally ingest into ember-memory on completion
- Import from CinderACE Chrome extension (bridge the browser world)

### Tier 3: Advanced

- Anonymization/scrubbing — strip personal data, API keys, file paths before export or summarization
- Session diff — compare two sessions or see project evolution over time
- Shared templates — community prompt templates for summarization categories
- Scheduled summarization — "summarize everything from this week every Sunday"
- Forge-specific fork — tailored build with Forge-centric defaults, detectors, and branding

## ember-memory Bridge

The connective tissue making both tools more valuable together.

**Detection methods (in order):**
1. **Library import** — If `ember_memory` is importable, call it directly. Fastest path.
2. **HTTP API** — If ember-memory is running as a server on port 2214, use REST endpoints.
3. **Graceful disable** — If neither, grey out the button with a tooltip explaining installation.

**Bridge actions:**
- "Ingest this session" — sends parsed session content to a named collection
- "Ingest this summary" — sends the LLM-generated summary instead (cleaner RAG input)
- "Ingest with metadata" — tags the memory with CLI source, project, date range, participants

**Marketing synergy:** Someone discovers ember-memory and needs clean data. CinderACE-Sessions is the on-ramp. Someone finds CinderACE-Sessions first and wants to *do something* with exports. ember-memory is the natural next step. Free tools, mutual reinforcement. Paid tools (CinderACE Chrome extension, CinderVOX) ride the visibility wave.

## Custom CLI Registration

Config-driven with GUI overlay. Follows the ember-memory pattern (GUI for common setups, config file for power users).

**Config file location:** `~/.cinderace-sessions/custom_clis.json`

**Registration schema:**
```json
{
  "custom_clis": [
    {
      "name": "Fire Forge",
      "directory": "~/.forge/sessions",
      "format": "jsonl",
      "color": "#FF7820",
      "enabled": true
    }
  ]
}
```

**GUI form fields:** Name, Directory (file picker), Format (dropdown: JSONL / Markdown / Plain Text), Color (color picker), Enabled toggle.

**Detection behavior:** Built-in detectors run first (Claude Code, Codex, Gemini CLI). Custom CLIs are scanned after. All share the same session list — the CLI source badge distinguishes them.

## CLI Detection Details

### Claude Code
- **Path:** `~/.claude/projects/{workspace-slug}/*.jsonl`
- **Format:** JSONL with `type: "user" | "assistant"` records
- **Metadata:** Session ID, entrypoint (cli/vscode), timestamps, custom titles
- **Filtering:** Skip `<local-command-caveat>` stubs, skip CLI-originated sessions when in VSCode context

### Codex
- **Path:** TBD — depends on Codex CLI's session storage
- **Format:** JSONL (similar structure to Claude Code)

### Gemini CLI
- **Path:** TBD — depends on Gemini CLI's session storage
- **Format:** JSONL (similar structure)

### Custom (Fire Forge example)
- **Path:** Configured by user
- **Format:** Specified at registration time
- **Parsing:** Uses the registered format's parser

## Summarization Pipeline

**Flow:**
1. User selects a session → clicks "Summarize"
2. App shows a confirmation with estimated token count and cost warning
3. Template prompt is populated with session content
4. API call is made to the configured LLM endpoint
5. Summary is displayed in a modal/panel
6. User can: copy, export, or ingest directly into ember-memory

**Default template prompt categories:**
- Key decisions and architectural choices
- Emotional moments, growth, and learning
- Action items and follow-ups
- Technical insights and patterns
- Things that went wrong and how they were handled

**Provider configuration stored locally at:** `~/.cinderace-sessions/settings.json` (API keys never leave the machine)

## Session File Handling

**Read-only principle:** CinderACE-Sessions never modifies source session files. All operations are read-parse-render-export. Source data is sacred.

**Performance:** Large session files (100MB+) are handled by reading headers first (first 16KB for metadata) and streaming content on demand, never loading entire files into memory unnecessarily.

## App Lifecycle

Mirrors ember-memory exactly:

```bash
cinderace-sessions                # Launch detached controller
cinderace-sessions controller      # Launch controller in foreground
cinderace-sessions tray            # Launch system tray
cinderace-sessions setup           # First-run setup
cinderace-sessions install-desktop # Install desktop launcher
```

**Lifecycle:**
- Terminal launch: spawns detached controller, returns to terminal
- Desktop launcher: opens controller window
- Tray launch: creates tray icon, "Open Controller" launches the GUI
- Window close: hides to tray (never destroys)
- Tray quit: terminates controller process, cleans up