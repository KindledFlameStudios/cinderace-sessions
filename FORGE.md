# CinderACE Sessions v2 — FORGE Context

## What It Is

Standalone desktop application for discovering, browsing, exporting, and summarizing AI CLI conversation sessions (Claude Code, Codex, Gemini CLI). Companion to CinderACE and sibling tool to ember-memory.

Same philosophy: preserve everything, extract thinking, make it readable.

## Tech Stack

- **Language:** Python 3.10+
- **Frontend:** Vanilla HTML + CSS + JS via PyWebView
- **Build/Packaging:** `pyproject.toml`
- **Dependencies:** `pywebview`, `requests`, `pystray`, `PyQt6` (Linux)

## How to Run

```bash
cd "/home/seren/CinderACE - Sessions"

# Install as editable package
pip install -e .

# Run the controller GUI
cinderace-sessions              # Detached mode
cinderace-sessions controller   # Foreground (for development)
```

## Architecture

```
cinderace_sessions/
  __main__.py              # CLI dispatcher + logging setup
  controller_app.py        # SessionsAPI backend + pywebview window
  config.py                # Config management (JSON in ~/.cinderace-sessions/)
  single_instance.py       # Prevents multiple app instances
  detector/                # Scanners for CLI session files
    base.py                # CLIDetector base class, SessionInfo dataclass
    registry.py            # DetectorRegistry — unified scan_all()
    claude_code.py         # ~/.claude/projects/ scanner
    codex.py               # ~/.codex/sessions/ scanner
    gemini_cli.py          # ~/.gemini/tmp/ scanner
  parser/                  # Parsers for CLI session formats
    base.py                # ExportFormat, SessionMeta, Turn, ContentBlock, etc.
    jsonl_parser.py         # Claude Code + Codex JSONL parser
    gemini_parser.py        # Gemini CLI JSON/JSONL parser
    markdown_parser.py     # Markdown session parser
    text_parser.py         # Plain text parser
  renderer/                # Export builders
    html.py                # HTML export (3 themes: Ember, Dark, Light)
    markdown.py            # Markdown export
    json_export.py         # JSON export
    jsonl_export.py        # JSONL export
    zip_export.py          # ZIP bundler (all formats)
  summarizer/               # LLM summarization pipeline
    engine.py              # OpenAI, Anthropic, OpenRouter providers
    ollama.py              # Local Ollama provider
    model_catalog.py       # Live model discovery + static fallbacks
    template.py            # Summary template management
  controller_assets/       # Frontend (HTML/CSS/JS)
    ui.html                # Single-page app shell
    ui.css                 # Ember-themed dark UI
    ui.js                  # All frontend logic
```

## Features

### Session Browser
- **Project-grouped view** — sessions grouped by project directory by default, toggle to flat list
- **CLI detection** — auto-discovers Claude Code, Codex, and Gemini CLI sessions
- **Custom CLIs** — add/remove custom CLI directories from Settings
- **Filter/search** — by date range, CLI source, or text search
- **Preview pane** — shows first 20 turns of conversation

### Export
- Markdown, HTML (3 themes), JSON, JSONL, ZIP (all formats)
- Clean variant (conversation + thinking) and full variant (+ tool usage)

### Summarizer
- OpenAI, Anthropic, OpenRouter providers with live model discovery
- Ollama local provider
- Custom URL endpoint (OpenAI-compatible)
- Template system for summary prompts
- Summary history with copy/export/ingest

### ember-memory Bridge
- Ingest session content or summaries directly into ember-memory
- Library mode detection (no HTTP needed)

### UI
- **Right-click context menu** — Copy/Cut/Paste/Select All
- **Model fetching** — dropdown populates from provider APIs with static fallbacks
- **Logging** — centralized to `~/.cinderace-sessions/cinderace-sessions.log`

## Export Formats

| Format | Notes |
|--------|-------|
| Markdown | Clean readable text |
| HTML | Themed (Ember/Dark/Light), collapsible thinking blocks |
| JSON | Structured with metadata |
| JSONL | One turn per line |
| ZIP | All formats bundled |

## Testing

```bash
cd "/home/seren/CinderACE - Sessions"
python -m pytest tests/ -v
```

46 tests covering JSONL parser, Gemini parser, and model catalog.

## Notes

- This is v2. All v1 VS Code extension code has been removed.
- Session parsing handles multi-megabyte files safely (8MB streaming guard for Gemini, 128KB read window for Codex/Claude).
- Codex session previews skip system context blocks to show actual user input.
- The app runs with `debug=True` in pywebview to enable context menu events, with `OPEN_DEVTOOLS_IN_DEBUG=False` to suppress the F12 popup.