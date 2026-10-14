"""Explicit host-local writer authority, separate from the Polarstern lease.

All cooperating clients must use the SAME configured local directory and host
identity. The inode is never removed/replaced. The first byte is the OS lock;
the remaining checksummed journal holds unresolved reservations across crashes.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import uuid

from .contracts import Hold, identity


class HostWriterAuthority:
    def __init__(self, directory: Path, host_id: str):
        self.host_id = identity(host_id)
        self.directory = Path(directory)
        self.authority_id = ""
        self._stream = None
        self._pid = None
        self._path = None
        self._arbiter_bound = False

    @property
    def held(self) -> bool:
        return self._stream is not None and not self._stream.closed

    def __enter__(self):
        if self.held:
            raise Hold("writer authority is already held")
        if not self.directory.is_absolute() or not self.directory.is_dir():
            raise Hold("explicit existing absolute host-local state directory required")
        if self.directory.resolve() != self.directory.absolute():
            raise Hold("linked state directory is not allowed")
        if self.directory.drive.startswith("\\\\") or any(p.lower().startswith("onedrive") for p in self.directory.parts):
            raise Hold("writer state must be host-local and outside OneDrive")
        path = self.directory / (self.host_id + ".writer")
        if path.is_symlink():
            raise Hold("linked writer file is not allowed")
        flags = os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            try:
                descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                descriptor = os.open(path, flags)
                created = False
            stream = os.fdopen(descriptor, "r+b", buffering=0)
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if "stream" in locals():
                stream.close()
            raise Hold("host-local writer cannot be exclusively acquired") from exc
        self._stream, self._path, self._pid = stream, path, os.getpid()
        self.authority_id = uuid.uuid4().hex
        self._arbiter_bound = False
        try:
            if created:
                self.record(None)
            self.unresolved()
        except Exception:
            self.__exit__()
            raise
        return self

    def require(self):
        if not self.held or self._pid != os.getpid():
            raise Hold("host-local writer authority is not held by this process")
        try:
            current = self._path.stat(follow_symlinks=False)
            opened = os.fstat(self._stream.fileno())
            if self._path.is_symlink() or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise Hold("writer inode identity changed")
        except OSError as exc:
            raise Hold("writer inode identity is unavailable") from exc

    def claim_arbiter(self):
        self.require()
        if self._arbiter_bound:
            raise Hold("this host writer already has an arbiter")
        self._arbiter_bound = True

    def record(self, unresolved: dict | None):
        self.require()
        payload = json.dumps({"unresolved": unresolved}, sort_keys=True, separators=(",", ":"), allow_nan=False)
        journal = json.dumps({
            "payload": payload,
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        }, sort_keys=True).encode("utf-8")
        # Never replace the locked inode. A torn journal fails closed on reopen.
        self._stream.seek(0)
        content = b"0" + journal
        if self._stream.write(content) != len(content):
            raise Hold("writer journal short write; independent recovery required")
        self._stream.truncate()
        os.fsync(self._stream.fileno())

    def unresolved(self) -> dict | None:
        self.require()
        self._stream.seek(1)
        raw = self._stream.read(64 * 1024 + 1)
        try:
            if len(raw) > 64 * 1024:
                raise ValueError("journal too large")
            outer = json.loads(raw)
            if not isinstance(outer, dict) or set(outer) != {"payload", "sha256"}:
                raise ValueError("journal envelope")
            payload = outer["payload"]
            if not isinstance(payload, str):
                raise ValueError("journal payload")
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != outer["sha256"]:
                raise ValueError("journal hash")
            result = json.loads(payload)
            if not isinstance(result, dict) or set(result) != {"unresolved"} or (
                result["unresolved"] is not None and not isinstance(result["unresolved"], dict)
            ):
                raise ValueError("journal schema")
            return result["unresolved"]
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise Hold("writer journal is invalid; independent recovery required") from exc

    def __exit__(self, *exc):
        if self.held:
            stream = self._stream
            # fork inherits the open-file description. LOCK_UN in the child
            # would release the parent's POSIX lock as well; close only.
            if self._pid != os.getpid():
                stream.close()
                self._stream = None
                return
            try:
                if os.name == "nt":
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()
        self._stream = None
