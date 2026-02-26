# CinderACE Sessions

**Export Claude Code sessions as clean, readable documents — markdown, HTML, JSON, JSONL, or ZIP.**

CinderACE Sessions brings the [CinderACE](https://kindledflamestudios.com/cinderace) conversation preservation philosophy to Claude Code. Your conversations deserve to be preserved with fidelity — not lost to context window limits.

## The Problem

Claude Code stores sessions as raw JSONL files. When your context window fills up and compresses, older messages disappear from the UI — but the data is still there on disk, buried in unreadable JSON. CinderACE Sessions extracts it all and gives you clean, human-readable exports.

## Features

**5 Export Formats** — each produces both clean and full variants:

| Format | Clean | Full |
|--------|-------|------|
| **Markdown** | Conversation + thinking blocks | + tool usage details |
| **HTML** | Themed, styled, collapsible thinking | + tool details with syntax highlighting |
| **JSON** | Structured with metadata | + thinking + tool data |
| **JSONL** | One turn per line | + thinking + tool data |
| **ZIP** | All of the above bundled together |

**3 HTML Themes:**
- **Ember** — the signature CinderACE look (warm oranges and golds on dark)
- **Dark** — cool blues and grays
- **Light** — clean white with blue accents

**Custom Naming** — name each export with a prompt, or press Enter for the auto-detected session slug.

**Thinking Block Extraction** — Claude's internal reasoning captured and presented in collapsible sections.

**Tool Usage Details** — see exactly what files were read, edited, what commands were run:
```
> **Read** `/src/components/App.tsx`
> **Edit** `/src/utils/helpers.ts`
> **Bash** `npm run build`
> **Grep** `useState` in *.tsx
```

## Usage

1. Click the **flame icon** in the status bar (or run `CinderACE Sessions: Export Current Session` from the command palette)
2. **Name your export** — type a custom name or press Enter for the default
3. **Pick your formats** — select one or more (multi-select)
4. **Choose your output directory** (remembered after first use)
5. Done — your exports are saved

### Commands

| Command | Description |
|---------|-------------|
| `CinderACE Sessions: Export Current Session` | Export the active session (also: click the flame) |
| `CinderACE Sessions: Export Recent Sessions` | Batch export the last N sessions |
| `CinderACE Sessions: Select Output Directory` | Change where exports are saved |
| `CinderACE Sessions: Open Output Directory` | Open your export folder |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `cinderaceSessions.htmlTheme` | `ember` | HTML theme: `ember`, `dark`, or `light` |
| `cinderaceSessions.includeThinking` | `true` | Include thinking/reasoning blocks |
| `cinderaceSessions.includeTools` | `true` | Include tool usage details |
| `cinderaceSessions.userLabel` | `User` | Display label for user messages |
| `cinderaceSessions.assistantLabel` | `Assistant` | Display label for assistant messages |
| `cinderaceSessions.userEmoji` | *(empty)* | Emoji prefix for user messages |
| `cinderaceSessions.assistantEmoji` | *(empty)* | Emoji prefix for assistant messages |
| `cinderaceSessions.outputDirectory` | *(prompted)* | Where to save exports |
| `cinderaceSessions.transcriptsDirectory` | *(auto-detect)* | Override Claude Code transcripts location |

## How It Works

Claude Code stores every conversation as a JSONL file at `~/.claude/projects/{workspace-slug}/`. Each line is a JSON object containing the message role, content blocks (text, thinking, tool usage), timestamps, and metadata.

CinderACE Sessions reads these files, parses the structured content, and renders them into your chosen formats. The JSONL files are **append-only** — nothing is ever deleted, even after context compression. This means you can export a complete conversation at any time, regardless of what the UI shows.

**Clean vs Full exports:**
- **Clean** — conversation text + thinking blocks. Readable, focused, no noise.
- **Full** — everything clean has, plus detailed tool usage (file reads, edits, bash commands, searches). Great for reviewing past technical work.

## Part of the CinderACE Family

CinderACE Sessions is the editor companion to [CinderACE](https://kindledflamestudios.com/cinderace), the universal AI chat exporter for Chrome and Edge. Together they cover every AI conversation environment:

- **CinderACE** (browser) — Claude.ai, ChatGPT, Gemini, Grok, DeepSeek, Perplexity, and 8 more platforms
- **CinderACE Sessions** (editor) — Claude Code sessions in VS Code / VSCodium

Same philosophy: **preserve everything, extract thinking, make it readable.**

## Requirements

- VS Code 1.85+ or VSCodium
- Claude Code CLI (conversations must exist at `~/.claude/projects/`)

## License

MIT
