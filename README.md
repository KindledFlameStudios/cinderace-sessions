# CinderACE Sessions

**Discover, browse, export, and preserve AI CLI conversations from any tool, in any format.**

AI coding tools are incredible at helping us build.
They're terrible at helping us remember.

Sessions get compressed. Context windows move on. Old projects disappear into hidden folders. Six months later, you remember solving a problem, but not where, when, or how.

CinderACE Sessions was built because important conversations deserve better than being trapped inside a CLI.

It discovers AI sessions across your machine, presents them in a unified desktop interface, and exports them as clean, readable documents you can actually use.

Whether you're revisiting a breakthrough, preserving research, reviewing technical decisions, creating training datasets, or simply trying to remember how you solved a problem three months ago, CinderACE Sessions helps you keep what matters.

Built by developers who needed it themselves.

Because context windows forget.
Your work shouldn't.

## Why Sessions Matter

Most AI CLI tools focus on the current conversation.
CinderACE Sessions focuses on the complete history.

Even after context compression, summarization, or session pruning, the underlying session files often still contain the full journey. CinderACE Sessions discovers those files, organizes them, and makes them accessible again.

The result isn't just a conversation viewer.
It's a searchable archive of your work, decisions, and discoveries.

A place where ideas, experiments, debugging sessions, architectural decisions, and breakthroughs remain available long after the context window has moved on.

## Sources

Sessions don't live in one place. They scatter across every CLI tool you use.

| Source | Default Location |
|--------|------------------|
| **Claude Code** | `~/.claude/projects/` |
| **Codex** | `~/.codex/sessions/` (respects `CODEX_HOME`) |
| **Fire Forge** | `~/.forge/` |
| **Gemini CLI** | `~/.gemini/tmp/` (respects `GEMINI_CLI_HOME`) |

And if you use something we haven't thought of, you can register it. Point CinderACE Sessions at any directory containing JSONL, JSON, Markdown, or text session files — it scans, discovers, and includes those sessions alongside the built-in sources.

## Export Formats

Exports aren't just for reading. They're for using.

Every format produces two variants: **Clean** (conversation + thinking blocks, readable and focused) and **Full** (everything clean has, plus detailed tool usage — file reads, edits, bash commands, searches).

| Format | Clean | Full |
|--------|-------|------|
| **Markdown** | Conversation + thinking blocks | + tool usage details |
| **HTML** | Themed, styled, collapsible thinking | + tool details with syntax highlighting |
| **JSON** | Structured with metadata | + thinking + tool data |
| **JSONL** | One turn per line | + thinking + tool data |
| **ZIP** | All of the above bundled together |

Use JSONL for training datasets and fine-tuning. Use HTML when you need to share with someone who shouldn't need a terminal. Use ZIP when you need everything — archives, backups, documentation sets.

## Features

**Find everything.** Auto-discovers sessions from Claude Code, Codex, Fire Forge, and Gemini CLI. And if you use something we haven't thought of, point it at a directory and it just works.

**Browse in one window.** Desktop GUI with system tray. Filter by source, date range, or search across titles and previews. No terminal required.

**Export like you mean it.** Markdown, HTML, JSON, JSONL, or ZIP. Each in clean and full variants. Use JSONL for training datasets. Use HTML for sharing. Use ZIP when you need everything.

**Three HTML themes.** Ember (warm oranges on dark), Dark (cool blues), Light (clean white). Pick one. Or don't — it remembers.

**Summarize with your own keys.** OpenAI, Anthropic, OpenRouter, or a custom endpoint. Your API keys stay on your machine. The summarizer is a tool, not a service.

**Thinking isn't disposable.** Internal reasoning blocks are captured and presented in collapsible sections, not stripped out.

**Tool usage is part of the story.** See exactly what was read, edited, and run:

```
> **Read** `/src/components/App.tsx`
> **Edit** `/src/utils/helpers.ts`
> **Bash** `npm run build`
> **Grep** `useState` in *.tsx
```

## Installation

```bash
git clone https://github.com/KindledFlameStudios/cinderace-sessions.git
cd cinderace-sessions
pip install .

# Launch the app
cinderace-sessions
```

**Requirements:** Python 3.10+, a supported CLI tool with existing sessions.

## Commands

| Command | Description |
|---------|-------------|
| `cinderace-sessions` | Launch the app and return immediately |
| `cinderace-sessions controller` | Launch the controller in the foreground |
| `cinderace-sessions tray` | Launch the system tray |

## Part of the CinderACE Family

Same philosophy: **preserve everything, extract thinking, make it readable.**

- **CinderACE** (browser) — Claude.ai, ChatGPT, Gemini, Grok, DeepSeek, Perplexity, and 8 more platforms
- **CinderACE Sessions** (desktop) — Claude Code, Codex, Fire Forge, Gemini CLI, and any custom CLI tool

Designed to pair with [Ember Memory](https://kindledflamestudios.com) for building clean, organized conversation collections.

## License

MIT

---

CinderACE Sessions exists because context windows are temporary, but the work you do inside them doesn't have to be.
