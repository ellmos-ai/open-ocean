"""Observe six K9 operations through four pinned, isolated source arms.

This is a fixture comparison tool. It never grants runtime or parity acceptance.
Run one case per dedicated process: the filesystem/network guard is permanent.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import stat
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

MODES = ("historical-native", "current-native", "current-shared", "ocean")
OPERATIONS = ("backup", "status", "enable", "disable", "cleanup", "init")
SCENARIOS = ("prepared", "missing", "foreign-marker", "enabled-marker",
             "corrupt-state", "corrupt-heartbeat", "sidecar", "stale-copy",
             "snapshot-pairs", "corrupt-snapshot")
PROFILES = ("minimal7", "native0", "native7-fts")
NODE = "node-a"


class ProbeRefusal(ValueError):
    """A setup/source refusal; never a successful operation observation."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ProbeRefusal("absolute-unlinked-path-required")
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProbeRefusal("linked-path-refused")
    return path.resolve()


def contract() -> dict:
    path = Path(__file__).resolve().parents[2] / "tests/fixtures/k9_remaining/contract.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def sources(manifest: Path) -> dict:
    """Bind every imported dependency to the shipped immutable source hashes."""
    manifest = safe_path(manifest)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    required = contract()["sources"]
    if value.get("rc") != 0 or set(value.get("sources", {})) != set(required):
        raise ProbeRefusal("complete-source-manifest-required")
    result = {}
    for name, expected in required.items():
        entry = value["sources"][name]
        if entry.get("commit") != expected["commit"]:
            raise ProbeRefusal("source-commit-mismatch")
        root = safe_path(entry["root"])
        if set(entry.get("files", {})) != set(expected["files"]):
            raise ProbeRefusal("source-closure-mismatch")
        for relative, wanted in expected["files"].items():
            path = safe_path(root / relative)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ProbeRefusal("independent-source-file-required")
            data = path.read_bytes()
            if digest(data.replace(b"\r\n", b"\n")) != wanted:
                raise ProbeRefusal("source-bytes-mismatch")
        result[name] = root
    return result


def inventory(root: Path) -> dict:
    """Include directories, file bytes and metadata; never follow aliases."""
    result = {}
    pending = [root]
    while pending:
        parent = pending.pop()
        for path in sorted(parent.iterdir()):
            if len(result) >= 4096:
                raise ProbeRefusal("fixture-inventory-limit")
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            record = {"mode": info.st_mode, "mtime_ns": info.st_mtime_ns,
                      "size": info.st_size, "nlink": info.st_nlink}
            if stat.S_ISDIR(info.st_mode):
                record["kind"] = "directory"
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                record.update(kind="file", sha256=digest(path.read_bytes()))
            else:
                record.update(kind="alias-or-special")
            result[relative] = record
    return result


def image(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    try:
        with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1",
                                               uri=True)) as connection:
            schema = connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
            ).fetchall()
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
            )]
            rows = {}
            counts = {}
            for name in tables:
                quoted = '"' + name.replace('"', '""') + '"'
                values = connection.execute("SELECT * FROM " + quoted).fetchall()
                # Typed repr preserves BLOB/NULL distinctions without exposing values.
                rows[name] = digest(repr(values).encode("utf-8"))
                counts[name] = len(values)
            return {"exists": True, "schema_sha256": digest(repr(schema).encode()),
                    "rows_sha256": rows, "counts": counts,
                    "user_version": connection.execute("PRAGMA user_version").fetchone()[0]}
    except sqlite3.Error as error:
        return {"exists": True, "error_class": type(error).__name__}


