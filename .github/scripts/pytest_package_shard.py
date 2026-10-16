"""Create and execute fail-closed, cell-bound package-test shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = Path("tests/test_python_packages.py")
PYPROJECT = Path("pyproject.toml")
SHARD_COUNT = 6
SCHEMA_VERSION = 1
EXPECTED_SYSTEMS = {
    "ubuntu-latest": "Linux",
    "windows-latest": "Windows",
    "macos-latest": "Darwin",
}
BOUND_FIELDS = (
    "run_id",
    "run_attempt",
    "commit",
    "github_sha",
    "os",
    "os_system",
    "python_version",
    "pytest_version",
    "module_sha256",
    "pyproject_sha256",
)


def _fail(message: str) -> None:
    print(f"package shard error: {message}", file=sys.stderr)
    raise SystemExit(2)


class _NodeIdCollector:
    def __init__(self) -> None:
        self.nodeids: list[str] = []

    def pytest_collection_finish(self, session: object) -> None:
        self.nodeids = [item.nodeid for item in session.items]  # type: ignore[attr-defined]


def _collect_command(output: Path) -> int:
    import pytest

    collector = _NodeIdCollector()
    result = pytest.main(
        [
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "--collect-only",
            "-q",
            MODULE.as_posix(),
        ],
        plugins=[collector],
    )
    if result != pytest.ExitCode.OK:
        print(f"package shard error: pytest collection exited with {int(result)}", file=sys.stderr)
        return int(result)
    if not collector.nodeids:
        print("package shard error: collection returned no test IDs", file=sys.stderr)
        return 2
    output.write_text(json.dumps(collector.nodeids, ensure_ascii=False), encoding="utf-8")
    return 0


def _collect_nodeids() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="ocean-package-collect-") as temporary:
        output = Path(temporary) / "nodeids.json"
        command = [sys.executable, str(Path(__file__).resolve()), "_collect", "--output", str(output)]
        result = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            _fail(f"complete module collection failed with exit code {result.returncode}")
        try:
            nodeids = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"could not read collected test IDs: {exc}")
        if not isinstance(nodeids, list) or any(not isinstance(nodeid, str) for nodeid in nodeids):
            _fail("collection output is not a list of test IDs")
        if not nodeids:
            _fail("collection returned no test IDs")
        if len(nodeids) != len(set(nodeids)):
            _fail("collection returned duplicate test IDs")
        if any(not nodeid.startswith(f"{MODULE.as_posix()}::") for nodeid in nodeids):
            _fail("collection returned an ID outside the package test module")
        return sorted(nodeids)


def _partition(nodeids: list[str]) -> list[list[str]]:
    if len(nodeids) < SHARD_COUNT:
        _fail(f"cannot create {SHARD_COUNT} non-empty shards from {len(nodeids)} IDs")
    shards = [nodeids[index::SHARD_COUNT] for index in range(SHARD_COUNT)]
    flattened = [nodeid for shard in shards for nodeid in shard]
    if any(not shard for shard in shards):
        _fail("partition contains an empty shard")
    if len(flattened) != len(set(flattened)) or sorted(flattened) != nodeids:
        _fail("partition is not a disjoint, complete union of the collected IDs")
    return shards


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail(f"could not identify the checked-out commit: {result.stderr.strip()}")
    return result.stdout.strip().lower()


def _binding(expected_os: str, expected_python: str) -> dict[str, str | int]:
    import pytest

    expected_system = EXPECTED_SYSTEMS.get(expected_os)
    if expected_system is None:
        _fail(f"unsupported runner OS label: {expected_os}")
    actual_system = platform.system()
    if actual_system != expected_system:
        _fail(f"runner OS is {actual_system}, expected {expected_system} for {expected_os}")
    actual_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if actual_python != expected_python:
        _fail(f"Python is {actual_python}, expected matrix version {expected_python}")

    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    github_sha = os.environ.get("GITHUB_SHA", "").lower()
    if not run_id.isdecimal() or not run_attempt.isdecimal() or not github_sha:
        _fail("GitHub run ID, attempt, and SHA are required")
    commit = _git_head()
    if commit != github_sha:
        _fail(f"checked-out commit {commit} does not match GITHUB_SHA {github_sha}")

    return {
        "run_id": run_id,
        "run_attempt": int(run_attempt),
        "commit": commit,
        "github_sha": github_sha,
        "os": expected_os,
        "os_system": actual_system,
        "python_version": actual_python,
        "python_full_version": platform.python_version(),
        "pytest_version": pytest.__version__,
        "module_sha256": _sha256(REPO_ROOT / MODULE),
        "pyproject_sha256": _sha256(REPO_ROOT / PYPROJECT),
    }


def _write_plan(args: argparse.Namespace) -> int:
    binding = _binding(args.os, args.python_version)
    nodeids = _collect_nodeids()
    shards = _partition(nodeids)
    document = {
        "schema_version": SCHEMA_VERSION,
        **binding,
        "module": MODULE.as_posix(),
        "shard_count": SHARD_COUNT,
        "nodeids": nodeids,
        "shards": shards,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created a complete plan with {len(nodeids)} IDs in {len(shards)} non-empty shards.")
    return 0


def _read_plan(path: Path) -> dict[str, object]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"could not read package test plan: {exc}")
    if not isinstance(plan, dict):
        _fail("package test plan must be a JSON object")
    return plan


def _run_shard(args: argparse.Namespace) -> int:
    plan = _read_plan(Path(args.plan))
    if plan.get("schema_version") != SCHEMA_VERSION:
        _fail("package test plan has an unsupported schema version")
    if plan.get("module") != MODULE.as_posix() or plan.get("shard_count") != SHARD_COUNT:
        _fail("package test plan has an unexpected module or shard count")

    binding = _binding(args.os, args.python_version)
    nodeids = _collect_nodeids()
    for field in BOUND_FIELDS:
        if plan.get(field) != binding[field]:
            _fail(f"package test plan binding mismatch for {field}")

    planned_nodeids = plan.get("nodeids")
    if planned_nodeids != nodeids:
        _fail("fresh complete collection does not exactly match the plan IDs")
    expected_shards = _partition(nodeids)
    if plan.get("shards") != expected_shards:
        _fail("plan shards are not the deterministic partition of the complete IDs")
    if not 0 <= args.shard < SHARD_COUNT:
        _fail(f"shard index must be between 0 and {SHARD_COUNT - 1}")

    selected = expected_shards[args.shard]
    print(f"Running shard {args.shard + 1}/{SHARD_COUNT} with {len(selected)} test IDs.")
    command = [sys.executable, "-m", "pytest", "-v", "-rA", *selected]
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan", help="collect the complete module and write its cell plan")
    plan.add_argument("--os", choices=sorted(EXPECTED_SYSTEMS), required=True)
    plan.add_argument("--python-version", required=True)
    plan.add_argument("--output", required=True)

    run = commands.add_parser("run", help="re-collect, validate, and run one assigned shard")
    run.add_argument("--plan", required=True)
    run.add_argument("--os", choices=sorted(EXPECTED_SYSTEMS), required=True)
    run.add_argument("--python-version", required=True)
    run.add_argument("--shard", type=int, required=True)

    collect = commands.add_parser("_collect", help="internal collection worker used by plan and run")
    collect.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "_collect":
        return _collect_command(args.output)
    if args.command == "plan":
        return _write_plan(args)
    return _run_shard(args)


if __name__ == "__main__":
    raise SystemExit(main())
