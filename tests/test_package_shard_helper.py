import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "pytest_package_shard.py"
SPEC = importlib.util.spec_from_file_location("pytest_package_shard", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
shard_helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shard_helper)


def _binding(python_full_version):
    return {
        "run_id": "42",
        "run_attempt": 1,
        "commit": "abc123",
        "github_sha": "abc123",
        "os": "macos-latest",
        "os_system": "Darwin",
        "python_version": "3.13",
        "python_full_version": python_full_version,
        "pytest_version": "8.3.5",
        "module_sha256": "module-hash",
        "pyproject_sha256": "project-hash",
    }


def test_shard_plan_allows_patch_release_drift_but_requires_same_minor(monkeypatch, tmp_path):
    nodeids = [f"tests/test_python_packages.py::test_case_{index}" for index in range(6)]
    planned_binding = _binding("3.13.16")
    plan = {
        "schema_version": shard_helper.SCHEMA_VERSION,
        **planned_binding,
        "module": shard_helper.MODULE.as_posix(),
        "shard_count": shard_helper.SHARD_COUNT,
        "nodeids": nodeids,
        "shards": shard_helper._partition(nodeids),
    }
    path = tmp_path / "package-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(shard_helper, "_binding", lambda _os, _python: _binding("3.13.15"))
    monkeypatch.setattr(shard_helper, "_collect_nodeids", lambda: nodeids)
    monkeypatch.setattr(shard_helper.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    args = argparse.Namespace(plan=str(path), os="macos-latest", python_version="3.13", shard=0)

    assert shard_helper._run_shard(args) == 0

    monkeypatch.setattr(shard_helper, "_binding", lambda _os, _python: {**_binding("3.13.15"), "python_version": "3.12"})
    with pytest.raises(SystemExit):
        shard_helper._run_shard(args)
