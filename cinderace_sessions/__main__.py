"""CinderACE Sessions v2 — entry point for all commands."""

import logging
import os
import subprocess
import sys
from datetime import datetime


def _configure_logging():
    """Set up centralized logging for the application."""
    log_dir = os.path.join(os.path.expanduser("~"), ".cinderace-sessions")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "cinderace-sessions.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    # Quiet noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("webview").setLevel(logging.INFO)


def _open_launch_log(name: str):
    """Open a local launch log for detached app startup diagnostics."""
    log_dir = os.path.join(os.path.expanduser("~"), ".cinderace-sessions")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, name)
    handle = open(path, "a", encoding="utf-8")
    handle.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n")
    handle.flush()
    return handle


def launch_app_detached():
    """Launch the controller as a detached app process and return immediately."""
    env = {**os.environ, "CINDERACE_SESSIONS_LAUNCHER": "1"}
    command = [sys.executable, "-m", "cinderace_sessions", "controller"]
    log_handle = _open_launch_log("controller_launch.log")
    popen_kwargs = {
        "cwd": os.path.expanduser("~"),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": log_handle,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        return subprocess.Popen(command, **popen_kwargs)
    finally:
        log_handle.close()


def launch_controller():
    """Launch the desktop controller in the foreground."""
    from cinderace_sessions.controller_app import main as controller_main

    controller_main()


def launch_tray():
    """Launch the system tray."""
    from controller.tray import main as tray_main

    tray_main()


def main():
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("CinderACE Sessions v2 starting")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "launch"

    if cmd in {"launch", "app"}:
        launch_app_detached()

    elif cmd in {"controller", "ui"}:
        launch_controller()

    elif cmd == "tray":
        launch_tray()

    elif cmd == "setup":
        launch_controller()

    elif cmd in {"install-desktop", "uninstall-desktop", "desktop-status"}:
        # Will be implemented in Phase 7
        print(f"Desktop integration not yet implemented. Command: {cmd}")

    else:
        print("CinderACE Sessions v2.0")
        print()
        print("Commands:")
        print("  cinderace-sessions               Launch the app and return immediately")
        print("  cinderace-sessions controller     Launch the controller in the foreground")
        print("  cinderace-sessions tray           Launch the system tray")
        print("  cinderace-sessions setup          Launch the controller in the foreground")
        print("  cinderace-sessions install-desktop Create app launcher / Start Menu shortcut")
        print("  cinderace-sessions uninstall-desktop Remove app launcher / Start Menu shortcut")
        print()
        print("Quick start:")
        print("  cinderace-sessions                Open the app")


if __name__ == "__main__":
    main()