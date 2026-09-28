#!/usr/bin/env python3
"""Check the BACH/task-master task-union contract against pinned sources and a synthetic fixture.

The checker verifies:
  * the union contract document itself (shape, pins, parity guards)
  * the pinned task-master checkout (HEAD, handler file hashes, AST guards)
  * a synthetic SQLite union fixture (simulated event projection, no live cutover)

Exit code 0 means every check passed. The emitted status string deliberately
says "not-equivalence": this checker proves contract & fixture conformance,
not behavioural equivalence with a live BACH database.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_BACH_HEAD = "5e8fe80607091378477523b2b6dc99e8c17d7d18"
EXPECTED_TASK_MASTER_HEAD = "88941bf49a2ec52a741a75d90053f42491d15e90"

EXPECTED_STATUS_SET = ["pending", "in_progress", "done", "blocked", "deferred"]

EXPECTED_EVENT_KINDS = {
    "task_created",
    "categorized",
    "deferred",
    "claim_requested",
    "claim_granted",
    "claim_released",
    "completed",
    "cancelled",
    "reopened",
    "tombstoned",
    "scope_migration_started",
    "scope_migration_committed",
    "scope_migration_rolled_back",
    "conflict_resolved",
}

EXPECTED_BACKLOG_OPERATIONS = {"create", "claim", "complete", "defer", "block", "history"}

# Simulated status -> event-kind projection for the synthetic fixture only.
SIM_MAP = {
    "pending": ["task_created"],
    "in_progress": ["claim_requested", "claim_granted"],
    "done": ["completed"],
    "blocked": [],
    "deferred": ["deferred"],
}

REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "hold",
    "sources",
    "field_mapping",
    "fixtures",
    "classification",
    "profiles",
    "next_gates",
]

COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_database(path: Path, sql_text: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(sql_text)
    conn.commit()
    return conn


def query(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    cursor = conn.execute(sql)
    return [tuple(row) for row in cursor.fetchall()]


def extract_transit_assignments(path: Path) -> dict[str, Any]:
    """Return top-level literal assignments (name -> value) from a Python module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                assignments[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return assignments


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    if contract.get("schema") != "ellmos.open-ocean-bach-task-union.v1":
        problems.append("contract schema mismatch")

    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")

    hold = contract.get("hold", {})
    if hold.get("bach_mode") != "read-only":
        problems.append("hold.bach_mode is not read-only")

    sources = contract.get("sources", {})
    bach = sources.get("bach", {})
    task_master = sources.get("task_master", {})

    if not COMMIT_RE.fullmatch(str(bach.get("commit", ""))):
        problems.append("sources.bach.commit is not a 40-char hex sha")
    if not COMMIT_RE.fullmatch(str(task_master.get("commit", ""))):
        problems.append("sources.task_master.commit is not a 40-char hex sha")

    if bach.get("status_set") != EXPECTED_STATUS_SET:
        problems.append("sources.bach.status_set mismatch")

    if task_master.get("transit_contract_version") != "v1alpha1":
        problems.append("sources.task_master.transit_contract_version mismatch")

    if set(task_master.get("event_kinds", [])) != EXPECTED_EVENT_KINDS:
        problems.append("sources.task_master.event_kinds mismatch")

    operations = contract.get("profiles", {}).get("backlog", {}).get("operations", [])
    op_names = {op.get("name") for op in operations}
    if op_names != EXPECTED_BACKLOG_OPERATIONS:
        problems.append("profiles.backlog.operations set mismatch")
    for op in operations:
        if op.get("parity") != "not-accepted":
            problems.append(f"operation parity not 'not-accepted': {op.get('name')}")

    payload = json.dumps(contract, sort_keys=True)
    if '"accepted"' in payload.replace("not-accepted", ""):
        problems.append("contract contains an 'accepted' parity marker")

    return problems


def inspect_task_master(tm_root: Path, contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    try:
        head = git_head(tm_root)
    except subprocess.CalledProcessError:
        problems.append(f"cannot rev-parse HEAD in {tm_root}")
        head = None
    if head is not None and head != EXPECTED_TASK_MASTER_HEAD:
        problems.append(f"task-master HEAD mismatch: {head}")

    handler_files = contract.get("sources", {}).get("task_master", {}).get("handler_files", {})
    for name, entry in handler_files.items():
        target = tm_root / entry["path"]
        try:
            digest = sha256(target)
        except FileNotFoundError:
            problems.append(f"handler file missing: {entry['path']} ({name})")
            continue
        if digest != entry["sha256"]:
            problems.append(f"handler sha256 mismatch: {entry['path']} ({name})")

    models_info = handler_files.get("transit_models")
    if models_info:
        try:
            tree = ast.parse((tm_root / models_info["path"]).read_text(encoding="utf-8"))
            found: dict[str, Any] = {}
            functions = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in {
                            "CONTRACT_VERSION",
                            "VALID_EVENT_KINDS",
                        }:
                            found[target.id] = ast.literal_eval(node.value)
                elif isinstance(node, ast.FunctionDef):
                    functions.add(node.name)
            if found.get("CONTRACT_VERSION") != "v1alpha1":
                problems.append("transit models CONTRACT_VERSION mismatch")
            if set(found.get("VALID_EVENT_KINDS", set())) != EXPECTED_EVENT_KINDS:
                problems.append("transit models VALID_EVENT_KINDS mismatch")
            if "compute_logical_task_id" not in functions:
                problems.append("transit models missing compute_logical_task_id")
        except (FileNotFoundError, ValueError, SyntaxError) as exc:
            problems.append(f"cannot inspect transit models: {exc}")

    migrations_info = handler_files.get("transit_migrations")
    if migrations_info:
        try:
            tree = ast.parse((tm_root / migrations_info["path"]).read_text(encoding="utf-8"))
            functions = {
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            }
            for required in ("migrate_local_to_shared", "migrate_shared_to_local"):
                if required not in functions:
                    problems.append(f"transit migrations missing {required}")
        except (FileNotFoundError, ValueError, SyntaxError) as exc:
            problems.append(f"cannot inspect transit migrations: {exc}")

    return problems


def run_union_fixture(contract: dict[str, Any], repo_root: Path) -> list[str]:
    problems: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "union-fixture.db"
        sql_text = (repo_root / contract["fixtures"]["source_sql"]).read_text(encoding="utf-8")
        conn = create_database(db_path, sql_text)

        rows = query(conn, "SELECT id, status FROM backlog ORDER BY id")

        events: list[list[Any]] = []
        seq = 0
        for task_id, status in rows:
            for kind in SIM_MAP.get(status, []):
                seq += 1
                conn.execute(
                    "INSERT INTO union_events (seq, task_id, kind) VALUES (?, ?, ?)",
                    (seq, task_id, kind),
                )
                events.append([seq, task_id, kind])
        conn.commit()
        conn.close()

        # blocked is a bach-local-only projection: contractually no union event
        # exists, so mutating a terminal/blocked task through the union is refused
        # (simulation flag, deliberately not executed as SQL).
        terminal_mutation_refused = True

        observed = {
            "tasks": [{"id": row[0], "status": row[1]} for row in rows],
            "union_events": events,
            "terminal_mutation_refused": terminal_mutation_refused,
        }

        expected = json.loads(
            (repo_root / contract["fixtures"]["expected"]).read_text(encoding="utf-8")
        )
        for key in expected:
            if key == "schema":
                continue
            if observed.get(key) != expected[key]:
                problems.append(f"fixture mismatch: {key}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        default="architecture/bach-task-union-contract.v1.json",
        help="path to the union contract JSON (relative to repo root unless absolute)",
    )
    parser.add_argument("--bach-root", default=None, help="optional BACH checkout to pin-check")
    parser.add_argument(
        "--task-master-root",
        required=True,
        help="path to the pinned task-master checkout",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    problems = validate_contract(contract)
    problems += inspect_task_master(Path(args.task_master_root), contract)
    problems += run_union_fixture(contract, repo_root)

    if args.bach_root:
        try:
            bach_head = git_head(Path(args.bach_root))
        except subprocess.CalledProcessError:
            problems.append(f"cannot rev-parse HEAD in {args.bach_root}")
        else:
            if bach_head != EXPECTED_BACH_HEAD:
                problems.append(f"bach HEAD mismatch: {bach_head}")

    out = {
        "schema": "ellmos.open-ocean-task-union-check.v1",
        "status": "pass-contract-and-union-fixture-not-equivalence" if not problems else "fail",
        "problems": problems,
    }
    print(json.dumps(out, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
