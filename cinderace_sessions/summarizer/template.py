"""CinderACE Sessions v2 — summary template management.

Templates are stored at ~/.cinderace-sessions/templates/
with a built-in default created on first use.
"""

from __future__ import annotations

import os
from pathlib import Path

TEMPLATES_DIR = Path.home() / ".cinderace-sessions" / "templates"

DEFAULT_TEMPLATE = """You are summarizing an AI CLI conversation session. Extract the following from the transcript:

## Key Decisions & Architectural Choices
What decisions were made? What alternatives were considered? What was chosen and why?

## Emotional Moments & Growth
What moments of excitement, frustration, breakthrough, or learning occurred?

## Action Items & Follow-ups
What tasks were started, completed, or left pending? What needs to happen next?

## Technical Insights & Patterns
What technical knowledge, patterns, or approaches were discovered or applied?

## What Went Wrong & How It Was Handled
What problems, errors, or misunderstandings arose? How were they resolved?

---

Session transcript:
{content}
"""


def _ensure_templates_dir():
    """Create templates directory if it doesn't exist."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def load_template(name: str = "default") -> str:
    """Load a template by name. Returns the default template if not found."""
    _ensure_templates_dir()

    if name == "default":
        # Always recreate the default template if missing
        default_path = TEMPLATES_DIR / "default.md"
        if not default_path.exists():
            save_template("default", DEFAULT_TEMPLATE)
            return DEFAULT_TEMPLATE
        try:
            return default_path.read_text(encoding="utf-8")
        except OSError:
            return DEFAULT_TEMPLATE

    # Custom template
    template_path = TEMPLATES_DIR / f"{name}.md"
    try:
        return template_path.read_text(encoding="utf-8")
    except OSError:
        return load_template("default")


def save_template(name: str, content: str) -> bool:
    """Save a template by name. Returns True on success."""
    _ensure_templates_dir()

    try:
        template_path = TEMPLATES_DIR / f"{name}.md"
        template_path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


def list_templates() -> list[str]:
    """List all available template names."""
    _ensure_templates_dir()

    try:
        return [p.stem for p in TEMPLATES_DIR.glob("*.md")]
    except OSError:
        return ["default"]


def delete_template(name: str) -> bool:
    """Delete a custom template. Cannot delete the default."""
    if name == "default":
        return False

    try:
        template_path = TEMPLATES_DIR / f"{name}.md"
        template_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False