def _database(path: Path, profile: str, roots: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(sqlite3.connect(path)) as connection:
        if profile == "minimal7":
            connection.executescript(
                "PRAGMA user_version=7;"
                "CREATE TABLE items(id INTEGER PRIMARY KEY,value TEXT,updated_at TEXT);"
                "CREATE TABLE secrets(id INTEGER PRIMARY KEY,key TEXT,value TEXT);"
                "INSERT INTO items VALUES(1,'synthetic-public','2026-01-01T00:00:00Z');"
            )
        else:
            sql = roots["bach-current"] / "system/data/schema/schema.sql"
            connection.executescript(sql.read_text(encoding="utf-8"))
            if profile == "native7-fts":
                connection.execute("PRAGMA user_version=7")
        if profile == "minimal7":
            connection.execute(
                "INSERT INTO secrets(key,value) VALUES(?,?)",
                ("synthetic-fixture", "SYNTHETIC_SECRET_ONLY"),
            )
        else:
            connection.execute(
                "INSERT INTO secrets(key,value,created_at,updated_at) VALUES(?,?,?,?)",
                ("synthetic-fixture", "SYNTHETIC_SECRET_ONLY",
                 "2026-01-01 00:00:00", "2026-01-01 00:00:00"),
            )
        connection.commit()


def prepare(work: Path, profile: str, scenario: str, roots: dict) -> dict:
    work = safe_path(work)
    if not work.is_dir() or any(work.iterdir()):
        raise ProbeRefusal("fresh-empty-owned-workdir-required")
    paths = {
        "database": work / "local/bach.db", "transit": work / "transit",
        "state": work / "adapter/state.json", "marker": work / "system/data/config/db_sync_enabled",
        "heartbeat": work / "heartbeat.json", "base": work / "system",
    }
    if scenario != "missing":
        _database(paths["database"], profile, roots)
        paths["transit"].mkdir()
        paths["state"].parent.mkdir()
        paths["base"].mkdir()
    if scenario in {"foreign-marker", "enabled-marker"}:
        paths["marker"].parent.mkdir(parents=True, exist_ok=True)
        paths["marker"].write_bytes(b"foreign" if scenario == "foreign-marker" else b"enabled")
    if scenario == "corrupt-state":
        paths["state"].write_text("{invalid", encoding="utf-8")
    if scenario == "corrupt-heartbeat":
        paths["heartbeat"].write_text("{invalid", encoding="utf-8")
    if scenario == "sidecar":
        paths["database"].with_name("bach.db-wal").write_bytes(b"synthetic-sidecar")
    if scenario == "stale-copy":
        paths["database"].unlink()
        _database(paths["base"] / "data/bach.db", profile, roots)
    if scenario in {"snapshot-pairs", "corrupt-snapshot"}:
        # Protocol fixtures, not a replacement snapshot/backup implementation.
        for node in ("node-a", "node-b"):
            for token in ("20000101T000000000000Z", "29990101T000000000000Z"):
                target = paths["transit"] / f"bach__{node}__{token}.sqlite-snapshot"
                target.write_bytes(paths["database"].read_bytes())
                payload = {"protocol": 1, "namespace": "bach", "node_id": node,
                           "created_at": token, "snapshot": target.name,
                           "sha256": digest(target.read_bytes()), "size": target.stat().st_size}
                if scenario == "corrupt-snapshot" and token.startswith("2000"):
                    payload["sha256"] = "0" * 64
                target.with_suffix(target.suffix + ".json").write_text(json.dumps(payload), encoding="utf-8")
                # Same eligible age, deliberately different timestamp policy/source format.
                legacy = paths["transit"] / f"bach_{node}_2000-01-01T00-00-00.bachdb"
                legacy.write_bytes(paths["database"].read_bytes())
                os.utime(legacy, (946684800, 946684800))
    # Bind only synthetic fixture metadata before any product measurement.
    # Preserve all subsequent real constructor/operation effects.
    fixture_time_ns = 946684800000000000
    for relative in inventory(work):
        os.utime(work / relative, ns=(fixture_time_ns, fixture_time_ns))
    return paths


def boundary(work: Path) -> list:
    violations = []
    def check(value):
        if isinstance(value, int):
            return  # an already opened Python-owned file descriptor
        target = safe_path(os.fsdecode(value))
        if target != work and work not in target.parents:
            violations.append("outside-write")
            raise ProbeRefusal("outside-owned-fixture-write-refused")

    def audit(event, args):
        if event == "sqlite3.connect":
            value = os.fspath(args[0])
            if value == ":memory:":
                return  # source-pinned native readiness builds only its expected schema
            if value.startswith("file:"):
                parsed = urlsplit(value)
                if parsed.netloc or parsed.fragment:
                    raise ProbeRefusal("sqlite-uri-refused")
                value = unquote(parsed.path)
                if os.name == "nt" and len(value) > 3 and value[0] == "/" and value[2] == ":":
                    value = value[1:]
            check(value)
        elif event == "open":
            mode, flags = args[1], args[2]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+"))
            writing = writing or (isinstance(flags, int) and bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writing:
                check(args[0])
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
            check(args[0])
        elif event in {"os.rename", "os.link", "os.symlink"}:
            check(args[0])
            check(args[1])
        elif event == "subprocess.Popen" or event in {
            "socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo"
        }:
            violations.append("process-or-network")
            raise ProbeRefusal("process-or-network-refused")
    sys.addaudithook(audit)
    return violations


def _load(name: str, path: Path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    exec(compile(path.read_bytes().replace(b"\r\n", b"\n"), str(path), "exec"), module.__dict__)
    return module


def _bach(roots: dict, mode: str, paths: dict, constructors: list):
    selected = "bach-old" if mode == "historical-native" else "bach-current"
    root = roots[selected] / "system/hub"
    prefix = "_k9_bach_" + uuid.uuid4().hex
    package = types.ModuleType(prefix)
    package.__path__ = [str(root)]
    sys.modules[prefix] = package
    # The fixture explicitly owns these path inputs. It is not a defaults/startup test.
    config = types.ModuleType(prefix + ".bach_paths")
    config.BACH_DB = paths["database"]
    config.LOCAL_BACH_DIR = paths["database"].parent
    config.PROSYNC_TRANSIT_DIR = paths["transit"]
    sys.modules[config.__name__] = config
    module = _load(prefix + ".db_sync", root / "db_sync.py")
    original = module.DBSyncManager
    def selected_manager(db_path=None, transit_dir=None):
        result = original(db_path=db_path or paths["database"],
                          transit_dir=transit_dir or paths["transit"])
        constructors.append({"class": original.__qualname__,
                             "module_sha256": digest((root / "db_sync.py").read_bytes()),
                             "database": str(result.db_path), "transit": str(result.transit_dir)})
        result.base_path = paths["base"]
        result.local_bach_dir = paths["database"].parent
        result.hostname = NODE
        result.heartbeat_file = paths["heartbeat"]
        return result
    module.DBSyncManager = selected_manager  # actual constructor, explicit fixture input binding
    return module, module.DBSyncHandler(paths["base"])


def run(*, mode: str, operation: str, manifest: Path, work: Path,
        profile: str = "minimal7", scenario: str = "prepared", dry_run: bool = True,
        scope: str | None = None, keep_days: int = 7, keep_per_node: int = 10) -> dict:
    if mode not in MODES or operation not in OPERATIONS or profile not in PROFILES or scenario not in SCENARIOS:
        raise ProbeRefusal("unknown-explicit-selection")
    if type(dry_run) is not bool or scope not in {None, "local-node", "all-nodes"}:
        raise ProbeRefusal("invalid-explicit-input")
    if mode != "ocean" and (keep_days != 7 or keep_per_node != 10):
        raise ProbeRefusal("retention-not-exposed-by-native-or-shared-handler")
    roots = sources(manifest)
    paths = prepare(work, profile, scenario, roots)
    before = inventory(work)
    before_db = image(paths["database"])
    # Measurement precedes all actual handler/manager/adapter/carrier imports.
    sys.dont_write_bytecode = True
    os.environ["BACH_USE_EXTERNAL_TRANSITSYNC"] = "0"
    violations = boundary(work)
    constructors = []
    stream = io.StringIO()
    now = datetime.now(timezone.utc)
    observed = {}
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            if mode in {"historical-native", "current-native", "current-shared"}:
                module, handler = _bach(roots, mode, paths, constructors)
                if mode == "current-shared":
                    shared = __import__(module.__package__ + ".db_sync_adapter", fromlist=["SharedDBSyncAdapter"])
                    config = shared.SharedDBSyncConfig(
                        **{key: paths[key] for key in ("database", "transit", "state", "marker", "heartbeat")},
                        node_id=NODE, namespace="bach", required_schema={"secrets": ("id", "key", "value")},
                        user_version=0 if profile == "native0" else 7,
                    )
                    adapter = shared.SharedDBSyncAdapter(config, ocean_root=roots["ocean"],
                                                         carrier_root=roots["carrier"], clock=lambda: now)
                    args = ["--" + scope] if operation == "cleanup" and scope else []
                    raw = handler.handle(operation, args, dry_run=dry_run, shared_adapter=adapter)
                else:
                    raw = handler.handle(operation, [], dry_run=dry_run)
                observed = {"kind": "handler", "ok": raw[0], "message": raw[1],
                            "provider": mode, "cleanup_arguments_supported": mode == "current-shared"}
            else:
                module = _load("_k9_ocean_" + uuid.uuid4().hex, roots["ocean"] / "tools/dbsync_adapter.py")
                config = module.AdapterConfig(
                    **{key: paths[key] for key in ("database", "transit", "state", "marker", "heartbeat")},
                    node_id=NODE, namespace="bach", required_schema={"secrets": ("id", "key", "value")},
                    user_version=0 if profile == "native0" else 7,
                )
                adapter = module.DBSyncAdapter(config, carrier_root=roots["carrier"], clock=lambda: now)
                raw = adapter.handle(operation, dry_run=dry_run, scope=scope,
                                     keep_days=keep_days, keep_per_node=keep_per_node)
                observed = {"kind": "adapter", "ok": raw.ok, "outcome": raw.outcome,
                            "code": raw.code, "message": raw.message, "data": raw.data,
                            "provider": "ocean"}
    except Exception as error:
        observed = {"kind": "exception", "ok": False, "error_class": type(error).__name__,
                    "reason": str(error) if isinstance(error, (ProbeRefusal, ValueError)) else None}
    after = inventory(work)
    snapshot_images = {
        path.relative_to(work).as_posix(): image(path)
        for path in sorted(paths["transit"].glob("*"))
        if path.is_file() and path.suffix in {".bachdb", ".sqlite-snapshot"}
    } if paths["transit"].is_dir() else {}
    return {"schema": "ellmos.k9.remaining-observation.v1", "mode": mode,
            "operation": operation, "profile": profile, "scenario": scenario,
            "dry_run": dry_run, "scope": scope, "retention": {"keep_days": keep_days, "keep_per_node": keep_per_node}, "pid": os.getpid(),
            "source_pins": {key: value["commit"] for key, value in contract()["sources"].items()},
            "clock": {"adapter": now.isoformat(), "native_and_carrier": "unchanged-source-system-clock"},
            "before": before, "after": after, "file_effects": {
                "created": sorted(set(after) - set(before)),
                "removed": sorted(set(before) - set(after)),
                "changed": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
            }, "before_database": before_db, "after_database": image(paths["database"]),
            "snapshots": snapshot_images, "raw": observed, "captured_output": stream.getvalue(),
            "native_constructors": constructors, "boundary_violations": violations,
            "selection_binding": "explicit fixture paths; original constructor and handler code",
            "parity_accepted": False, "host_or_runtime_acceptance": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--operation", choices=OPERATIONS, required=True)
    parser.add_argument("--profile", choices=PROFILES, default="minimal7")
    parser.add_argument("--scenario", choices=SCENARIOS, default="prepared")
    parser.add_argument("--scope", choices=("local-node", "all-nodes"))
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--keep-per-node", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        receipt = safe_path(args.receipt)
        work = safe_path(args.workdir)
        if receipt.parent != work or receipt.exists():
            raise ProbeRefusal("fresh-receipt-inside-owned-workdir-required")
        result = run(mode=args.mode, operation=args.operation, manifest=args.manifest,
                     work=work, profile=args.profile, scenario=args.scenario,
                     dry_run=not args.apply, scope=args.scope, keep_days=args.keep_days, keep_per_node=args.keep_per_node)
        receipt.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        print(json.dumps({"receipt": str(receipt), "parity_accepted": False}))
        return 0  # observed refusal is data; setup/source failure is nonzero
    except (ProbeRefusal, OSError, ValueError) as error:
        print(json.dumps({"setup_refused": True, "error_class": type(error).__name__,
                          "code": str(error) if isinstance(error, ProbeRefusal) else "unavailable-input"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
