"""Required isolated K9 observations; no whole-operation parity promotion.

Set OCEAN_K9_SOURCE_MANIFEST to the complete pinned closure.
OCEAN_REQUIRE_K9_REMAINING=1 makes missing sources a failure rather than a skip.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.parity_probes import bach_k9_dbsync_remaining_probe as probe


@pytest.fixture
def source_manifest():
    value = os.environ.get("OCEAN_K9_SOURCE_MANIFEST")
    if not value or not Path(value).is_file():
        if os.environ.get("OCEAN_REQUIRE_K9_REMAINING") == "1":
            pytest.fail("required pinned K9 source closure is unavailable")
        pytest.skip("no pinned source closure; this is not K9 acceptance")
    return Path(value)


def observe(tmp_path, manifest, *, mode, operation, profile="minimal7",
            scenario="prepared", apply=False, scope=None, keep_per_node=10):
    work = tmp_path / "work"
    work.mkdir()
    receipt = work / "receipt.json"
    args = [sys.executable, str(Path(probe.__file__).resolve()), "--manifest", str(manifest),
            "--workdir", str(work), "--receipt", str(receipt), "--mode", mode,
            "--operation", operation, "--profile", profile, "--scenario", scenario]
    args += ["--keep-per-node", str(keep_per_node)]
    if apply:
        args.append("--apply")
    if scope:
        args += ["--scope", scope]
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               HOME=str(tmp_path / "uncreated-home"),
               USERPROFILE=str(tmp_path / "uncreated-home"))
    completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                               env=env, shell=False, stdin=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                               timeout=90)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    result = json.loads(receipt.read_text(encoding="utf-8"))
    assert result["parity_accepted"] is False
    assert result["host_or_runtime_acceptance"] is False
    assert result["mode"] == mode and result["operation"] == operation
    assert result["boundary_violations"] == []
    assert not (tmp_path / "uncreated-home").exists()
    return result


@pytest.mark.parametrize("mode", probe.MODES)
@pytest.mark.parametrize("operation", probe.OPERATIONS)
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
@pytest.mark.parametrize("profile", ["minimal7", "native0"])
def test_actual_four_arm_operation(tmp_path, source_manifest, mode, operation, apply, profile):
    result = observe(tmp_path, source_manifest, mode=mode, operation=operation,
                     apply=apply, profile=profile,
                     scope="local-node" if operation == "cleanup" else None)
    assert result["before_database"]["counts"]["secrets"] == 1
    assert result["after_database"] == result["before_database"]
    if mode in {"current-shared", "ocean"}:
        assert result["native_constructors"] == []
        if profile == "native0":
            assert result["raw"]["ok"] is False  # actual positive-schema0 gap remains
        elif operation in {"enable", "disable", "init", "backup", "status", "cleanup"}:
            assert result["raw"]["ok"] is True
        if not apply or operation in {"status", "init"}:
            assert result["before"] == result["after"]
    elif mode == "current-native":
        assert len(result["native_constructors"]) == 1
        if profile == "minimal7" and operation not in {"status", "disable"}:
            assert result["raw"]["ok"] is False  # native readiness does not accept fixture7
        if not apply or operation in {"status", "init"}:
            assert result["before"] == result["after"]
    else:
        assert len(result["native_constructors"]) == 1
        # Historical preview/constructor writes are observations, not normalised away.
    if apply and operation == "backup" and result["raw"]["ok"]:
        assert result["snapshots"]
        assert all(item["counts"]["secrets"] == 0 for item in result["snapshots"].values())


@pytest.mark.parametrize("mode", probe.MODES)
@pytest.mark.parametrize("operation", ["status", "init"])
def test_missing_directories_measured_before_construction(tmp_path, source_manifest, mode, operation):
    result = observe(tmp_path, source_manifest, mode=mode, operation=operation, scenario="missing")
    assert result["before"] == {}
    assert result["before_database"] == {"exists": False}
    if mode == "historical-native":
        assert result["file_effects"]["created"]  # real old constructor effect
    else:
        assert result["after"] == {}
        assert result["after_database"] == {"exists": False}


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
@pytest.mark.parametrize("operation", ["enable", "disable"])
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
def test_foreign_marker_is_refused_without_changes(tmp_path, source_manifest, mode, operation, apply):
    result = observe(tmp_path, source_manifest, mode=mode, operation=operation,
                     scenario="foreign-marker", apply=apply)
    assert result["raw"]["ok"] is False
    assert result["before"] == result["after"]


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
@pytest.mark.parametrize("scenario", ["corrupt-state", "corrupt-heartbeat", "sidecar"])
def test_untrusted_backup_inputs_preserve_originals(tmp_path, source_manifest, mode, scenario):
    result = observe(tmp_path, source_manifest, mode=mode, operation="backup",
                     scenario=scenario, apply=True)
    assert result["raw"]["ok"] is False
    assert result["before"] == result["after"]


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
def test_cleanup_requires_explicit_scope(tmp_path, source_manifest, mode):
    result = observe(tmp_path, source_manifest, mode=mode, operation="cleanup", apply=True)
    assert result["raw"]["ok"] is False
    assert result["before"] == result["after"]


@pytest.mark.parametrize("scope", ["local-node", "all-nodes"])
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
def test_actual_cleanup_retention_and_node_scope(tmp_path, source_manifest, scope, apply):
    result = observe(tmp_path, source_manifest, mode="ocean", operation="cleanup",
                     scenario="snapshot-pairs", apply=apply, scope=scope, keep_per_node=0)
    assert result["raw"]["ok"] is True
    removed = result["file_effects"]["removed"]
    if not apply:
        assert result["before"] == result["after"]
    else:
        assert "transit/bach__node-a__20000101T000000000000Z.sqlite-snapshot" in removed
        foreign = "transit/bach__node-b__20000101T000000000000Z.sqlite-snapshot"
        assert (foreign in removed) == (scope == "all-nodes")
        assert all("2999" not in name for name in removed)
        assert all(not name.endswith(".bachdb") for name in removed)


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
def test_corrupt_snapshot_cannot_be_cleaned(tmp_path, source_manifest, mode):
    result = observe(tmp_path, source_manifest, mode=mode, operation="cleanup",
                     scenario="corrupt-snapshot", apply=True, scope="all-nodes")
    assert result["raw"]["ok"] is False
    assert result["before"] == result["after"]


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
@pytest.mark.parametrize("operation", ["backup", "init"])
def test_actual_fts_shape_is_not_fixture7_acceptance(tmp_path, source_manifest, mode, operation):
    result = observe(tmp_path, source_manifest, mode=mode, operation=operation,
                     profile="native7-fts", apply=True)
    assert result["raw"]["ok"] is False
    assert result["before"] == result["after"]


def test_pinned_closure_cannot_be_replaced(tmp_path, source_manifest):
    value = json.loads(source_manifest.read_text(encoding="utf-8"))
    value["sources"]["ocean"]["commit"] = "0" * 40
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(probe.ProbeRefusal, match="source-commit-mismatch"):
        probe.sources(changed)


def test_explicit_selection_refuses_unknown_input_before_source_or_fixture(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(probe.ProbeRefusal, match="unknown-explicit-selection"):
        probe.run(mode="silent-default", operation="backup", manifest=tmp_path / "absent",
                  work=work)
    assert list(work.iterdir()) == []


@pytest.mark.parametrize("mode", probe.MODES)
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
def test_actual_stale_first_copy_is_not_normalised(tmp_path, source_manifest, mode, apply):
    result = observe(tmp_path, source_manifest, mode=mode, operation="init",
                     scenario="stale-copy", apply=apply)
    assert result["before_database"] == {"exists": False}
    source = "system/data/bach.db"
    assert result["before"][source] == result["after"][source]
    if mode == "historical-native":
        # Original code ignores dry_run here: preserve the actual historical copy.
        assert result["raw"]["ok"] is True
        assert result["after_database"]["exists"] is True
        assert result["after_database"]["counts"]["secrets"] == 1
        assert result["after"]["local/bach.db"]["sha256"] == result["before"][source]["sha256"]
        assert "local/bach.db" in result["file_effects"]["created"]
    else:
        assert result["raw"]["ok"] is False
        assert result["after_database"] == {"exists": False}
        assert result["before"] == result["after"]


@pytest.mark.parametrize("mode", ["current-shared", "ocean"])
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
def test_owned_enabled_marker_disable_is_explicit(tmp_path, source_manifest, mode, apply):
    result = observe(tmp_path, source_manifest, mode=mode, operation="disable",
                     scenario="enabled-marker", apply=apply)
    assert result["raw"]["ok"] is True
    assert result["after_database"] == result["before_database"]
    marker = "system/data/config/db_sync_enabled"
    if apply:
        assert marker in result["file_effects"]["removed"]
        assert marker not in result["after"]
    else:
        assert result["before"] == result["after"]


@pytest.mark.parametrize("profile", ["minimal7", "native0"])
def test_identical_initial_images_across_all_four_source_arms(tmp_path, source_manifest, profile):
    results = []
    for mode in probe.MODES:
        parent = tmp_path / mode
        parent.mkdir()
        results.append(observe(parent, source_manifest, mode=mode, operation="status", profile=profile))
    first = results[0]
    for result in results[1:]:
        assert result["before"] == first["before"]
        assert result["before_database"] == first["before_database"]
