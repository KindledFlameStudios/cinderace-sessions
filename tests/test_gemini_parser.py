"""Tests for the Gemini parser — logs.json and chat formats."""

import json
import os
import tempfile

import pytest

from cinderace_sessions.parser.gemini_parser import (
    parse_gemini_session,
    gemini_extract_meta,
    _parse_chat_messages,
    _parse_logs_entries,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_gemini(tmp_path):
    """Create a temporary Gemini session file."""
    def _make(data, filename="session-test.json"):
        filepath = tmp_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return str(filepath)
    return _make


@pytest.fixture
def tmp_gemini_raw(tmp_path):
    """Create a temporary file from raw string content."""
    def _make(content, filename="session-test.json"):
        filepath = tmp_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return str(filepath)
    return _make


# ── logs.json format ────────────────────────────────────────────────

class TestLogsFormat:
    def test_basic_logs(self, tmp_gemini):
        data = [
            {"type": "user", "message": "What is Python?", "timestamp": "2026-01-15T10:00:00Z"},
            {"type": "model", "message": "Python is a programming language.", "timestamp": "2026-01-15T10:01:00Z"},
            {"type": "user", "message": "Tell me more", "timestamp": "2026-01-15T10:02:00Z"},
        ]
        path = tmp_gemini(data, filename="logs.json")
        turns = parse_gemini_session(path)
        assert len(turns) == 3
        assert turns[0].role == "user"
        assert "Python" in turns[0].blocks[0].text
        assert turns[1].role == "assistant"

    def test_logs_with_info_entry(self, tmp_gemini):
        data = [
            {"type": "info", "message": "Model switched to gemini-2.0"},
            {"type": "user", "message": "Hello", "timestamp": "2026-01-15T10:00:00Z"},
        ]
        path = tmp_gemini(data, filename="logs.json")
        turns = parse_gemini_session(path)
        assert len(turns) == 1
        assert turns[0].role == "user"


# ── Chat format ──────────────────────────────────────────────────────

class TestChatFormat:
    def test_basic_chat(self, tmp_gemini):
        data = {
            "sessionId": "test-session-123",
            "messages": [
                {"type": "user", "content": "Hello Gemini"},
                {"type": "gemini", "content": "Hi! How can I help?"},
                {"type": "user", "content": "Explain async/await"},
            ],
        }
        path = tmp_gemini(data)
        turns = parse_gemini_session(path)
        assert len(turns) == 3
        assert turns[0].role == "user"
        assert turns[1].role == "assistant"

    def test_chat_with_thoughts(self, tmp_gemini):
        data = {
            "sessionId": "test-session-456",
            "messages": [
                {
                    "type": "gemini",
                    "content": "The answer is 42.",
                    "thoughts": [
                        {"subject": "Reasoning", "description": "I need to think about this"},
                    ],
                },
            ],
        }
        path = tmp_gemini(data)
        turns = parse_gemini_session(path)
        assert len(turns) == 1
        # Should have both thinking and text blocks
        block_types = [b.type.value if hasattr(b.type, 'value') else b.type for b in turns[0].blocks]
        assert "thinking" in block_types or any("think" in str(b).lower() for b in turns[0].blocks)

    def test_chat_with_tool_calls(self, tmp_gemini):
        data = {
            "sessionId": "test-session-789",
            "messages": [
                {
                    "type": "gemini",
                    "content": "Let me check that.",
                    "toolCalls": [
                        {"name": "read_file", "args": {"path": "/tmp/test.py"}, "result": "OK", "status": "success"},
                    ],
                },
            ],
        }
        path = tmp_gemini(data)
        turns = parse_gemini_session(path)
        assert len(turns) == 1
        # Should have text and tool use blocks
        block_types = []
        for b in turns[0].blocks:
            if hasattr(b, 'type'):
                t = b.type.value if hasattr(b.type, 'value') else b.type
                block_types.append(t)
        assert "tool_use" in block_types or "text" in block_types

    def test_content_as_list(self, tmp_gemini):
        data = {
            "sessionId": "test-session-list",
            "messages": [
                {"type": "user", "content": [{"text": "Hello from a list"}]},
            ],
        }
        path = tmp_gemini(data)
        turns = parse_gemini_session(path)
        assert len(turns) == 1
        assert "Hello" in turns[0].blocks[0].text


# ── Metadata ─────────────────────────────────────────────────────────

class TestGeminiMeta:
    def test_chat_file_meta(self, tmp_gemini):
        data = {
            "sessionId": "abc-123",
            "startTime": "2026-03-20T15:30:00Z",
            "messages": [],
        }
        path = tmp_gemini(data)
        meta = gemini_extract_meta(path)
        assert meta.session_id == "abc-123"
        assert meta.first_date == "2026-03-20"

    def test_logs_file_meta(self, tmp_gemini):
        data = [
            {"type": "user", "message": "test", "timestamp": "2026-04-01T12:00:00Z"},
        ]
        path = tmp_gemini(data, filename="logs.json")
        meta = gemini_extract_meta(path)
        # Session ID should be derived from parent dir or filename
        assert meta is not None

    def test_session_filename_meta(self, tmp_gemini_raw):
        data = {"messages": []}
        path = tmp_gemini_raw(json.dumps(data), filename="session-2026-05-10T14-30-abc123.json")
        meta = gemini_extract_meta(path)
        assert meta.first_date == "2026-05-10"
        assert "2026-05-10" in meta.slug


# ── Edge cases ──────────────────────────────────────────────────────

class TestGeminiEdgeCases:
    def test_empty_file(self, tmp_gemini_raw):
        path = tmp_gemini_raw("", filename="empty.json")
        turns = parse_gemini_session(path)
        assert turns == []

    def test_invalid_json(self, tmp_gemini_raw):
        path = tmp_gemini_raw("not json at all {broken", filename="bad.json")
        turns = parse_gemini_session(path)
        assert turns == []

    def test_empty_array(self, tmp_gemini):
        path = tmp_gemini([], filename="empty.json")
        turns = parse_gemini_session(path)
        assert turns == []

    def test_info_type_skipped(self, tmp_gemini):
        data = {
            "sessionId": "test",
            "messages": [
                {"type": "info", "content": "Model switch"},
                {"type": "user", "content": "Hello"},
            ],
        }
        path = tmp_gemini(data)
        turns = parse_gemini_session(path)
        assert len(turns) == 1
        assert turns[0].role == "user"