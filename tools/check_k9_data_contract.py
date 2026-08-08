#!/usr/bin/env python3
"""Check the K9 data contract without booting or importing BACH.

The source side is inspected with AST and hashes only. The carrier side runs on
the repository's anonymized SQLite fixtures in a temporary directory. Passing
this check is contract and carrier evidence, not BACH runtime equivalence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def extract_operations(path: Path, profile: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        profile_name: str | None = None
        operations: list[str] | None = None
        for member in node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if member.name == "profile_name":
                for returned in (item for item in ast.walk(member) if isinstance(item, ast.Return)):
                    try:
                        value = ast.literal_eval(returned.value)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, str):
                        profile_name = value
            elif member.name == "get_operations":
                for returned in (item for item in ast.walk(member) if isinstance(item, ast.Return)):
                    try:
                        value = ast.literal_eval(returned.value)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
                        operations = sorted(value)
        if profile_name == profile and operations is not None:
            return operations
    raise ValueError(f"Profile {profile!r} with a literal get_operations() not found in {path}")


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if contract.get("schema") != "ellmos.open-ocean-bach-k9-data-contract.v1":
        problems.append("unexpected contract schema")
    profiles = contract.get("profiles", {})
    for profile, expected_count in (("dbsync", 9), ("snapshot", 4)):
        operations = profiles.get(profile, {}).get("operations", [])
        names = [item.get("name") for item in operations]
        if len(operations) != expected_count or len(set(names)) != expected_count:
            problems.append(f"{profile}: expected {expected_count} unique operations")
        if any(item.get("parity") == "accepted" for item in operations):
            problems.append(f"{profile}: contract baseline must not claim accepted parity")
    if profiles.get("snapshot", {}).get("carrier_fit") != "wrong-carrier":
        problems.append("snapshot must remain outside the database-transit carrier")
    for source_name in ("bach", "carrier"):
        commit = contract.get("sources", {}).get(source_name, {}).get("commit", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            problems.append(f"{source_name}: expected a pinned 40-character commit")
    return problems


def inspect_bach(contract: dict[str, Any], bach_root: Path) -> dict[str, Any]:
    expected = contract["sources"]["bach"]
    result: dict[str, Any] = {"head": git_head(bach_root), "profiles": {}, "problems": []}
    if result["head"] != expected["commit"]:
        result["problems"].append(
            f"BACH commit drift: expected {expected['commit']}, got {result['head']}"
        )
    for profile, relative in expected["handler_files"].items():
        path = bach_root / relative["path"]
        actual_hash = sha256(path)
        actual_operations = extract_operations(path, profile)
        expected_operations = sorted(
            item["name"] for item in contract["profiles"][profile]["operations"]
        )
        result["profiles"][profile] = {
            "sha256": actual_hash,
            "operations": actual_operations,
        }
        if actual_hash != relative["sha256"]:
            result["problems"].append(f"{profile}: source hash drift")
        if actual_operations != expected_operations:
            result["problems"].append(
                f"{profile}: operations drift: expected {expected_operations}, got {actual_operations}"
            )
    return result


def create_database(path: Path, sql_path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(sql_path.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def query(path: Path, sql: str) -> list[list[Any]]:
    connection = sqlite3.connect(path)
    try:
        return [list(row) for row in connection.execute(sql).fetchall()]
    finally:
        connection.close()


def run_carrier_fixture(
    contract: dict[str, Any],
    repo_root: Path,
    carrier_root: Path,
) -> dict[str, Any]:
    expected_source = contract["sources"]["carrier"]
    result: dict[str, Any] = {
        "head": git_head(carrier_root),
        "module": None,
        "observed": {},
        "problems": [],
    }
    if result["head"] != expected_source["commit"]:
        result["problems"].append(
            f"carrier commit drift: expected {expected_source['commit']}, got {result['head']}"
        )

    sys.path.insert(0, str(carrier_root))
    try:
        module = importlib.import_module("sqlite_transit_sync")
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(carrier_root.resolve()):
            result["problems"].append(f"carrier import escaped requested root: {module_path}")
            return result
        result["module"] = str(module_path)
        SyncConfig = module.SyncConfig
        TransitSync = module.TransitSync

        fixture = contract["fixtures"]
        source_sql = repo_root / fixture["source_sql"]
        target_sql = repo_root / fixture["target_sql"]
        expected = json.loads((repo_root / fixture["expected"]).read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            transit = temp / "transit"
            source_db = temp / "source.sqlite"
            target_db = temp / "target.sqlite"
            create_database(source_db, source_sql)
            create_database(target_db, target_sql)
            source = TransitSync(
                SyncConfig(source_db, transit, temp / "source-state.json", "node-a", "fixture")
            )
            target = TransitSync(
                SyncConfig(target_db, transit, temp / "target-state.json", "node-b", "fixture")
            )
            snapshot = source.push()
            reports = target.pull()
            cleanup = source.cleanup(keep_days=0, keep_per_node=0)
            observed = {
                "source_snapshot_secret_rows": query(
                    snapshot.path, "SELECT COUNT(*) FROM secrets"
                )[0][0],
                "target_secret_rows": query(target_db, "SELECT COUNT(*) FROM secrets")[0][0],
                "target_items": query(target_db, "SELECT id, value FROM items ORDER BY id"),
                "merge_inserted": sum(report.inserted for report in reports),
                "merge_updated": sum(report.updated for report in reports),
                "cleanup_dry_run": cleanup["dry_run"],
                "cleanup_scope": cleanup["scope"],
                "cleanup_eligible": len(cleanup["eligible"]),
            }
            result["observed"] = observed
            for key, expected_value in expected.items():
                if key == "schema":
                    continue
                if observed.get(key) != expected_value:
                    result["problems"].append(
                        f"fixture {key}: expected {expected_value!r}, got {observed.get(key)!r}"
                    )
    finally:
        sys.path.pop(0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--bach-root", type=Path, required=True)
    parser.add_argument("--carrier-root", type=Path, required=True)
    args = parser.parse_args()

    contract_path = args.contract.resolve()
    repo_root = contract_path.parent.parent
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_problems = validate_contract(contract)
    bach = inspect_bach(contract, args.bach_root.resolve())
    carrier = run_carrier_fixture(contract, repo_root, args.carrier_root.resolve())
    problems = contract_problems + bach["problems"] + carrier["problems"]
    output = {
        "schema": "ellmos.open-ocean-k9-data-check.v1",
        "status": "pass-contract-and-carrier-fixture-not-equivalence" if not problems else "fail",
        "contract": str(contract_path),
        "bach": bach,
        "carrier": carrier,
        "problems": problems,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
