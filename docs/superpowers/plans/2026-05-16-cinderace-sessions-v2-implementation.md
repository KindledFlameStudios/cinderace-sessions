# CinderACE-Sessions v2 — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-05-16-cinderace-sessions-v2-design.md`

---

## Build Order Philosophy

Each phase produces something testable. Each task within a phase builds on the previous one. We commit after every meaningful unit of work.

---

## Phase 1: Skeleton + Configuration

The app doesn't do anything yet, but it can launch, show a window, and read its own config.

### Task 1.1: Package structure + pyproject.toml

- Create the full directory structure from the spec (`cinderace_sessions/`, `controller/`, `tests/`, `docs/`)
- Write `pyproject.toml` with entry points, dependencies (pywebview, PyQt6, pystray, requests)
- Write `requirements.txt`
- Write `cinderace_sessions/__init__.py` with `__version__ = "2.0.0"`
- Empty `__init__.py` files in all subpackages
- Verify: `pip install -e .` works, `cinderace-sessions --help` doesn't crash

### Task 1.2: Configuration system

- Create `cinderace_sessions/config.py`
- Config resolution: `env var > ~/.cinderace-sessions/settings.json > defaults`
- Settings: output_directory, default_export_format, html_theme, include_thinking, include_tools, user_label, assistant_label, user_emoji, assistant_emoji, auto_detect_on_launch
- Write `load_config()` and `save_settings()` functions
- Settings file at `~/.cinderace-sessions/settings.json`
- Verify: can load, modify, and persist settings

### Task 1.3: Singleton lock

- Port `single_instance.py` from ember-memory pattern
- Lock file at `~/.cinderace-sessions/controller.lock` (controller) and `tray.lock` (tray)
- `acquire_instance_lock(name)` / `release_instance_lock(name)`
- Verify: second launch detects first and exits

### Task 1.4: CLI dispatcher

- Create `cinderace_sessions/__main__.py`
- Commands: `controller`, `tray`, `setup`, `install-desktop`
- Default (no args): launch controller detached
- `launch_app_detached()` spawns detached subprocess
- Verify: `cinderace-sessions` launches without error

---

## Phase 2: Core Parser + Detector

The app can find and read session files. No UI yet — just the backend data layer.

### Task 2.1: Data types

- Create `cinderace_sessions/parser/base.py`
- Define dataclasses: `ContentBlock`, `Turn`, `SessionStats`, `SessionMeta`, `RenderOptions`, `SessionSummary`
- Port from the TypeScript types, using Python dataclasses
- `ContentBlock` types: text, thinking, tool_use, tool_result, image
- `SessionEntrypoint`: cli, vscode, unknown
- `ExportFormat`: md, html, json, jsonl, zip
- `HtmlTheme`: ember, dark, light

### Task 2.2: JSONL parser (Claude Code format)

- Create `cinderace_sessions/parser/jsonl_parser.py`
- Functions: `parse_jsonl_transcript(filepath) -> list[Turn]`, `extract_session_meta(filepath) -> SessionMeta`, `build_stats(turns) -> SessionStats`
- Port logic from the TypeScript `parser.ts`:
  - Line-by-line JSON parsing, skip empty/malformed
  - Filter records with `type == 'user' | 'assistant'`
  - Normalize content: string → `[{type: 'text', text: str}]`, or array of blocks
  - Extract only text, thinking, tool_use blocks (drop tool_result, image)
  - Meta extraction: stop early once all fields found
  - SessionId fallback to filename minus `.jsonl`
  - Entrypoint detection from first record
- Verify: parse the actual Claude Code sessions in `~/.claude/projects/` and get valid Turn lists

### Task 2.3: JSONL parser additions (Codex format)

- Extend `jsonl_parser.py` or create `codex_parser.py` if format differs meaningfully
- Codex sessions at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
- Research the actual Codex JSONL schema (the agent found: user messages, AI responses, tool calls, file changes, token usage)
- Parse the Codex-specific fields but normalize to the same Turn/ContentBlock model
- Verify: if Codex CLI is installed, parse its sessions

### Task 2.4: JSON parser (Gemini CLI format)

