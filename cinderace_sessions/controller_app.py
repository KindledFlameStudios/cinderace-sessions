"""CinderACE Sessions v2 — controller app (pywebview desktop GUI).

This is the main application window with the SessionsAPI backend
exposed to the JavaScript frontend via pywebview's bridge.
"""

from __future__ import annotations

import webview
from cinderace_sessions.config import load_config


class SessionsAPI:
    """Backend API exposed to the JS frontend via pywebview bridge."""

    def get_config(self) -> dict:
        return load_config()

    def save_settings(self, settings: dict) -> bool:
        from cinderace_sessions.config import save_settings
        return save_settings(settings)

    def get_version(self) -> str:
        from cinderace_sessions import __version__
        return __version__


def run_gui():
    """Create and run the pywebview window."""
    config = load_config()

    api = SessionsAPI()

    # Load the UI HTML — for now, a minimal placeholder
    # Phase 4 will replace this with the full ui.html template
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                margin: 0;
                padding: 24px;
                background: #050505;
                color: #e0dcd0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            }
            h1 { color: #FF7820; font-size: 20px; }
            p { color: #888; font-size: 14px; }
            .badge {
                display: inline-block;
                background: #1a1000;
                border: 1px solid #FF7820;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
                color: #FF7820;
            }
        </style>
    </head>
    <body>
        <h1>CinderACE Sessions v2</h1>
        <p>Session discovery, export, and summarization for AI CLIs.</p>
        <p>Controller loaded. Full UI coming in Phase 4.</p>
        <span class="badge">Skeleton Active</span>
    </body>
    </html>
    """

    window = webview.create_window(
        title="CinderACE Sessions",
        html=html,
        js_api=api,
        width=840,
        height=660,
        min_size=(700, 550),
        background_color="#050505",
        text_select=True,
    )

    webview.start(debug=True)


def main():
    """Entry point for the controller."""
    run_gui()


if __name__ == "__main__":
    main()