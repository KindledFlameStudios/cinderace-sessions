"""CinderACE Sessions v2 — single-instance process lock.

Prevents duplicate controller or tray instances using OS-level file locks.
Adapted from ember-memory's single_instance module.
"""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class InstanceLock:
    """Hold an OS-level lock for the lifetime of a process.

    Supports use as a context manager:
        with InstanceLock("controller") as lock:
            if not lock.acquired:
                sys.exit("Already running")

    The lock is also released automatically on interpreter exit via atexit.
    """

    def __init__(self, name: str):
        lock_dir = Path.home() / ".cinderace-sessions"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self.path = lock_dir / f"{name}.lock"
        self.name = name
        self.handle = None
        self.acquired = False
        self._registered_atexit = False

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired, False if held by another process."""
        if self.acquired:
            return True
        try:
            # Open with explicit encoding for cross-platform consistency
            self.handle = self.path.open("a+", encoding="utf-8")
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                if not self.handle.read(1):
                    self.handle.seek(0)
                    self.handle.write(" ")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(str(os.getpid()))
            self.handle.flush()
            self.acquired = True
            # Register cleanup on interpreter exit (only once)
            if not self._registered_atexit:
                atexit.register(self.close)
                self._registered_atexit = True
            return True
        except OSError as e:
            logger.debug("Failed to acquire instance lock '%s': %s", self.name, e)
            self._close_handle()
            return False

    def close(self) -> None:
        """Release the lock and close the file handle. Safe to call multiple times."""
        if not self.acquired and self.handle is None:
            return
        try:
            if self.acquired:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            logger.debug("Error releasing lock '%s': %s", self.name, e)
        finally:
            self.acquired = False
            self._close_handle()

    def _close_handle(self) -> None:
        """Close the file handle if open. Safe to call multiple times."""
        if self.handle is not None:
            try:
                self.handle.close()
            except OSError:
                pass
            finally:
                self.handle = None

    # ── Context manager support ───────────────────────────────────────

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def acquire_instance_lock(name: str) -> InstanceLock | None:
    """Try to acquire an instance lock.

    Returns the InstanceLock if acquired, None if already held by another process.
    The caller is responsible for keeping a reference to the returned lock for
    the lifetime of the process (otherwise GC may release it early).
    """
    lock = InstanceLock(name)
    return lock if lock.acquire() else None