"""Real host observation boundaries and the POSIX single-writer regression."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ocean_resources import HostObservation, HostWriterAuthority, sample_host
from ocean_resources.host import parse_macos_vm


def test_macos_parser_counts_reclaimable_pages_without_compressor_double_counting():
    text = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free: 10.
Pages inactive: 20.
Pages speculative: 30.
Pages wired down: 800.
Pages stored in compressor: 999999.
"""
    assert parse_macos_vm(text) == 60 * 16384


@pytest.mark.parametrize("text", ["", "page size of 3 bytes", "page size of 16384 bytes\nPages free: 1."])
def test_incomplete_macos_probe_never_creates_capacity(text):
    with pytest.raises(ValueError):
        parse_macos_vm(text)


def test_native_host_observation_is_not_an_admission(tmp_path):
    before = list(tmp_path.iterdir())
    reading = sample_host(tmp_path)
    assert reading.host_id
    if reading.available_ram_bytes is not None:
        assert 0 <= reading.available_ram_bytes <= reading.total_ram_bytes
    assert reading.disk_free_bytes > 0
    assert reading.to_dict()["start_authorized"] is False
    assert reading.to_dict()["cpu_load_is_admission_capacity"] is False
    assert list(tmp_path.iterdir()) == before


def test_probe_failure_stays_unknown(monkeypatch, tmp_path):
    import ocean_resources.host as host

    monkeypatch.setattr(host.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(host, "_command", lambda args: (_ for _ in ()).throw(ValueError("probe unavailable")))
    reading = host.sample_host(tmp_path)
    assert reading.available_ram_bytes is None
    assert reading.pressure == "unknown"
    assert reading.errors == ("memory-probe-unavailable",)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork descriptor semantics")
def test_fork_child_close_cannot_unlock_parent_writer(tmp_path):
    root = str(Path(__file__).resolve().parents[1])
    probe = """from pathlib import Path
import sys
from ocean_resources import HostWriterAuthority, Hold
try:
    with HostWriterAuthority(Path(sys.argv[1]), "test-host"):
        print("ACQUIRED")
except Hold:
    print("BLOCKED")
"""

    def probe_writer():
        result = subprocess.run(
            [sys.executable, "-c", probe, str(tmp_path)], cwd=root, capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    with HostWriterAuthority(tmp_path.resolve(), "test-host") as writer:
        assert probe_writer() == "BLOCKED"
        pid = os.fork()
        if pid == 0:
            try:
                writer.__exit__()
                os._exit(0)
            except BaseException:
                os._exit(1)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        writer.require()
        assert probe_writer() == "BLOCKED"
    assert probe_writer() == "ACQUIRED"


def test_host_cli_is_json_and_does_not_write_in_empty_cwd(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "ocean_resources", "host"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["start_authorized"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_at": float("nan")},
        {"observed_at": True},
        {"available_ram_bytes": float("nan")},
        {"available_ram_bytes": True},
        {"available_ram_bytes": -1},
        {"available_ram_bytes": 2001},
        {"total_ram_bytes": None},
        {"total_ram_bytes": 0},
        {"disk_free_bytes": float("inf")},
        {"disk_free_bytes": -1},
        {"logical_cpus": True},
        {"load_average_1m": float("nan")},
        {"pressure": "ready"},
        {"host_id": "../host"},
    ],
)
def test_remote_or_constructed_invalid_reading_cannot_look_ready(changes):
    values = dict(
        host_id="test-host",
        platform="Linux",
        observed_at=100,
        total_ram_bytes=2000,
        available_ram_bytes=1000,
        logical_cpus=4,
        load_average_1m=None,
        pressure="normal",
        disk_free_bytes=1000,
        measurement_source="test-probe",
    )
    with pytest.raises(ValueError):
        HostObservation(**{**values, **changes})
