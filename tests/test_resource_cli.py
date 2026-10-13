"""Offline CLI and installed manifest contracts."""
from pathlib import Path
import json
import os
import subprocess
import sys

from ocean_resources.__main__ import fixture_demo, manifest


def test_default_cli_manifest_is_read_only_from_an_empty_cwd(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-m", "ocean_resources"], cwd=tmp_path,
                            env=env, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == manifest()
    assert list(tmp_path.iterdir()) == []


def test_fixture_demo_explicitly_labels_synthetic_capacity_and_resumes():
    result = fixture_demo()
    assert result["mode"] == "synthetic-fixture-only"
    assert result["host_ram_measurement"] == "not-performed-synthetic-capacity"
    assert result["models_started"] == result["live_queue_writes"] == 0
    assert result["starts"] == [
        {"request_id": "compute-job", "resumed_progress": 0},
        {"request_id": "chat", "resumed_progress": 0},
        {"request_id": "compute-job", "resumed_progress": 7},
    ]
    assert result["result_progress"] == 14
    assert result["final"]["torch"] is None and result["final"]["waiting"] == []


def test_no_live_cli_command_exists():
    result = subprocess.run([sys.executable, "-m", "ocean_resources", "start-model"],
                            capture_output=True, text=True)
    assert result.returncode == 2


def test_manifest_keeps_task_union_and_polarstern_boundaries_explicit():
    record = manifest()
    assert record["task_union_status"] == "union-schema-specified-fixtures-green-no-live-cutover"
    assert record["state"]["polarstern"] == "separate and unchanged"
    assert "fixture" in record["admission"]["mode"]
    assert record["decision"]["pipeline_count"] == "unresolved-no-new-pipeline"
