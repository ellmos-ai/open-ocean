"""Read-only host observations. A snapshot is never permission to start work."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time


@dataclass(frozen=True)
class HostObservation:
    host_id: str
    platform: str
    observed_at: float  # UTC Unix seconds; comparable across hosts, unlike monotonic uptime.
    total_ram_bytes: int | None
    available_ram_bytes: int | None
    logical_cpus: int | None
    load_average_1m: float | None
    pressure: str
    disk_free_bytes: int | None
    measurement_source: str
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "mode": "read-only-observation",
            "start_authorized": False,
            "cpu_load_is_admission_capacity": False,
        }


def _command(argv: list[str]) -> str:
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env={**os.environ, "LC_ALL": "C"},
    )
    if result.returncode:
        raise ValueError("native probe failed")
    return result.stdout


def parse_macos_vm(text: str) -> int:
    """Conservative readily reclaimable estimate; never counts compressed pages."""
    match = re.search(r"page size of (\d+) bytes", text)
    if not match:
        raise ValueError("unknown vm_stat page size")
    page_size = int(match[1])
    if page_size not in {4096, 16384, 65536}:
        raise ValueError("unsupported page size")
    pages = []
    for label in ("Pages free", "Pages inactive", "Pages speculative"):
        item = re.search(r"^" + label + r":\s+(\d+)\.?\s*$", text, re.MULTILINE)
        if not item:
            raise ValueError("incomplete vm_stat")
        pages.append(int(item[1]))
    return sum(pages) * page_size


def _windows_memory() -> tuple[int, int]:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            *[
                (name, ctypes.c_ulonglong)
                for name in (
                    "total",
                    "available",
                    "total_page",
                    "available_page",
                    "total_virtual",
                    "available_virtual",
                    "extended",
                )
            ],
        ]

    value = MemoryStatus()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(value.total), int(value.available)


def sample_host(directory: Path | None = None) -> HostObservation:
    """No writes, networking, model API, queue discovery or service manipulation."""
    system = platform.system()
    total = available = disk = load = None
    pressure = "unknown"
    errors = []
    source = "unsupported"
    try:
        if system == "Windows":
            total, available = _windows_memory()
            if total <= 0:
                raise ValueError("invalid physical memory size")
            source = "GlobalMemoryStatusEx"
            # Ratio is a conservative observation, not a native pressure signal.
            pressure = "normal" if available / total >= 0.20 else "elevated"
        elif system == "Darwin":
            total = int(_command(["/usr/sbin/sysctl", "-n", "hw.memsize"]).strip())
            available = parse_macos_vm(_command(["/usr/bin/vm_stat"]))
            level = int(_command(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip())
            pressure = {1: "normal", 2: "elevated", 4: "critical"}.get(level, "unknown")
            source = "vm_stat free+inactive+speculative; sysctl pressure"
        elif system == "Linux":
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                match = re.fullmatch(r"(MemTotal|MemAvailable):\s+(\d+) kB", line)
                if match:
                    values[match[1]] = int(match[2]) * 1024
            total, available = values["MemTotal"], values["MemAvailable"]
            if total <= 0:
                raise ValueError("invalid physical memory size")
            pressure = "normal" if available / total >= 0.20 else "elevated"
            source = "/proc/meminfo; available ratio (not PSI)"
        else:
            errors.append("unsupported-platform")
        if total is not None and not (0 <= available <= total and total > 0):
            raise ValueError("inconsistent memory probe")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        errors.append("memory-probe-unavailable")
        total = available = None
        pressure = "unknown"
    try:
        disk = shutil.disk_usage(directory if directory is not None else Path.home()).free
    except OSError:
        errors.append("disk-probe-unavailable")
    if hasattr(os, "getloadavg"):
        try:
            load = os.getloadavg()[0]
        except OSError:
            errors.append("load-probe-unavailable")
    return HostObservation(
        platform.node(),
        system,
        time.time(),
        total,
        available,
        os.cpu_count(),
        load,
        pressure,
        disk,
        source,
        tuple(errors),
    )
