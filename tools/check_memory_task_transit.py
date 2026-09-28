#!/usr/bin/env python3
"""Check the BACH memory-task-transit contract against synthetic host receipts.

The checker verifies:
  * the memory-task-transit contract document itself (shape, hold, claim signal)
  * every synthetic host receipt (schema, required fields, privacy class,
    transit scope, claim salt, receipt signature)
  * cross-host reconciliation (same task_uid, stable_id, scope, contents)
  * double-claim prohibition (unique host_id and sequence per stable_id)

Exit code 0 means every check passed. The emitted status string deliberately
says "not-equivalence": this checker proves contract & fixture conformance,
not behavioural equivalence with a live BACH working-memory database.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "ellmos.open-ocean-bach-memory-task-transit.v1"
EXPECTED_RECEIPT_SCHEMA = "ellmos.open-ocean-memory-task-host-receipt.v1"
EXPECTED_TRANSIT_SCOPE = "memory-task-transit"
EXPECTED_PRIVACY_CLASS = "bach-working-memory-pointer-row"

REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "hold",
    "stable_id",
    "task_uid",
    "transit_scope",
    "privacy_class",
    "hosts",
    "receipt_schema",
    "required_receipt_fields",
    "required_contents_fields",
    "claim_signal",
    "reconciliation",
    "double_claim_prohibition",
    "fixtures",
    "classification",
    "next_gates",
]

BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
HOST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    if contract.get("schema") != EXPECTED_SCHEMA:
        problems.append("contract schema mismatch")

    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")

    hold = contract.get("hold", {})
    if hold.get("bach_mode") != "read-only":
        problems.append("hold.bach_mode is not read-only")

    if contract.get("transit_scope") != EXPECTED_TRANSIT_SCOPE:
        problems.append("contract transit_scope mismatch")

    if contract.get("privacy_class") != EXPECTED_PRIVACY_CLASS:
        problems.append("contract privacy_class mismatch")

    if contract.get("receipt_schema") != EXPECTED_RECEIPT_SCHEMA:
        problems.append("contract receipt_schema mismatch")

    hosts = contract.get("hosts", [])
    expected_hosts = {"mac-studio", "WORKSTATION-LG", "ASUS-GEI"}
    if set(hosts) != expected_hosts:
        problems.append(f"contract hosts mismatch: {set(hosts)}")

    return problems


def validate_receipt(
    receipt: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    problems: list[str] = []

    if receipt.get("schema") != EXPECTED_RECEIPT_SCHEMA:
        problems.append(f"receipt schema mismatch for {receipt.get('host_id')}")

    for field in contract.get("required_receipt_fields", []):
        if field not in receipt:
            problems.append(f"missing receipt field {field!r} for {receipt.get('host_id')}")

    for field in contract.get("required_contents_fields", []):
        if field not in receipt.get("contents", {}):
            problems.append(
                f"missing contents field {field!r} for {receipt.get('host_id')}"
            )

    host_id = receipt.get("host_id", "")
    if not HOST_ID_RE.match(host_id):
        problems.append(f"invalid host_id {host_id!r}")

    if receipt.get("transit_scope") != EXPECTED_TRANSIT_SCOPE:
        problems.append(f"transit_scope mismatch for {host_id}")

    if receipt.get("privacy_class") != EXPECTED_PRIVACY_CLASS:
        problems.append(f"privacy_class mismatch for {host_id}")

    if not SHA256_RE.fullmatch(str(receipt.get("claim_salt_hash", ""))):
        problems.append(f"claim_salt_hash not a valid sha256 literal for {host_id}")

    if not SHA256_RE.fullmatch(str(receipt.get("receipt_signature", ""))):
        problems.append(f"receipt_signature not a valid sha256 literal for {host_id}")

    for banned in BANNED_STRINGS:
        if banned in json.dumps(receipt):
            problems.append(f"banned marker {banned!r} in receipt {host_id}")

    return problems


def reconcile_receipts(
    contract: dict[str, Any],
    receipts: list[dict[str, Any]],
) -> list[str]:
    problems: list[str] = []

    if len(receipts) != 3:
        problems.append(f"expected 3 host receipts, got {len(receipts)}")

    reconciliation = contract.get("reconciliation", {})

    def field_value(receipt: dict[str, Any], field: str) -> Any:
        if field in ("logical_task_id", "payload_digest"):
            return receipt.get("contents", {}).get(field)
        return receipt.get(field)

    first = receipts[0] if receipts else {}
    for field in reconciliation.get("identity_fields", []):
        expected = contract.get(field) if field in ("task_uid", "stable_id") else first.get(field)
        for receipt in receipts:
            if field_value(receipt, field) != expected:
                problems.append(
                    f"reconciliation mismatch on {field}: "
                    f"{receipt.get('host_id')}={field_value(receipt, field)!r} "
                    f"expected {expected!r}"
                )

    for field in reconciliation.get("scope_fields", []):
        expected = contract.get(field) if field in ("transit_scope", "privacy_class") else first.get(field)
        for receipt in receipts:
            if field_value(receipt, field) != expected:
                problems.append(
                    f"reconciliation mismatch on {field}: "
                    f"{receipt.get('host_id')}={field_value(receipt, field)!r} "
                    f"expected {expected!r}"
                )

    for field in reconciliation.get("content_fields", []):
        expected = first.get("contents", {}).get(field)
        for receipt in receipts:
            if field_value(receipt, field) != expected:
                problems.append(
                    f"reconciliation mismatch on contents.{field}: "
                    f"{receipt.get('host_id')}={field_value(receipt, field)!r} "
                    f"expected {expected!r}"
                )

    return problems


def check_double_claim(receipts: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []

    seen_hosts: set[str] = set()
    seen_sequences: set[Any] = set()

    for receipt in receipts:
        host_id = receipt.get("host_id")
        sequence = receipt.get("sequence")

        if host_id in seen_hosts:
            problems.append(f"double claim detected for host {host_id}")
        seen_hosts.add(host_id)

        if sequence in seen_sequences:
            problems.append(f"duplicate sequence {sequence}")
        seen_sequences.add(sequence)

    return problems


def check_expected(contract: dict[str, Any], receipts: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []

    expected_path = Path(contract["fixtures"]["expected"])
    if not expected_path.is_absolute():
        expected_path = Path(__file__).parent.parent / expected_path

    expected = load_json(expected_path)

    host_ids = sorted(receipt.get("host_id") for receipt in receipts)
    if expected.get("hosts") != host_ids:
        problems.append(f"expected hosts mismatch: {expected.get('hosts')} vs {host_ids}")

    if expected.get("host_count") != len(receipts):
        problems.append(
            f"expected host_count mismatch: {expected.get('host_count')} vs {len(receipts)}"
        )

    sequences = sorted(receipt.get("sequence") for receipt in receipts if "sequence" in receipt)
    if expected.get("sequences") != sequences:
        problems.append(f"expected sequences mismatch: {expected.get('sequences')} vs {sequences}")

    return problems


def run_all(contract_path: Path) -> list[str]:
    problems: list[str] = []

    contract = load_json(contract_path)
    problems.extend(validate_contract(contract))

    fixtures = contract.get("fixtures", {})
    receipt_paths = fixtures.get("host_receipts", [])
    receipts: list[dict[str, Any]] = []

    for rel_path in receipt_paths:
        receipt_path = Path(rel_path)
        if not receipt_path.is_absolute():
            receipt_path = contract_path.parent.parent / receipt_path
        try:
            receipt = load_json(receipt_path)
        except FileNotFoundError:
            problems.append(f"missing receipt file: {receipt_path}")
            continue
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON in {receipt_path}: {exc}")
            continue
        receipts.append(receipt)
        problems.extend(validate_receipt(receipt, contract))

    if len(receipts) == 3:
        problems.extend(reconcile_receipts(contract, receipts))
        problems.extend(check_double_claim(receipts))
        problems.extend(check_expected(contract, receipts))

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        default="architecture/bach-memory-task-transit-contract.v1.json",
        help="path to the memory-task-transit contract JSON (relative to repo root unless absolute)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path

    problems = run_all(contract_path)

    if problems:
        print("memory-task-transit check: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "memory-task-transit check: PASSED "
        "(schema+fixture conformance, not equivalence with a live BACH working-memory row)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
