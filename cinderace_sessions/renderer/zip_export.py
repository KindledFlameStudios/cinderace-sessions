"""CinderACE Sessions v2 — ZIP bundle exporter.

Bundles clean + full variants of all export formats into a single ZIP file.
Uses Python's built-in zipfile module — no external dependencies.
"""

from __future__ import annotations

import zipfile
import io

from cinderace_sessions.parser.base import (
    HtmlTheme,
    RenderOptions,
    SessionMeta,
    SessionStats,
    Turn,
    clean_options,
)
from cinderace_sessions.renderer.markdown import build_document
from cinderace_sessions.renderer.html import build_html
from cinderace_sessions.renderer.json_export import build_json
from cinderace_sessions.renderer.jsonl_export import build_jsonl


def build_zip(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions,
    base_name: str,
    theme: str = "ember",
) -> bytes:
    """Build a ZIP file containing all export formats (clean + full variants).

    Returns the ZIP file content as bytes.
    """
    theme_enum = HtmlTheme(theme) if theme in [t.value for t in HtmlTheme] else HtmlTheme.EMBER
    theme_name = theme_enum.value
    clean = clean_options(options)

    # Generate all exports
    md_clean = build_document(turns, stats, meta, clean)
    md_full = build_document(turns, stats, meta, options)

    html_clean = build_html(turns, stats, meta, clean, theme_name)
    html_full = build_html(turns, stats, meta, options, theme_name)

    json_clean = build_json(turns, stats, meta, clean)
    json_full = build_json(turns, stats, meta, options)

    jsonl_clean = build_jsonl(turns, meta, clean)
    jsonl_full = build_jsonl(turns, meta, options)

    # Build ZIP in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}_clean.md", md_clean)
        zf.writestr(f"{base_name}_full.md", md_full)
        zf.writestr(f"{base_name}_clean.html", html_clean)
        zf.writestr(f"{base_name}_full.html", html_full)
        zf.writestr(f"{base_name}_clean.json", json_clean)
        zf.writestr(f"{base_name}_full.json", json_full)
        zf.writestr(f"{base_name}_clean.jsonl", jsonl_clean)
        zf.writestr(f"{base_name}_full.jsonl", jsonl_full)

    return buffer.getvalue()


def render_zip(
    turns: list[Turn],
    stats: SessionStats,
    meta: SessionMeta,
    options: RenderOptions | None = None,
    base_name: str = "session",
    theme: str = "ember",
) -> bytes:
    """Convenience function: render a session as a ZIP bundle."""
    if options is None:
        options = RenderOptions()
    return build_zip(turns, stats, meta, options, base_name, theme)