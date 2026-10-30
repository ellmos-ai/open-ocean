"""
Distributed atomic leases for cross-process coordination.

Zero-Trust rationale: a worker (tray, headless, agent) must never *assume*
that it holds a lease, because check-then-write sequences race under
concurrent access. The only trustworthy proof is the effect of a single
atomic SQL statement against the shared SQLite store. Claiming is
therefore one atomic INSERT OR REPLACE guarded by a NOT EXISTS clause:
it steals an expired lease and refuses a live one, all in a single
statement. This closes
the atomic-claim gap of worker.py / chat_tray.py (bach/ROADMAP.md, core
gap 1).

Every lease row carries an AUTOINCREMENT fencing token. Tokens increase
monotonically and are never reused, not even across release/re-claim or
steals, so a preempted holder presenting a stale token to renew() or
release() is rejected.

Fail-closed: invalid arguments raise ValueError, and any SQLite failure
(including a defective database file) raises CoordinationError. No code
path ever simulates a free lease.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CoordinationError", "Lease", "LeaseStore"]

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leases (
    name       TEXT NOT NULL UNIQUE,
    owner      TEXT NOT NULL,
    created    REAL NOT NULL,
    expires_at REAL NOT NULL,
    token      INTEGER PRIMARY KEY AUTOINCREMENT
);
"""

# Atomic claim: the INSERT materializes exactly one row iff no *live*
# lease for :name exists. An expired row slips past the NOT EXISTS guard
# (it only filters live leases), but OR REPLACE replaces that expired
# row atomically. Inserting NULL for the INTEGER PRIMARY KEY forces a
# fresh AUTOINCREMENT fencing token. Concurrent claimers serialize on
# the database write lock; only one can win.
_CLAIM_SQL = """
INSERT OR REPLACE INTO leases (name, owner, created, expires_at, token)
SELECT :name, :owner, :created, :expires_at, NULL
WHERE NOT EXISTS (
    SELECT 1 FROM leases WHERE name = :name AND expires_at > :now
);
"""

# Fencing on renew(): an old holder whose token went stale (lease stolen
# after TTL expiry) cannot extend somebody else's lease.
_RENEW_SQL = """
UPDATE leases SET expires_at = :expires_at
WHERE name = :name AND token = :token;
"""

_RELEASE_SQL = "DELETE FROM leases WHERE name = :name AND token = :token;"
_OWNER_SQL = "SELECT owner FROM leases WHERE name = :name AND expires_at > :now;"
_PRUNE_SQL = "DELETE FROM leases WHERE expires_at <= :now;"


class CoordinationError(RuntimeError):
    """The lease store could not fulfil an operation (fail-closed)."""


@dataclass(frozen=True)
class Lease:
    """Immutable proof of a held lease.

    token is the fencing token: strictly increasing per database and
    never reused, so it unambiguously orders lease generations.
    """

    name: str
    owner: str
    created: float
    expires_at: float
    token: int


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    return value


def _require_ttl(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"ttl_seconds must be a positive finite number, got {value!r}")
    return float(value)


def _require_token(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"token must be a positive int, got {value!r}")
    return value


class LeaseStore:
    """Atomic lease claims against a shared SQLite database file.

    Thread-safe: every thread gets its own connection (WAL mode, busy
    timeout, autocommit). Fail-closed: constructor and operations raise
    CoordinationError whenever the underlying database misbehaves.
    """

    def __init__(self, db_path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self._db_path = str(db_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._local = threading.local()
        # Open eagerly so a defective or unwritable store fails in the
        # constructor and can never be mistaken for an empty one.
        self._conn()

    # -- internal --------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        try:
            new_conn = sqlite3.connect(
                self._db_path,
                timeout=self._busy_timeout_ms / 1000.0,
                # autocommit: every single statement is its own atomic unit
                isolation_level=None,
            )
            new_conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
            new_conn.execute("PRAGMA journal_mode = WAL;")
            new_conn.execute("PRAGMA synchronous = NORMAL;")
            new_conn.execute(_SCHEMA_SQL)
        except sqlite3.Error as exc:
            raise CoordinationError(
                f"cannot open lease store {self._db_path!r}: {exc}"
            ) from exc
        self._local.conn = new_conn
        return new_conn

    # -- claims ----------------------------------------------------------

    def claim(self, name: str, owner: str, ttl_seconds: float) -> Lease | None:
        """Try to atomically acquire the lease ``name`` for ``owner``.

        Returns the won Lease, or None when another owner holds a live
        lease. An expired lease is stolen in the same call (with a fresh,
        larger fencing token).
        """
        name = _require_text(name, "name")
        owner = _require_text(owner, "owner")
        ttl = _require_ttl(ttl_seconds)
        now = time.time()
        params = {
            "name": name,
            "owner": owner,
            "created": now,
            "expires_at": now + ttl,
            "now": now,
        }
        conn = self._conn()
        try:
            cur = conn.execute(_CLAIM_SQL, params)
            if cur.rowcount == 1 and cur.lastrowid is not None:
                return Lease(
                    name=name,
                    owner=owner,
                    created=now,
                    expires_at=params["expires_at"],
                    token=int(cur.lastrowid),
                )
            return None
        except sqlite3.Error as exc:
            raise CoordinationError(f"claim of lease {name!r} failed: {exc}") from exc

    def renew(self, name: str, token: int, ttl_seconds: float) -> bool:
        """Extend a held lease. False when name/token do not match exactly."""
        name = _require_text(name, "name")
        token = _require_token(token)
        ttl = _require_ttl(ttl_seconds)
        params = {"name": name, "token": token, "expires_at": time.time() + ttl}
        try:
            cur = self._conn().execute(_RENEW_SQL, params)
        except sqlite3.Error as exc:
            raise CoordinationError(f"renew of lease {name!r} failed: {exc}") from exc
        return cur.rowcount == 1

    def release(self, name: str, token: int) -> bool:
        """Delete a held lease. False when name/token do not match exactly."""
        name = _require_text(name, "name")
        token = _require_token(token)
        try:
            cur = self._conn().execute(
                _RELEASE_SQL, {"name": name, "token": token}
            )
        except sqlite3.Error as exc:
            raise CoordinationError(f"release of lease {name!r} failed: {exc}") from exc
        return cur.rowcount == 1

    def owner_of(self, name: str) -> str | None:
        """Owner of the live lease ``name``; None when absent or expired."""
        name = _require_text(name, "name")
        try:
            row = self._conn().execute(
                _OWNER_SQL, {"name": name, "now": time.time()}
            ).fetchone()
        except sqlite3.Error as exc:
            raise CoordinationError(f"lookup of lease {name!r} failed: {exc}") from exc
        return str(row[0]) if row is not None else None

    def prune_expired(self) -> int:
        """Delete all expired leases. Returns the number of rows removed."""
        try:
            cur = self._conn().execute(_PRUNE_SQL, {"now": time.time()})
        except sqlite3.Error as exc:
            raise CoordinationError(f"pruning expired leases failed: {exc}") from exc
        return int(cur.rowcount)

    def close(self) -> None:
        """Close this thread's connection (idempotent)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            self._local.conn = None
            try:
                conn.close()
            except sqlite3.Error:
                pass