- Create `cinderace_sessions/parser/gemini_parser.py`
- Gemini sessions at `~/.gemini/tmp/<project_hash>/logs.json` (JSON, not JSONL)
- Checkpoint files at `~/.gemini/tmp/<project_hash>/checkpoints/checkpoint-*.json`
- Parse: array of `{role: 'user'|'model', parts: [...]}` records
- Normalize to Turn/ContentBlock model
- Verify: if Gemini CLI is installed, parse its sessions

### Task 2.5: Base CLI detector + Claude Code detector

- Create `cinderace_sessions/detector/base.py`
  - Abstract base class `CLIDetector` with methods: `detect() -> bool`, `find_sessions() -> list[str]`, `name -> str`, `is_available -> bool`
- Create `cinderace_sessions/detector/claude_code.py`
  - Detects `~/.claude/projects/` existence
  - Walks all project subdirectories, finds `.jsonl` files
  - Filters: skip `<local-command-caveat>` stubs, skip CLI-only sessions when appropriate
  - Reads custom titles from `{"type":"custom-title"}` records
  - Returns list of session file paths with metadata
- Verify: scans real Claude Code sessions, returns file list with dates/sizes/previews

### Task 2.6: Codex detector

- Create `cinderace_sessions/detector/codex.py`
  - Detects `~/.codex/` existence
  - Walks `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
  - Returns list of session file paths with metadata

### Task 2.7: Gemini CLI detector

- Create `cinderace_sessions/detector/gemini_cli.py`
  - Detects `~/.gemini/` existence
  - Walks `~/.gemini/tmp/*/logs.json` and `~/.gemini/tmp/*/chats/`
  - Returns list of session file paths with metadata

### Task 2.8: Detector registry + custom CLI support

- Create `cinderace_sessions/detector/registry.py`
  - `DetectorRegistry` class: holds built-in + custom detectors
  - `scan_all() -> list[SessionInfo]`: runs all enabled detectors, returns unified session list
  - `add_custom_cli(name, directory, format, color)`: registers a user-defined CLI
  - `remove_custom_cli(name)`: unregisters
  - Custom CLIs stored in `~/.cinderace-sessions/custom_clis.json`
  - Custom CLIs use the parser specified by format (jsonl → JsonlParser, json → GeminiParser, markdown → MarkdownParser, text → TextParser)
- Verify: add a custom CLI pointing at a test directory, scan finds sessions from it

### Task 2.9: Markdown + plain text parsers (for custom CLIs)

- Create `cinderace_sessions/parser/markdown_parser.py`
  - Best-effort parsing of markdown conversation logs
  - Detect common patterns: `**User**:`, `**Assistant**:`, `> `, code blocks
  - Normalize to Turn/ContentBlock model
- Create `cinderace_sessions/parser/text_parser.py`
  - Very loose parsing: split on common delimiters, assign alternating roles
  - Each chunk becomes a single text block
- Verify: parse a sample markdown conversation file

---

## Phase 3: Export Renderers

The app can turn parsed sessions into exportable formats.

### Task 3.1: Markdown renderer

- Create `cinderace_sessions/renderer/markdown.py`
- Port from TypeScript `renderer.ts`:
  - `build_document(turns, stats, meta, options) -> str`
  - Header: `# Session Digest: {slug}`, source, date, stats
  - Per-turn: role label with emoji + timestamp, thinking blocks (truncated at 1000 chars), tool details, text
  - Thinking in `<details><summary>` blocks
  - Tool detail formatting per tool name (Read, Edit, Write, Bash, Grep, Glob, Task, WebFetch, WebSearch, TodoWrite)
  - `clean_options()`: returns options with thinking=True, tools=False
- Verify: export a real session to .md, open and read it

### Task 3.2: HTML renderer

- Create `cinderace_sessions/renderer/html.py`
- Port from TypeScript `htmlRenderer.ts`:
  - `build_html(turns, stats, meta, options, theme) -> str`
  - Three themes: ember, dark, light (36 CSS variables each)
  - Inline CSS generated from theme variables
  - Thinking blocks: collapsible via CSS class toggle (onclick)
  - HTML escaping on all user text
  - Role labels, timestamps, tool details
  - Footer: "Exported by CinderACE Sessions"
- Verify: export to HTML in each theme, open in browser, verify rendering and collapsibles

