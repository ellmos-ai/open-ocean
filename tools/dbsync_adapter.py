"""Local, explicit-path adapter for the six remaining K9 dbsync operations.

This is a source adapter, not BACH wiring or old/new parity evidence. The caller
owns application schema creation and the exclusive local writer claim. Existing
databases must be quiescent; this adapter rejects SQLite sidecars, links and
reparse points. It is not a concurrent live-database or cross-host coordinator.
Backup, verification and retention are delegated to the pinned TransitSync.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import sys
import tempfile
import types
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

CARRIER_COMMIT = "7648a20b11ca958e9622d2b5d8a13fd02613e92a"
CARRIER_HASHES = {
    "core.py": "f90ac3134c64f68b4833650a44cb07fb4b020f664026b89d3820bd1b70dd2870",
    "credential-triggers.json": "8bc931754dd43cddfcebbfa3e20260ebfca3d16d12a6bfd6dafe37ee9b412e22",
}
OPERATIONS = frozenset({"backup", "status", "enable", "disable", "cleanup", "init"})


class AdapterRefusal(ValueError):
    """Stable reason code; never includes database values or exception payloads."""


def _path(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise AdapterRefusal("absolute-path-required")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AdapterRefusal("linked-path-refused")
    return path.resolve()


@dataclass(frozen=True)
class AdapterConfig:
    database: Path
    transit: Path
    state: Path
    marker: Path
    heartbeat: Path
    node_id: str
    namespace: str
    required_schema: Mapping[str, tuple[str, ...]]
    user_version: int


@dataclass(frozen=True)
class OperationResult:
    operation: str
    outcome: str  # supported, dry-run, refused, error
    code: str
    message: str
    data: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.outcome in {"supported", "dry-run"}


def _atomic_bytes(path: Path, content: bytes) -> None:
    _path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class DBSyncAdapter:
    """All paths, schema/version, identity, source and clock must be injected.

    ``handle`` defaults to dry-run. Cleanup additionally requires ``scope`` to
    be exactly ``local-node`` or ``all-nodes`` even for a preview. No method
    creates an application DB, rewrites a carrier state or starts a service.
    ``init`` means validation, not first-copy or migration.
    """

    def __init__(self, config: AdapterConfig, *, carrier_root: Path, clock: Callable[[], datetime]):
        self.config = config
        self.carrier_root = _path(carrier_root)
        self.clock = clock
        self._paths()

    def _paths(self) -> None:
        c = self.config
        paths = [_path(getattr(c, name)) for name in ("database", "transit", "state", "marker", "heartbeat")]
        if len(set(paths)) != len(paths):
            raise AdapterRefusal("overlapping-paths")
        database, transit, state, marker, heartbeat = paths
        if any(transit in path.parents for path in (database, state, marker, heartbeat)):
            raise AdapterRefusal("local-state-inside-transit")
        if any(left in right.parents for left in paths for right in paths if left != right):
            raise AdapterRefusal("overlapping-paths")
        if not isinstance(c.node_id, str) or not isinstance(c.namespace, str):
            raise AdapterRefusal("invalid-identity")
        if not c.node_id or not c.namespace:
            raise AdapterRefusal("invalid-identity")
        if type(c.user_version) is not int or c.user_version < 1 or not isinstance(c.required_schema, Mapping) or not c.required_schema:
            raise AdapterRefusal("explicit-schema-version-required")
        for table, columns in c.required_schema.items():
            if not isinstance(table, str) or not table or not isinstance(columns, tuple) or not columns:
                raise AdapterRefusal("invalid-schema-contract")
            if any(not isinstance(column, str) or not column for column in columns):
                raise AdapterRefusal("invalid-schema-contract")

    def _carrier(self):
        # Hash code before execution; compile verified bytes, never cached .pyc.
        package = _path(self.carrier_root / "sqlite_transit_sync")
        sources = {}
        for filename, digest in CARRIER_HASHES.items():
            content = _path(package / filename).read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(content).hexdigest() != digest:
                raise AdapterRefusal("carrier-pin-mismatch")
            sources[filename] = content
        name = f"_ocean_dbsync_carrier_{uuid.uuid4().hex}"
        module = types.ModuleType(name)
        module.__file__ = str(package / "core.py")
        sys.modules[name] = module  # dataclass resolves this during compilation
        try:
            exec(compile(sources["core.py"], module.__file__, "exec"), module.__dict__)
        finally:
            del sys.modules[name]
        c = self.config
        config = module.SyncConfig(
            database=c.database, transit=c.transit, state=c.state,
            node_id=c.node_id, namespace=c.namespace,
            secret_patterns_file=package / "credential-triggers.json",
            # These unused replica paths are explicit to avoid carrier home/env defaults.
            key_file=c.state.parent / "unused-republica.key",
            republica_root=c.state.parent / "unused-republica",
        )
        if config.node_id != c.node_id or config.namespace != c.namespace:
            raise AdapterRefusal("identity-would-be-normalized")
        return module, config

    def _engine(self, *, create: bool = False):
        module, config = self._carrier()
        if not create and (not config.transit.is_dir() or not config.state.parent.is_dir()):
            raise AdapterRefusal("carrier-directories-not-prepared")
        return module.TransitSync(config)

    def _now(self) -> datetime:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise AdapterRefusal("timezone-aware-clock-required")
        return now

    def _heartbeat(self) -> dict:
        path = self.config.heartbeat
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            for node, entry in payload.items():
                if not isinstance(node, str) or not node or not isinstance(entry, dict):
                    raise ValueError
                seen = datetime.fromisoformat(entry["last_seen"])
                if seen.tzinfo is None or seen.utcoffset() is None:
                    raise ValueError
                if type(entry["pid"]) is not int or entry["pid"] < 1 or type(entry["active"]) is not bool:
                    raise ValueError
            return payload
        except (ValueError, KeyError, TypeError):
            raise AdapterRefusal("invalid-heartbeat") from None

    def _schema(self) -> None:
        path = self.config.database
        if not path.is_file():
            raise AdapterRefusal("application-database-missing")
        if any(path.parent.glob(f"{path.name}-*")):
            raise AdapterRefusal("database-sidecars-refused")
        # An immutable read never creates SQLite journals or shared-memory files.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise AdapterRefusal("database-integrity-failed")
            if connection.execute("PRAGMA user_version").fetchone()[0] != self.config.user_version:
                raise AdapterRefusal("application-schema-version-mismatch")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, columns in self.config.required_schema.items():
                if table not in tables:
                    raise AdapterRefusal("application-schema-mismatch")
                quoted = table.replace('"', '""')
                present = {row[1] for row in connection.execute(f'PRAGMA table_info("{quoted}")')}
                if not set(columns) <= present:
                    raise AdapterRefusal("application-schema-mismatch")
            # The pinned redaction policy names this BACH table literally.
            if any(table.casefold() == "secrets" and table != "secrets" for table in tables):
                raise AdapterRefusal("secret-table-case-not-supported")

    def _marker(self) -> bool:
        marker = self.config.marker
        if not marker.exists():
            return False
        if not marker.is_file() or marker.read_bytes() != b"enabled":
            raise AdapterRefusal("foreign-marker-refused")
        return True

    def _carrier_state(self) -> None:
        if not self.config.state.exists():
            return
        try:
            state = json.loads(self.config.state.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or type(state.get("protocol")) is not int or state["protocol"] != 1:
                raise ValueError
            if not isinstance(state.get("last_pulled"), dict):
                raise ValueError
            for node, token in state["last_pulled"].items():
                if not isinstance(node, str) or not node or not isinstance(token, str):
                    raise ValueError
                datetime.strptime(token, "%Y%m%dT%H%M%S%fZ")
        except (ValueError, TypeError, KeyError):
            raise AdapterRefusal("invalid-carrier-state") from None

    @staticmethod
    def _snapshot_safety(engine, node_only: str | None = None) -> None:
        # Carrier verification uses SQLite mode=ro, which may create sidecars for
        # WAL artifacts. Reject such artifacts and linked payloads before that call.
        for manifest in engine.config.transit.glob(f"{engine.config.namespace}__*__*.sqlite-snapshot.json"):
            _path(manifest)
        snapshots = engine.snapshots(verify=False)
        for snapshot in snapshots:
            if node_only is not None and snapshot.node_id != node_only:
                continue
            _path(snapshot.path)
            _path(snapshot.manifest_path)
            if any(snapshot.path.parent.glob(f"{snapshot.path.name}-*")):
                raise AdapterRefusal("snapshot-sidecars-refused")

    @classmethod
    def _verified(cls, engine) -> list:
        cls._snapshot_safety(engine)
        return engine.snapshots(verify=True)

    def handle(self, operation: str, *, dry_run: bool = True, scope: str | None = None,
               keep_days: int = 7, keep_per_node: int = 10) -> OperationResult:
        """Return structured outcomes, including honest partial mutation failures.

        On a carrier apply exception, completed carrier effects may remain;
        ``carrier-call-failed-state-unknown`` is never a rollback claim. If
        heartbeat persistence fails after backup, the published snapshot is
        returned with ``snapshot-published-heartbeat-failed``.
        """
        data: dict = {}
        carrier_applied = False
        heartbeat_pending = False
        try:
            if operation not in OPERATIONS:
                raise AdapterRefusal("operation-outside-local-scope")
            if type(dry_run) is not bool:
                raise AdapterRefusal("boolean-dry-run-required")
            self._paths()
            self._carrier()  # refuse pin/config drift even for marker operations
            self._carrier_state()
            outcome = "dry-run" if dry_run else "supported"
            if operation in {"enable", "disable"}:
                enabled = self._marker()
                if not dry_run:
                    if operation == "enable" and not enabled:
                        _atomic_bytes(self.config.marker, b"enabled")
                    elif operation == "disable" and enabled:
                        self.config.marker.unlink()
                message = "Auto-Sync aktiviert (wirkt bei nächstem Start)" if operation == "enable" else "Auto-Sync deaktiviert"
                data = {"previous_enabled": enabled, "requested_enabled": operation == "enable"}
            elif operation == "init":
                self._schema()
                message = "Vorhandenes Anwendungsschema geprüft; keine Erstkopie oder Migration"
                data = {"validated_user_version": self.config.user_version, "created_database": False}
            elif operation == "backup":
                self._schema()
                if "secrets" not in self.config.required_schema:
                    raise AdapterRefusal("explicit-secrets-schema-required")
                heartbeats = self._heartbeat()
                now = self._now()
                if dry_run:
                    message = "Vorschau: Snapshot und Heartbeat würden erstellt"
                else:
                    engine = self._engine(create=True)
                    carrier_applied = True
                    snapshot = engine.push()
                    data["snapshot"] = snapshot.as_dict()
                    heartbeat_pending = True
                    heartbeats[self.config.node_id] = {"last_seen": now.isoformat(), "pid": os.getpid(), "active": True}
                    _atomic_bytes(self.config.heartbeat, (json.dumps(heartbeats, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                    heartbeat_pending = False
                    message = f"Backup erstellt: {snapshot.path.name}"
            elif operation == "status":
                engine = self._engine()
                snapshots = self._verified(engine)
                status = engine.status()
                if not isinstance(status["last_pulled"], dict):
                    raise AdapterRefusal("invalid-carrier-state")
                data = {"carrier": status, "verified_snapshots": [s.as_dict() for s in snapshots],
                        "heartbeats": self._heartbeat(), "enabled": self._marker()}
                outcome = "supported"
                message = "Status gelesen; Snapshotmetadaten verifiziert"
            else:  # cleanup: a scope is a caller decision, never an inferred default
                if not isinstance(scope, str) or scope not in {"local-node", "all-nodes"}:
                    raise AdapterRefusal("explicit-cleanup-scope-required")
                if any(type(value) is not int or value < 0 for value in (keep_days, keep_per_node)):
                    raise AdapterRefusal("invalid-retention")
                engine = self._engine()
                self._snapshot_safety(engine, self.config.node_id if scope == "local-node" else None)
                carrier_applied = not dry_run
                data = engine.cleanup(keep_days=keep_days, keep_per_node=keep_per_node,
                                      include_foreign=scope == "all-nodes", dry_run=dry_run)
                message = f"Cleanup abgeschlossen: {len(data['deleted'])} Backups gelöscht" if not dry_run else "Vorschau: Keine Backups gelöscht"
            if dry_run and operation != "status":
                message = "Dry-run — " + message
            return OperationResult(operation, outcome, "ok", message, data)
        except AdapterRefusal as error:
            if carrier_applied:
                code = "snapshot-published-heartbeat-failed" if heartbeat_pending else "carrier-call-failed-state-unknown"
                return OperationResult(operation, "error", code, "Operation fehlgeschlagen",
                                       {**data, "refusal_code": str(error)})
            return OperationResult(operation, "refused", str(error), "Operation sicher verweigert", data)
        except Exception as error:
            code = "snapshot-published-heartbeat-failed" if heartbeat_pending else (
                "carrier-call-failed-state-unknown" if carrier_applied else "operation-failed")
            return OperationResult(operation, "error", code, "Operation fehlgeschlagen",
                                   {**data, "error_class": type(error).__name__})
