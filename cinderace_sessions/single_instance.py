"""CinderACE Sessions v2 — single-instance process lock.

Prevents duplicate controller or tray instances using OS-level file locks.
Adapted from ember-memory's single_instance module.
"""

from __future__ import annotations

import os
from pathlib import Path


class InstanceLock:
    """Hold an OS-level lock for the lifetime of a process."""

    def __init__(self, name: str):
        lock_dir = Path.home() / ".cinderace-sessions"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self.path = lock_dir / f"{name}.lock"
        self.handle = self.path.open("a+")
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        try:
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
            return True
        except OSError:
            self.close()
            return False

    def close(self) -> None:
        try:
            if self.acquired:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.acquired = False
            self.handle.close()


def acquire_instance_lock(name: str) -> InstanceLock | None:
    """Try to acquire an instance lock. Returns None if already held."""
    lock = InstanceLock(name)
    return lock if lock.acquire() else None