### Task 3.3: JSON + JSONL renderers

- Create `cinderace_sessions/renderer/json_export.py`
  - Structured JSON with meta, stats, settings, turns
  - Each turn includes text, optional thinking, optional tools
- Create `cinderace_sessions/renderer/jsonl_export.py`
  - First line: metadata record
  - Subsequent lines: one turn per line
- Port from TypeScript `formats.ts` logic
- Verify: export to JSON and JSONL, parse them back, verify round-trip

### Task 3.4: ZIP bundler

- Create `cinderace_sessions/renderer/zip_export.py`
  - `build_zip(turns, stats, meta, options, base_name, theme) -> bytes`
  - Contains clean + full variants of: .md, .html, .json, .jsonl
  - Uses Python's `zipfile` module (no external dependency needed)
- Verify: export to ZIP, extract, verify all 8 files present and valid

---

## Phase 4: Controller App + GUI

The app has a real interface.

### Task 4.1: Controller shell

- Create `cinderace_sessions/controller_app.py`
- `SessionsAPI` class with pywebview bridge methods (model after ember-memory's `EmberAPI`)
- `run_gui()` function: creates pywebview window (840×660, min 700×550, dark #050505 background)
- Load HTML from `controller_assets/ui.html`, inline CSS and JS
- Window close hides to tray (doesn't destroy)
- Verify: app launches, shows window, closes to tray

### Task 4.2: SessionsAPI core methods

Expose these to the JS frontend via pywebview bridge:
- `get_config()` / `save_settings()`
- `detect_clis()` — runs DetectorRegistry.scan_all(), returns list of detected CLIs with status
- `get_sessions(cli_filter, date_range, search_text, page, per_page)` — returns paginated session list
- `get_session_detail(filepath)` — returns full parsed session (Turns, stats, meta)
- `get_projects()` — returns project-grouped session list
- `export_session(filepath, format, options)` — renders and saves to output directory
- `refresh_sessions()` — force rescan

### Task 4.3: UI — HTML skeleton

- Create `controller_assets/ui.html`
- Tab structure: Sessions, Projects, Summarizer, Settings, CLI Status
- SVG logo (port ember-memory style, CinderACE branding)
- Main layout: top nav + content area per tab
- Verify: tabs switch, layout renders correctly

### Task 4.4: UI — CSS (ember theme)

- Create `controller_assets/ui.css`
- CSS variables matching ember-memory palette: `--ember: #FF7820`, `--bg-void: #050505`, `--fg: #e0dcd0`, etc.
- Dark theme base, ember-orange accents
- Responsive layout, stat cards, panels, scroll areas
- Toast notification animations
- CLI source badge colors (orange/blue/red/configurable)
- Session list items, project cards, filter bars
- Verify: visual consistency with ember-memory

### Task 4.5: UI — Sessions tab (JS)

- Create `controller_assets/ui.js` — Sessions tab section
- Top bar: date range filter buttons, CLI source dropdown, text search
- Left panel: session list with polling (every 30s when active CLI detected via mtime)
  - Each item: preview, date, CLI badge, project/title, message count, size
  - Click → loads detail in right panel
- Right panel: rendered markdown preview of selected session
  - Collapsible thinking blocks
  - Action buttons: Export (format dropdown), Summarize, Ingest, Open in file manager
- `callApi()` helper wrapping `window.pywebview.api.*`
- Verify: browse real sessions, filter by CLI/date, preview renders correctly

### Task 4.6: UI — Projects tab

- Left panel: project list sorted by last active
- Click project → right panel shows sessions within it
- Session list reuses same item format as Sessions tab
- Verify: group sessions by project, navigate between projects

### Task 4.7: UI — Settings tab

- General section: output directory (file picker), default format dropdown, auto-detect toggle
- Display section: HTML theme dropdown, include thinking toggle, include tools toggle, custom labels
- Custom CLIs section: list with add/edit/remove, form with name/directory/format/color/enabled
- ember-memory section: connection status, default collection picker
- All settings wired to `save_settings()` API
- Verify: change settings, reload app, settings persist

### Task 4.8: UI — CLI Status tab

- List detected CLIs: name, session directory, file count, last scan time, health
- Quick actions: Rescan button, Open Directory button
- Custom CLIs shown alongside built-in with "Custom" badge
- Verify: shows real CLI detection results, rescan works

---

## Phase 5: Summarizer

The app can send sessions to an LLM and get structured summaries.

### Task 5.1: LLM engine client

- Create `cinderace_sessions/summarizer/engine.py`
- `LLMClient` class:
  - Supports OpenAI, Anthropic, OpenRouter, and custom URL endpoints
  - `summarize(content, prompt_template, model, max_tokens) -> str`
  - Handles API key management (stored in settings.json, never logged or sent elsewhere)
  - Error handling: rate limits, invalid keys, network failures — return clear error messages
- Port provider patterns from ember-memory's embedding providers where applicable
- Verify: call OpenAI API with a short test session, get a response

### Task 5.2: Template prompt system

- Create `cinderace_sessions/summarizer/template.py`
- Default template with extraction categories:
  - Key decisions and architectural choices
  - Emotional moments, growth, learning
  - Action items and follow-ups
  - Technical insights and patterns
  - What went wrong and how it was handled
- `load_template(name) -> str` / `save_template(name, content)`
- `list_templates() -> list[str]`
- Templates stored at `~/.cinderace-sessions/templates/`
- Built-in default template on first install
- Verify: load default template, create custom template, list templates

### Task 5.3: Ollama/local model support

- Create `cinderace_sessions/summarizer/ollama.py`
- Calls Ollama's HTTP API at `http://localhost:11434/api/generate`
- Same `summarize()` interface as LLMClient
- Auto-detect if Ollama is running (health check on `localhost:11434`)
- Verify: if Ollama is available, summarize a short session

### Task 5.4: UI — Summarizer tab

- Provider config section:
  - Dropdown: OpenAI / Anthropic / OpenRouter / Ollama / Custom URL
  - API key input (masked)
  - Model name input
  - "Test Connection" button
- Template editor section:
  - Dropdown to select template
  - Text area to edit template content
  - "Save Template" button
  - "Reset to Default" button
- Summary history section:
  - List of past summaries: session name, date, provider
  - Click to re-view summary content
  - "Copy" and "Export" buttons
- Verify: configure provider, test connection, edit template, view history

### Task 5.5: Summarization flow integration

- From Sessions tab: "Summarize" button on selected session
  - Shows confirmation: estimated token count, cost warning, selected provider
  - Populates template with session content
  - Calls configured LLM
  - Shows result in modal/panel
  - Actions: Copy, Export as .md, Ingest to ember-memory
- From Summarizer tab: can also trigger on a selected session
- Summary saved to history
- Verify: full flow on a real session

---

## Phase 6: ember-memory Bridge

The app can ingest sessions and summaries into persistent memory.

### Task 6.1: Bridge module

- Create `cinderace_sessions/ember_bridge.py`
- `EmberBridge` class:
  - `is_available() -> str` — returns 'library', 'server', or 'none'
  - Library path: try `from ember_memory.core.backends import get_backend_v2`
  - Server path: try HTTP GET to `http://localhost:2214/health` (or the MCP server)
  - `ingest_session(filepath, collection, tags) -> bool` — parses session, stores as memory entries
  - `ingest_summary(summary_text, collection, tags) -> bool` — stores LLM summary
  - `list_collections() -> list[dict]`
- Library import: use `get_backend_v2()` + `get_embedding_provider()` + `backend.insert()`
- Server fallback: use `requests` to POST to ember-memory's MCP/tools endpoint
- Graceful disable: if neither available, return clear status
- Verify: ingest a session when ember-memory is installed

### Task 6.2: UI integration — Ingest buttons

- Sessions tab: "Ingest" button on session preview
  - Dropdown: "Ingest Session" / "Ingest Summary" (if summary exists)
  - Collection picker (fetches from ember_bridge.list_collections())
  - Tags auto-populated: CLI source, project, date
  - Progress indicator during ingestion
  - Success/failure toast notification
- Summarizer tab: "Ingest to ember-memory" button on completed summary
- Settings tab: ember-memory section shows connection status (Library / Server / Not Found)
- Verify: ingest a session and a summary, check they appear in ember-memory

---

## Phase 7: System Tray + Desktop Integration

The app lives in the background like a proper desktop citizen.

### Task 7.1: System tray (Qt6 primary)

- Create `controller/tray.py`
- PyQt6 `QSystemTrayIcon` with context menu:
  - Show/Hide Controller
  - Rescan Sessions
  - Quick Export Latest (to default format)
  - Quit
- Tray icon: use CinderACE icon (from resources/)
- Tray launches controller as detached subprocess if not running
- Verify: tray appears in system tray, menu works, controller opens from tray

### Task 7.2: System tray (pystray fallback)

- Add pystray fallback for systems without Qt6
- Same menu structure, simpler UI (no custom widgets)
- Auto-select: try Qt6, fall back to pystray
- Verify: tray works with pystray on minimal systems

### Task 7.3: Desktop integration

- Create `cinderace_sessions/desktop_integration.py`
- Port from ember-memory's pattern:
  - Linux: `.desktop` file in `~/.local/share/applications/`, icon in hicolor theme, `update-desktop-database`
  - Windows: `.lnk` shortcut in Start Menu via PowerShell COM
- `install-desktop` / `uninstall-desktop` commands
- Verify: desktop launcher appears, launches app

---

## Phase 8: Polish + Testing

### Task 8.1: Test suite

- `tests/test_parser.py`: JSONL parsing, content normalization, edge cases (empty files, malformed lines, mixed content types)
- `tests/test_detector.py`: detector registry, custom CLI add/remove, session scanning with mock directories
- `tests/test_renderer.py`: markdown output, HTML output with all themes, JSON/JSONL round-trip, ZIP contents
- `tests/test_summarizer.py`: template loading/saving, LLM client with mocked API
- `tests/test_ember_bridge.py`: bridge detection, ingest with mocked ember-memory
- `tests/conftest.py`: shared fixtures (sample session files, mock CLIs)

### Task 8.2: Error handling pass

- Every API method returns structured error responses (not exceptions to the JS layer)
- File not found, permission denied, parse failures — all handled gracefully
- Network timeouts in summarizer/bridge — show clear "unreachable" messages
- Large files: streaming where possible, memory limits enforced

### Task 8.3: README + docs

- `README.md`: what it is, installation, usage, screenshots
- `docs/ARCHITECTURE.md`: system overview, data flow, component descriptions
- `docs/CONFIGURATION.md`: all settings, custom CLIs, summarize setup, ember-memory bridge
- Update `FORGE.md` to reflect the new project structure

### Task 8.4: Final verification

- Fresh install on clean environment: `pip install -e .`
- Launch, detect all three CLIs, browse sessions, export in all formats
- Summarize a session with API key
- Ingest to ember-memory
- Tray lifecycle: launch, hide, show, quit
- Desktop launcher install/uninstall

---

## Dependency Graph (What Blocks What)

```
Phase 1 (Skeleton)
    ↓
Phase 2 (Parser + Detector) ← no UI dependency, can test from Python
    ↓
Phase 3 (Renderers) ← needs Phase 2's data types
    ↓
Phase 4 (Controller + GUI) ← needs Phase 2 + 3 in backend
    ↓
Phase 5 (Summarizer) ← needs Phase 2 data, Phase 4 UI
    ↓
Phase 6 (ember Bridge) ← needs Phase 2 data, Phase 5 summaries
    ↓
Phase 7 (Tray + Desktop) ← needs Phase 4 controller
    ↓
Phase 8 (Polish) ← everything
```

Phases 2 and 3 can be partially parallelized — parsers and renderers don't depend on each other. Everything else is sequential.

---

## Key References

- **Existing parser logic:** `~/CinderACE - Sessions/src/parser.ts` (TypeScript, port to Python)
- **Existing renderer logic:** `~/CinderACE - Sessions/src/renderer.ts`, `htmlRenderer.ts` (TypeScript, port to Python)
- **ember-memory controller pattern:** `~/ember-memory/ember_memory/controller_app.py`
- **ember-memory tray pattern:** `~/ember-memory/controller/tray.py`
- **ember-memory integration API:** `~/ember-memory/ember_memory/ingest.py`, `server.py`, `core/backends/`, `core/embeddings/`
- **Codex sessions location:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
- **Gemini CLI sessions location:** `~/.gemini/tmp/<project_hash>/logs.json`