# CinderACE Sessions v2 — FORGE Context

## What It Is

Standalone desktop application (built with Python + PyWebView) for discovering, browsing, exporting, and summarizing AI CLI conversation sessions (Claude Code, Codex, Gemini CLI). It acts as a companion to CinderACE and a sibling tool to ember-memory.

Same philosophy as CinderACE: preserve everything, extract thinking, make it readable.

## Tech Stack

- **Language:** Python 3.10+
- **Frontend:** Vanilla HTML + CSS + JS via PyWebView
- **Build/Packaging:** `pyproject.toml`
- **Dependencies:** `pywebview`, `requests`, `pystray`, `PyQt6` (Linux)

## Key Files

```
CinderACE-Sessions/
  cinderace_sessions/
    __main__.py              # CLI dispatcher
    controller_app.py        # SessionsAPI backend + pywebview window
    config.py                # Config management
    detector/                # Scanners for CLI session files
    parser/                  # Parsers for JSONL/JSON/MD logs
    renderer/                # Export builders (HTML, MD, JSON, etc)
    summarizer/              # LLM clients for summarization
    controller_assets/       # Vanilla UI (HTML/CSS/JS)
  pyproject.toml             # Python build/deps
```

## How to Build and Run

```bash
cd "/home/seren/CinderACE - Sessions"

# Install as editable package
pip install -e .

# Run the controller GUI
cinderace-sessions
```

## Export Formats

Each export has a clean variant (conversation + thinking) and a full variant (+ tool usage details).

| Format | Notes |
|--------|-------|
| Markdown | Clean readable text |
| HTML | Themed (Ember/Dark/Light), collapsible thinking blocks |
| JSON | Structured with metadata |
| JSONL | One turn per line |
| ZIP | All formats bundled |

## Notes

- This is v2. All v1 VS Code extension code (TypeScript) has been stripped out.
- ember-memory bridge natively supports injecting sessions and summaries directly.
- All session parsing works iteratively over the file contents to handle multi-megabyte JSONL files safely.
