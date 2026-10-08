"""Ocean-only conformance at the real carrier pin; never imports or boots BACH.

Set TRANSIT_SYNC_ROOT to a checkout at the existing evidence pin. With
REQUIRE_DBSYNC_ADAPTER=1 absent prerequisites fail rather than skip. Loading
the carrier compiles verified source bytes and writes no provider bytecode.
These tests are not three-way parity and do not increase the 3/9 evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import dbsync_adapter as adapter_module
from tools.dbsync_adapter import AdapterConfig, AdapterRefusal, DBSyncAdapter

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
SCHEMA = {"items": ("id", "value", "updated_at"), "secrets": ("id", "value", "updated_at")}


@pytest.fixture(scope="module")
def carrier_root():
    value = os.environ.get("TRANSIT_SYNC_ROOT")
    if not value:
        if os.environ.get("REQUIRE_DBSYNC_ADAPTER") == "1":
            pytest.fail("TRANSIT_SYNC_ROOT is required for adapter conformance")
        pytest.skip("set TRANSIT_SYNC_ROOT to run pinned-carrier adapter conformance")
    return Path(value).resolve()


def inventory(root):
    """Include directories, file bytes and mtimes: no invisible mkdir dry-runs."""
    return {str(p.relative_to(root)): ("dir", p.stat().st_mtime_ns) if p.is_dir() else
            (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob("*")}


@pytest.fixture
def adapter(tmp_path, carrier_root):
    config = AdapterConfig(database=tmp_path / "application" / "data.sqlite",
                           transit=tmp_path / "transit", state=tmp_path / "local" / "state.json",
                           marker=tmp_path / "config" / "enabled", heartbeat=tmp_path / "local" / "heartbeat.json",
                           node_id="node-a", namespace="bach", required_schema=SCHEMA, user_version=7)
    config.database.parent.mkdir()
    source = Path(__file__).parent / "fixtures" / "k9_data" / "source.sql"
    with closing(sqlite3.connect(config.database)) as connection:
        connection.executescript(source.read_text(encoding="utf-8"))
        connection.execute("PRAGMA user_version=7")
        connection.commit()
    return DBSyncAdapter(config, carrier_root=carrier_root, clock=lambda: NOW)


def prepare(adapter):
    adapter.config.transit.mkdir(exist_ok=True)
    adapter.config.state.parent.mkdir(exist_ok=True)


def rows(database, table="secrets"):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(f'SELECT * FROM "{table}"').fetchall()


def seed_snapshots(adapter):
    """Use carrier push with a fixed test-only clock, never construct payloads."""
    prepare(adapter)
    module, config = adapter._carrier()
    result = {}
    for node in ("node-a", "node-b"):
        config.node_id = node
        engine = module.TransitSync(config)
        result[node] = []
        for day in (1, 2, 3):
            module._utc_token = lambda day=day: f"2020010{day}T000000000000Z"
            snapshot = engine.push()
            # Retention uses manifest creation time, not unrelated file mtime.
            os.utime(snapshot.path, (1893456000, 1893456000))
            result[node].append(snapshot)
    return result


@pytest.mark.parametrize("operation", ["backup", "status", "enable", "disable", "cleanup", "init"])
def test_all_six_dry_runs_preserve_all_files_and_directories(adapter, tmp_path, operation):
    prepare(adapter)
    before = inventory(tmp_path)
    result = adapter.handle(operation, scope="all-nodes")
    assert result.ok, result
    assert result.outcome == ("supported" if operation == "status" else "dry-run")
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("operation", ["backup", "enable", "disable", "init"])
def test_dry_run_does_not_prepare_missing_directories(adapter, tmp_path, operation):
    before = inventory(tmp_path)
    assert adapter.handle(operation).outcome == "dry-run"
    assert inventory(tmp_path) == before


def test_backup_delegates_redaction_and_records_heartbeat_only_after_publication(adapter, tmp_path):
    original = adapter.config.database.read_bytes()
    result = adapter.handle("backup", dry_run=False)
    assert result.outcome == "supported"
    snapshot = Path(result.data["snapshot"]["path"])
    assert rows(snapshot) == []
    assert len(rows(adapter.config.database)) == 1
    assert rows(snapshot, "items") == rows(adapter.config.database, "items")
    assert adapter.config.database.read_bytes() == original
    heartbeat = json.loads(adapter.config.heartbeat.read_text())
    assert heartbeat == {"node-a": {"last_seen": NOW.isoformat(), "pid": os.getpid(), "active": True}}
    status = adapter.handle("status")
    assert status.ok and len(status.data["verified_snapshots"]) == 1
    assert not list(tmp_path.rglob("*.tmp"))


def test_backup_preserves_foreign_heartbeat(adapter):
    prepare(adapter)
    foreign = {"node-b": {"last_seen": NOW.isoformat(), "pid": 42, "active": False, "extra": "preserved"}}
    adapter.config.heartbeat.write_text(json.dumps(foreign))
    assert adapter.handle("backup", dry_run=False).ok
    assert json.loads(adapter.config.heartbeat.read_text())["node-b"] == foreign["node-b"]


@pytest.mark.parametrize("operation", ["backup", "status"])
@pytest.mark.parametrize("payload", ["broken", "[]", '{"node-b": {}}',
                                    '{"node-b":{"last_seen":"2026-09-30T12:00:00","pid":1,"active":true}}'])
def test_malformed_heartbeat_fails_before_write(adapter, tmp_path, operation, payload):
    prepare(adapter)
    adapter.config.heartbeat.write_text(payload)
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=False)
    assert result.outcome == "refused" and result.code == "invalid-heartbeat"
    assert inventory(tmp_path) == before


def test_backup_heartbeat_failure_reports_the_already_published_snapshot(adapter, monkeypatch):
    def fail(*args):
        raise OSError("synthetic-private-payload")
    monkeypatch.setattr(adapter_module, "_atomic_bytes", fail)
    result = adapter.handle("backup", dry_run=False)
    assert result.outcome == "error" and not result.ok
    assert result.code == "snapshot-published-heartbeat-failed"
    assert Path(result.data["snapshot"]["path"]).exists()
    assert not adapter.config.heartbeat.exists()
    assert "synthetic-private-payload" not in repr(result)


def test_failed_carrier_backup_does_not_write_heartbeat(adapter, monkeypatch):
    engine = adapter._engine(create=True)
    def fail():
        raise RuntimeError("synthetic-private-payload")
    monkeypatch.setattr(engine, "push", fail)
    monkeypatch.setattr(adapter, "_engine", lambda **kwargs: engine)
    result = adapter.handle("backup", dry_run=False)
    assert result.code == "carrier-call-failed-state-unknown" and not result.ok
    assert not adapter.config.heartbeat.exists()
    assert not list(adapter.config.transit.iterdir())


def test_carrier_credential_scan_refusal_never_publishes_or_updates_heartbeat(adapter):
    synthetic = "-----BEGIN PRIVATE KEY-----"
    with closing(sqlite3.connect(adapter.config.database)) as connection:
        connection.execute("UPDATE items SET value=? WHERE id='shared'", (synthetic,))
        connection.commit()
    result = adapter.handle("backup", dry_run=False)
    assert not result.ok and result.code == "carrier-call-failed-state-unknown"
    assert not list(adapter.config.transit.iterdir()) and not adapter.config.heartbeat.exists()
    assert synthetic not in repr(result)


def test_status_returns_only_verified_metadata_and_never_changes_state(adapter, tmp_path):
    adapter.handle("backup", dry_run=False)
    before = inventory(tmp_path)
    result = adapter.handle("status", dry_run=False)
    assert result.ok and result.data["carrier"]["namespace"] == "bach"
    assert result.data["verified_snapshots"][0]["sha256"]
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("operation", ["status", "backup", "enable", "disable", "cleanup", "init"])
@pytest.mark.parametrize("payload", ["{", "[]", '{"protocol":true,"last_pulled":{}}',
                                    '{"protocol":1,"last_pulled":{"node-b":"invalid-time"}}'])
def test_corrupt_carrier_state_is_refused_without_reset_or_mutation(adapter, tmp_path, operation, payload):
    prepare(adapter)
    adapter.config.state.write_text(payload)
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=False, scope="all-nodes")
    assert result.code == "invalid-carrier-state" and not result.ok
    assert inventory(tmp_path) == before


def test_valid_carrier_state_is_preserved_by_all_read_operations(adapter, tmp_path):
    prepare(adapter)
    state = {"protocol": 1, "last_pulled": {"node-b": "20200101T000000000000Z"}}
    adapter.config.state.write_text(json.dumps(state))
    before = inventory(tmp_path)
    for operation in ("status", "init", "backup", "cleanup"):
        assert adapter.handle(operation, scope="all-nodes").ok
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("operation", ["status", "cleanup"])
def test_corrupt_snapshot_fails_without_changes(adapter, tmp_path, operation):
    snapshot = seed_snapshots(adapter)["node-a"][0]
    snapshot.path.write_bytes(b"corrupt")
    before = inventory(tmp_path)
    result = adapter.handle(operation, scope="all-nodes")
    assert not result.ok
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("operation", ["status", "cleanup"])
def test_snapshot_sidecars_are_refused_before_sqlite_verification(adapter, tmp_path, operation):
    snapshot = seed_snapshots(adapter)["node-a"][0]
    Path(str(snapshot.path) + "-wal").write_bytes(b"synthetic")
    before = inventory(tmp_path)
    result = adapter.handle(operation, scope="all-nodes")
    assert result.code == "snapshot-sidecars-refused"
    assert inventory(tmp_path) == before


def test_enable_and_disable_only_change_explicit_marker(adapter, tmp_path):
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("untouched")
    original = adapter.config.database.read_bytes()
    assert adapter.handle("enable", dry_run=False).ok
    assert adapter.config.marker.read_bytes() == b"enabled"
    before = inventory(tmp_path)
    assert adapter.handle("enable", dry_run=False).ok
    assert inventory(tmp_path) == before  # idempotence does not replace the marker
    assert adapter.handle("disable", dry_run=False).ok
    assert not adapter.config.marker.exists()
    before = inventory(tmp_path)
    assert adapter.handle("disable", dry_run=False).ok
    assert inventory(tmp_path) == before
    assert foreign.read_text() == "untouched" and adapter.config.database.read_bytes() == original
    assert not adapter.config.heartbeat.exists() and not adapter.config.transit.exists()


@pytest.mark.parametrize("operation", ["enable", "disable", "status"])
def test_foreign_marker_is_not_overwritten_or_removed(adapter, tmp_path, operation):
    prepare(adapter)
    adapter.config.marker.parent.mkdir()
    adapter.config.marker.write_bytes(b"foreign-content")
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=False)
    assert result.code == "foreign-marker-refused" and not result.ok
    assert inventory(tmp_path) == before


def test_atomic_marker_replace_failure_preserves_existing_files(adapter, monkeypatch):
    adapter.config.marker.parent.mkdir()
    foreign = adapter.config.marker.parent / "foreign"
    foreign.write_bytes(b"untouched")
    def fail(*args):
        raise OSError("synthetic")
    monkeypatch.setattr(adapter_module.os, "replace", fail)
    result = adapter.handle("enable", dry_run=False)
    assert result.outcome == "error"
    assert not adapter.config.marker.exists()
    assert foreign.read_bytes() == b"untouched" and not list(foreign.parent.glob("*.tmp"))


def test_post_publication_path_refusal_is_an_error_with_partial_state(adapter, monkeypatch):
    def fail(*args):
        raise AdapterRefusal("linked-path-refused")
    monkeypatch.setattr(adapter_module, "_atomic_bytes", fail)
    result = adapter.handle("backup", dry_run=False)
    assert result.outcome == "error" and result.code == "snapshot-published-heartbeat-failed"
    assert Path(result.data["snapshot"]["path"]).is_file()


def test_disable_failure_preserves_marker_and_reports_error(adapter, monkeypatch):
    assert adapter.handle("enable", dry_run=False).ok
    real_unlink = Path.unlink
    def fail_marker(path, *args, **kwargs):
        if path == adapter.config.marker:
            raise PermissionError("synthetic")
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_marker)
    result = adapter.handle("disable", dry_run=False)
    assert result.outcome == "error" and adapter.config.marker.read_bytes() == b"enabled"


@pytest.mark.parametrize("scope", [None, "auto", "all", True])
def test_cleanup_never_infers_scope(adapter, tmp_path, scope):
    before = inventory(tmp_path)
    result = adapter.handle("cleanup", dry_run=False, scope=scope)
    assert result.code == "explicit-cleanup-scope-required"
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("scope,remaining", [("local-node", 4), ("all-nodes", 2)])
def test_cleanup_honors_explicit_scope_retention_and_preview(adapter, tmp_path, scope, remaining):
    snapshots = seed_snapshots(adapter)
    before = inventory(tmp_path)
    preview = adapter.handle("cleanup", scope=scope, keep_days=7, keep_per_node=1)
    assert preview.ok and preview.data["scope"] == scope and preview.data["deleted"] == []
    assert len(preview.data["eligible"]) == (2 if scope == "local-node" else 4)
    assert inventory(tmp_path) == before
    result = adapter.handle("cleanup", dry_run=False, scope=scope, keep_days=7, keep_per_node=1)
    assert result.ok and len(result.data["deleted"]) == len(preview.data["eligible"])
    assert len(list(adapter.config.transit.glob("*.sqlite-snapshot"))) == remaining
    assert len(list(adapter.config.transit.glob("*.json"))) == remaining
    assert snapshots["node-a"][-1].path.exists() and snapshots["node-b"][-1].path.exists()


def test_local_cleanup_does_not_verify_or_remove_foreign_corrupt_payload(adapter):
    snapshots = seed_snapshots(adapter)
    snapshots["node-b"][0].path.write_bytes(b"foreign-corrupt")
    result = adapter.handle("cleanup", dry_run=False, scope="local-node", keep_per_node=1)
    assert result.ok
    assert snapshots["node-b"][0].path.read_bytes() == b"foreign-corrupt"


def test_cleanup_apply_failure_is_not_claimed_as_rollback(adapter, monkeypatch):
    seed_snapshots(adapter)
    engine = adapter._engine()
    real_cleanup = engine.cleanup
    def partial(**kwargs):
        real_cleanup(**kwargs)
        raise OSError("synthetic-private-payload")
    monkeypatch.setattr(engine, "cleanup", partial)
    monkeypatch.setattr(adapter, "_engine", lambda **kwargs: engine)
    result = adapter.handle("cleanup", dry_run=False, scope="all-nodes", keep_per_node=1)
    assert result.outcome == "error" and result.code == "carrier-call-failed-state-unknown"
    assert len(list(adapter.config.transit.glob("*.sqlite-snapshot"))) == 2
    assert "synthetic-private-payload" not in repr(result)


def test_cleanup_does_not_claim_missing_directory_is_initialized(adapter, tmp_path):
    before = inventory(tmp_path)
    result = adapter.handle("cleanup", scope="local-node")
    assert result.code == "carrier-directories-not-prepared"
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("value", [-1, True, 1.5, "7"])
def test_cleanup_rejects_invalid_retention(adapter, value):
    assert adapter.handle("cleanup", scope="local-node", keep_days=value).code == "invalid-retention"


def test_init_validates_existing_schema_without_copy_or_migration(adapter, tmp_path):
    before = inventory(tmp_path)
    result = adapter.handle("init", dry_run=False)
    assert result.ok and result.data == {"validated_user_version": 7, "created_database": False}
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("fault,code", [("missing", "application-database-missing"),
                                       ("stale", "application-schema-version-mismatch"),
                                       ("wrong-schema", "application-schema-mismatch"),
                                       ("sidecar", "database-sidecars-refused")])
@pytest.mark.parametrize("operation", ["init", "backup"])
def test_missing_stale_or_invalid_application_database_is_refused(adapter, tmp_path, fault, code, operation):
    if fault == "missing":
        adapter.config.database.unlink()
    elif fault == "sidecar":
        Path(str(adapter.config.database) + "-wal").write_bytes(b"synthetic")
    else:
        with closing(sqlite3.connect(adapter.config.database)) as connection:
            connection.execute("PRAGMA user_version=6" if fault == "stale" else "DROP TABLE items")
            connection.commit()
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=False)
    assert result.outcome == "refused" and result.code == code
    assert inventory(tmp_path) == before


def test_missing_init_does_not_copy_a_stale_sibling_database(adapter, tmp_path):
    sibling = tmp_path / "stale-source.sqlite"
    shutil.copyfile(adapter.config.database, sibling)
    adapter.config.database.unlink()
    before = inventory(tmp_path)
    assert adapter.handle("init", dry_run=False).code == "application-database-missing"
    assert inventory(tmp_path) == before


def test_pin_drift_is_refused_before_any_write(adapter, tmp_path):
    root = tmp_path / "modified-provider"
    package = root / "sqlite_transit_sync"
    package.mkdir(parents=True)
    for name in adapter_module.CARRIER_HASHES:
        shutil.copyfile(adapter.carrier_root / "sqlite_transit_sync" / name, package / name)
    with (package / "core.py").open("ab") as handle:
        handle.write(b"\nraise RuntimeError('must not execute')\n")
    adapter.carrier_root = root
    before = inventory(tmp_path)
    assert adapter.handle("enable", dry_run=False).code == "carrier-pin-mismatch"
    assert inventory(tmp_path) == before


def test_credential_trigger_pin_drift_is_refused(adapter, tmp_path):
    root = tmp_path / "modified-provider"
    package = root / "sqlite_transit_sync"
    package.mkdir(parents=True)
    for name in adapter_module.CARRIER_HASHES:
        shutil.copyfile(adapter.carrier_root / "sqlite_transit_sync" / name, package / name)
    (package / "credential-triggers.json").write_bytes(b'{"patterns": []}')
    adapter.carrier_root = root
    assert adapter.handle("backup", dry_run=False).code == "carrier-pin-mismatch"


def test_pinned_provider_is_unchanged_and_receives_no_bytecode(adapter):
    before = inventory(adapter.carrier_root / "sqlite_transit_sync")
    assert adapter.handle("backup", dry_run=False).ok
    assert adapter.handle("status").ok
    assert inventory(adapter.carrier_root / "sqlite_transit_sync") == before


def test_all_six_use_no_home_network_or_subprocess_defaults(adapter, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("home/network/process access is forbidden in adapter conformance")
    monkeypatch.setattr(Path, "home", forbidden)
    monkeypatch.setattr(socket, "gethostname", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setenv("SQLITE_TRANSIT_SYNC_KEY_FILE", "must-not-be-used")
    assert adapter.handle("backup", dry_run=False).ok
    for operation in ("init", "status", "enable", "disable", "cleanup"):
        result = adapter.handle(operation, dry_run=False, scope="local-node")
        assert result.ok, result
    _, config = adapter._carrier()
    assert config.key_file == adapter.config.state.parent / "unused-republica.key"
    assert config.republica_root == adapter.config.state.parent / "unused-republica"


def test_symlink_marker_is_refused_without_touching_foreign_target(adapter, tmp_path):
    adapter.config.marker.parent.mkdir()
    foreign = tmp_path / "foreign.txt"
    foreign.write_bytes(b"enabled")
    try:
        adapter.config.marker.symlink_to(foreign)
    except OSError as error:
        pytest.skip(f"native symlink creation unavailable: {type(error).__name__}")
    result = adapter.handle("disable", dry_run=False)
    assert result.code == "linked-path-refused" and foreign.read_bytes() == b"enabled"
    assert adapter.config.marker.is_symlink()


def test_symlink_snapshot_is_refused_before_provider_sqlite_open(adapter, tmp_path):
    snapshot = seed_snapshots(adapter)["node-a"][0]
    foreign = tmp_path / "foreign.sqlite"
    shutil.copyfile(snapshot.path, foreign)
    snapshot.path.unlink()
    try:
        snapshot.path.symlink_to(foreign)
    except OSError as error:
        pytest.skip(f"native symlink creation unavailable: {type(error).__name__}")
    result = adapter.handle("status")
    assert result.code == "linked-path-refused" and snapshot.path.is_symlink()


def test_config_rejects_missing_version_relative_or_overlapping_paths(adapter):
    for config in (replace(adapter.config, user_version=0),
                   replace(adapter.config, marker=Path("relative")),
                   replace(adapter.config, heartbeat=adapter.config.marker),
                   replace(adapter.config, marker=adapter.config.transit / "marker")):
        with pytest.raises(AdapterRefusal):
            DBSyncAdapter(config, carrier_root=adapter.carrier_root, clock=lambda: NOW)


def test_timezone_naive_clock_refuses_backup_before_publication(adapter, tmp_path):
    adapter.clock = lambda: datetime(2026, 9, 30)
    before = inventory(tmp_path)
    assert adapter.handle("backup", dry_run=False).code == "timezone-aware-clock-required"
    assert inventory(tmp_path) == before


def test_secret_table_case_drift_is_refused(adapter):
    with closing(sqlite3.connect(adapter.config.database)) as connection:
        connection.execute('ALTER TABLE secrets RENAME TO "SecretsRenamed"')
        connection.execute('ALTER TABLE SecretsRenamed RENAME TO "Secrets"')
        connection.commit()
    config = replace(adapter.config, required_schema={"items": SCHEMA["items"]})
    checked = DBSyncAdapter(config, carrier_root=adapter.carrier_root, clock=lambda: NOW)
    assert checked.handle("backup", dry_run=False).code == "secret-table-case-not-supported"


def test_local_adapter_does_not_claim_unsupported_push_pull_sync(adapter):
    for operation in ("push", "pull", "sync", "unknown"):
        assert adapter.handle(operation).code == "operation-outside-local-scope"


def test_parity_register_preserves_the_three_existing_evidenced_operations():
    evidence = json.loads((Path(__file__).parents[1] / "architecture" / "bach-parity-evidence.v1.json").read_text())
    covered = {operation for case in evidence["rows"]["dbsync"]["use_cases"]
               if case["state"] == "evidenced" for operation in case["operations"]}
    assert covered == {"push", "pull", "sync"}


@pytest.mark.parametrize("storage", ["STORED", "VIRTUAL"])
@pytest.mark.parametrize("table", ["items", "extra_note"])
@pytest.mark.parametrize("operation", ["init", "backup"])
@pytest.mark.parametrize("dry_run", [True, False])
def test_generated_columns_in_any_table_are_refused_before_publication(adapter, tmp_path, storage, table, operation, dry_run):
    with closing(sqlite3.connect(adapter.config.database)) as connection:
        if table == "items":
            connection.execute("DROP TABLE items")
        connection.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY, value TEXT, updated_at TEXT, tail TEXT, "
                           f"private_note TEXT GENERATED ALWAYS AS (value || tail) {storage})")
        connection.execute(f"INSERT INTO {table}(id,value,updated_at,tail) VALUES "
                           "('synthetic','-----BEGIN ','2026-09-30','PRIVATE KEY-----')")
        assert connection.execute(f"SELECT private_note FROM {table}").fetchone()[0] == "-----BEGIN PRIVATE KEY-----"
        connection.commit()
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=dry_run)
    assert result.outcome == "refused" and result.code == "unsupported-table-columns"
    assert inventory(tmp_path) == before
    assert not adapter.config.transit.exists() and not adapter.config.heartbeat.exists()


@pytest.mark.parametrize("module", ["fts5(value)", "rtree(id,x_min,x_max)"])
@pytest.mark.parametrize("operation", ["init", "backup"])
def test_virtual_and_hidden_table_forms_are_refused(adapter, tmp_path, module, operation):
    with closing(sqlite3.connect(adapter.config.database)) as connection:
        connection.execute(f"CREATE VIRTUAL TABLE extra_surface USING {module}")
        connection.commit()
    before = inventory(tmp_path)
    result = adapter.handle(operation, dry_run=False)
    assert result.outcome == "refused"
    assert result.code in {"unsupported-table-columns", "unsupported-table-kind"}
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("operation", ["init", "backup"])
@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecars_with_glob_metacharacters_in_db_name_are_literal_and_refused_before_open(adapter, tmp_path, monkeypatch, operation, dry_run, suffix):
    name = adapter.config.database.with_name("data[1].sqlite")
    adapter.config.database.rename(name)
    checked = DBSyncAdapter(replace(adapter.config, database=name), carrier_root=adapter.carrier_root, clock=lambda: NOW)
    Path(str(name) + suffix).write_bytes(b"synthetic-sidecar")
    before = inventory(tmp_path)
    def forbidden_open(*args, **kwargs):
        raise AssertionError("database/carrier must not open before sidecar refusal")
    monkeypatch.setattr(sqlite3, "connect", forbidden_open)
    monkeypatch.setattr(checked, "_engine", forbidden_open)
    result = checked.handle(operation, dry_run=dry_run)
    assert result.outcome == "refused" and result.code == "database-sidecars-refused"
    assert inventory(tmp_path) == before
