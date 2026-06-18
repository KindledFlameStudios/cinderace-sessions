"""Tests for the JSONL parser — Claude Code and Codex formats."""

import json
import os
import tempfile

import pytest

from cinderace_sessions.parser.jsonl_parser import (
    extract_session_meta,
    parse_jsonl_transcript,
    read_preview,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_jsonl(tmp_path):
    """Create a temporary JSONL file from lines."""
    def _make(lines, filename="test.jsonl"):
        filepath = tmp_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        return str(filepath)
    return _make


def _claude_user_line(text, timestamp="2026-01-15T10:00:00Z"):
    """Build a Claude Code user record."""
    return json.dumps({
        "type": "user",
        "message": {"role": "user", "content": text},
        "timestamp": timestamp,
    })


def _claude_assistant_line(text, timestamp="2026-01-15T10:01:00Z"):
    """Build a Claude Code assistant record."""
    return json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
        "timestamp": timestamp,
    })


def _codex_user_line(text, cwd="/home/user", timestamp="2026-01-15T10:00:00Z"):
    """Build a Codex response_item with user content."""
    return json.dumps({
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    })


def _codex_meta_line(session_id="test-123", cwd="/home/user/projects/myapp"):
    """Build a Codex session_meta record."""
    return json.dumps({
        "type": "session_meta",
        "payload": {"id": session_id, "cwd": cwd},
    })


# ── Metadata extraction ──────────────────────────────────────────────

class TestExtractMeta:
    def test_claude_session_id(self, tmp_jsonl):
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}, "timestamp": "2026-01-15T10:00:00Z"}),
        ]
        path = tmp_jsonl(lines)
        meta = extract_session_meta(path)
        # Session ID should be derived from filename
        assert meta.session_id  # Not empty

    def test_codex_session_meta(self, tmp_jsonl):
        lines = [
            _codex_meta_line(session_id="abc-123", cwd="/home/dev/project"),
        ]
        path = tmp_jsonl(lines)
        meta = extract_session_meta(path)
        assert meta.session_id == "abc-123"
        assert meta.slug == "-home-dev-project"

    def test_codex_timestamp_extraction(self, tmp_jsonl):
        lines = [
            json.dumps({"type": "response_item", "timestamp": "2026-03-10T14:30:00Z", "payload": {"role": "user"}}),
        ]
        path = tmp_jsonl(lines)
        meta = extract_session_meta(path)
        assert meta.first_date == "2026-03-10"

    def test_empty_file(self, tmp_jsonl):
        path = tmp_jsonl([])
        meta = extract_session_meta(path)
        # Should not crash, should have fallback values
        assert meta is not None


# ── Preview reading ──────────────────────────────────────────────────

class TestReadPreview:
    def test_claude_user_preview(self, tmp_jsonl):
        lines = [
            _claude_user_line("Hello, how are you?"),
            _claude_assistant_line("I'm doing well!"),
        ]
        path = tmp_jsonl(lines)
        preview = read_preview(path)
        assert "Hello" in preview

    def test_claude_blocks_preview(self, tmp_jsonl):
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": [
                    {"type": "text", "text": "What does this code do?"}
                ]},
                "timestamp": "2026-01-15T10:00:00Z",
            }),
        ]
        path = tmp_jsonl(lines)
        preview = read_preview(path)
        assert "What does this code do?" in preview

    def test_codex_user_preview(self, tmp_jsonl):
        lines = [
            _codex_meta_line(),
            json.dumps({"type": "response_item", "timestamp": "2026-01-15T10:00:00Z",
                        "payload": {"role": "developer", "content": "system instructions"}}),
            _codex_user_line("Fix the bug in app.py"),
        ]
        path = tmp_jsonl(lines)
        preview = read_preview(path)
        assert "Fix the bug" in preview

    def test_codex_skips_environment_context(self, tmp_jsonl):
        lines = [
            _codex_meta_line(),
            _codex_user_line("<environment_context>\n  <cwd>/home/user</cwd>\n  <shell>bash</shell>\n</environment_context>"),
            _codex_user_line("What's the status of the project?"),
        ]
        path = tmp_jsonl(lines)
        preview = read_preview(path)
        assert "/home/user" not in preview
        assert "bash" not in preview
        assert "status" in preview.lower() or "project" in preview.lower()

    def test_codex_skips_agents_md(self, tmp_jsonl):
        lines = [
            _codex_meta_line(),
            _codex_user_line("# AGENTS.md instructions for /home/dev\n\nYou are a helpful assistant..."),
            _codex_user_line("Build me a todo app"),
        ]
        path = tmp_jsonl(lines)
        preview = read_preview(path)
        assert "AGENTS.md" not in preview
        assert "todo" in preview.lower()

    def test_empty_file_no_crash(self, tmp_jsonl):
        path = tmp_jsonl([])
        preview = read_preview(path)
        assert preview == ""


# ── Transcript parsing ──────────────────────────────────────────────

class TestParseTranscript:
    def test_claude_conversation(self, tmp_jsonl):
        lines = [
            _claude_user_line("Hello there"),
            _claude_assistant_line("Hi! How can I help?"),
            _claude_user_line("Tell me about Python"),
        ]
        path = tmp_jsonl(lines)
        turns = parse_jsonl_transcript(path)
        assert len(turns) >= 2
        assert turns[0].role == "user"
        assert "Hello" in turns[0].blocks[0].text

    def test_empty_file_returns_empty(self, tmp_jsonl):
        path = tmp_jsonl([])
        turns = parse_jsonl_transcript(path)
        assert turns == []

    def test_invalid_json_skipped(self, tmp_jsonl):
        lines = [
            "this is not json",
            _claude_user_line("Valid message"),
        ]
        path = tmp_jsonl(lines)
        turns = parse_jsonl_transcript(path)
        assert len(turns) >= 1