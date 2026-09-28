#!/usr/bin/env python3
"""Check the BACH skills-workflow projection contract against synthetic projection items.

The checker verifies:
  * the skills-workflow projection contract document itself (shape, hold,
    provenance, registry counts, keyword-to-carrier pattern)
  * every synthetic projection item (schema, required fields, trigger
    phrases, German language, carrier mapping, projection digest)
  * cross-item reconciliation (same projection scope and language,
    non-empty trigger phrases)
  * trigger-phrase and projection_id uniqueness (no double trigger)
  * toolchain/workflow_tuev absence findings for workflowhooker and MarbleRun
  * the expected document (item set, carriers, phrase totals, alignment)

Exit code 0 means every check passed. The emitted status string deliberately
says "not-equivalence": this checker proves contract & fixture conformance,
not behavioural equivalence with a live BACH ControlCenter registry.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "ellmos.open-ocean-bach-skills-workflow-projection.v1"
EXPECTED_ITEM_SCHEMA = "ellmos.open-ocean-skills-workflow-projection-item.v1"
EXPECTED_EXPECTED_SCHEMA = "ellmos.open-ocean-skills-workflow-projection-expected.v1"
EXPECTED_PROJECTION_SCOPE = "skills-workflow-projection"
EXPECTED_LANGUAGE = "de"
EXPECTED_TICKET = "T-20260920-823767362"
EXPECTED_COUNTS = {
    "tool_registry": 45,
    "ati_tool_registry": 137,
    "skills": 128,
    "toolchain_runs": 6,
    "tool_patterns": 5,
    "agents": 6,
}
EXPECTED_KEYWORD_TO_CARRIER = {
    "chain routine recurring": "marblerun",
    "agent agents": "agent-launcher",
    "ati task": "task-master",
    "backup db dbsync restore sync": "sqlite-transit-sync",
    "connector email msg": "connectors",
    "scheduler": "ellmos-scheduler",
    "schwarm": "swarm_ai",
}

REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "hold",
    "provenance",
    "projection_scope",
    "language",
    "source_registry",
    "projection",
    "toolchain_alignment",
    "fixtures",
    "classification",
    "next_gates",
]

BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
PROJECTION_ID_RE = re.compile(r"^sproj-\d{4}-\d{3}$")
REGISTRY_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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

    provenance = contract.get("provenance", {})
    if provenance.get("ticket") != EXPECTED_TICKET:
        problems.append("provenance ticket mismatch")
    if provenance.get("slice") != "S8":
        problems.append("provenance slice mismatch")
    if provenance.get("task") != 1446:
        problems.append("provenance task mismatch")

    if contract.get("projection_scope") != EXPECTED_PROJECTION_SCOPE:
        problems.append("contract projection_scope mismatch")

    if contract.get("language") != EXPECTED_LANGUAGE:
        problems.append("contract language mismatch")

    source_registry = contract.get("source_registry", {})
    if source_registry.get("read_only") is not True:
        problems.append("source_registry.read_only is not true")
    if source_registry.get("runtime_authority") is not False:
        problems.append("source_registry.runtime_authority is not false")
    if source_registry.get("counts") != EXPECTED_COUNTS:
        problems.append(f"contract registry counts mismatch: {source_registry.get('counts')}")

    projection = contract.get("projection", {})
    if projection.get("item_schema") != EXPECTED_ITEM_SCHEMA:
        problems.append("projection item_schema mismatch")
    if projection.get("keyword_to_carrier") != EXPECTED_KEYWORD_TO_CARRIER:
        problems.append("projection keyword_to_carrier mismatch")

    classification = contract.get("classification", {}).get("skills_workflow_projection", {})
    if classification.get("parity") != "not-accepted":
        problems.append("classification parity is not not-accepted")

    fixtures = contract.get("fixtures", {})
    for key in ("projection_items", "expected"):
        if key not in fixtures:
            problems.append(f"missing fixtures key: {key}")

    return problems


def validate_item(
    item: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    problems: list[str] = []

    item_id = item.get("projection_id", "")

    if item.get("schema") != EXPECTED_ITEM_SCHEMA:
        problems.append(f"item schema mismatch for {item_id}")

    for field in contract.get("projection", {}).get("required_item_fields", []):
        if field not in item:
            problems.append(f"missing item field {field!r} for {item_id}")

    allowed_sources = contract.get("projection", {}).get("allowed_item_sources", [])
    if item.get("source_registry") not in allowed_sources:
        problems.append(f"source_registry {item.get('source_registry')!r} not allowed for {item_id}")

    allowed_types = contract.get("projection", {}).get("allowed_item_types", [])
    if item.get("item_type") not in allowed_types:
        problems.append(f"item_type {item.get('item_type')!r} not allowed for {item_id}")

    if item.get("projection_scope") != EXPECTED_PROJECTION_SCOPE:
        problems.append(f"projection_scope mismatch for {item_id}")

    if item.get("language") != EXPECTED_LANGUAGE:
        problems.append(f"language mismatch for {item_id}")

    keyword_to_carrier = contract.get("projection", {}).get("keyword_to_carrier", {})
    carrier = item.get("carrier", "")
    if carrier not in keyword_to_carrier.values():
        problems.append(f"carrier {carrier!r} not in keyword_to_carrier values for {item_id}")

    if item.get("carrier_locator") != f"module:{carrier}":
        problems.append(f"carrier_locator mismatch for {item_id}")

    phrases = item.get("trigger_phrases", [])
    if not isinstance(phrases, list) or not phrases:
        problems.append(f"trigger_phrases must be a non-empty list for {item_id}")
    else:
        for phrase in phrases:
            if not isinstance(phrase, str) or not phrase.strip():
                problems.append(f"invalid trigger phrase {phrase!r} for {item_id}")
        if len(set(phrases)) != len(phrases):
            problems.append(f"duplicate trigger phrases within item {item_id}")

    if not PROJECTION_ID_RE.match(item_id):
        problems.append(f"invalid projection_id {item_id!r}")

    registry_key = item.get("registry_key", "")
    if not REGISTRY_KEY_RE.match(registry_key):
        problems.append(f"invalid registry_key {registry_key!r}")

    if not SHA256_RE.fullmatch(str(item.get("projection_digest", ""))):
        problems.append(f"projection_digest not a valid sha256 literal for {item_id}")

    for banned in BANNED_STRINGS:
        if banned in json.dumps(item):
            problems.append(f"banned marker {banned!r} in item {item_id}")

    return problems


def reconcile_items(
    contract: dict[str, Any],
    items: list[dict[str, Any]],
) -> list[str]:
    problems: list[str] = []

    if len(items) != 3:
        problems.append(f"expected 3 projection items, got {len(items)}")

    reconciliation = contract.get("projection", {}).get("reconciliation", {})

    for field in reconciliation.get("scope_fields", []):
        expected = contract.get(field)
        for item in items:
            if item.get(field) != expected:
                problems.append(
                    f"reconciliation mismatch on {field}: "
                    f"{item.get('projection_id')}={item.get(field)!r} "
                    f"expected {expected!r}"
                )

    for field in reconciliation.get("content_fields", []):
        for item in items:
            if not item.get(field):
                problems.append(
                    f"reconciliation mismatch on {field}: "
                    f"{item.get('projection_id')} carries no {field}"
                )

    return problems


def check_double_trigger(items: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []

    seen_ids: set[str] = set()
    seen_phrases: dict[str, str] = {}

    for item in items:
        item_id = item.get("projection_id", "")

        if item_id in seen_ids:
            problems.append(f"duplicate projection_id {item_id}")
        seen_ids.add(item_id)

        for phrase in item.get("trigger_phrases", []):
            if phrase in seen_phrases:
                problems.append(
                    f"duplicate trigger phrase {phrase!r} in {item_id} "
                    f"(already claimed by {seen_phrases[phrase]})"
                )
            else:
                seen_phrases[phrase] = item_id

    return problems


def check_toolchain_alignment(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []

    alignment = contract.get("toolchain_alignment", {})
    if not isinstance(alignment, dict):
        return ["toolchain_alignment missing"]

    hook = alignment.get("workflowhooker", {})
    if hook.get("version") != "0.2.1":
        problems.append("workflowhooker version mismatch")
    for capability in ("workflow.hook", "workflow.check"):
        if capability not in hook.get("provides", []):
            problems.append(f"workflowhooker missing capability {capability!r}")
    if hook.get("workflow_tuev_present") is not False:
        problems.append("workflowhooker workflow_tuev_present must be false")
    if hook.get("toolchain_strings_found") is not False:
        problems.append("workflowhooker toolchain_strings_found must be false")

    marble = alignment.get("marblerun", {})
    if marble.get("git_head") != "938f3d5":
        problems.append("marblerun git_head mismatch")
    if marble.get("git_branch") != "main":
        problems.append("marblerun git_branch mismatch")
    if marble.get("workflow_tuev_present") is not False:
        problems.append("marblerun workflow_tuev_present must be false")
    if marble.get("toolchain_strings_found") is not False:
        problems.append("marblerun toolchain_strings_found must be false")
    if marble.get("carrier_locator") != "module:marblerun":
        problems.append("marblerun carrier_locator mismatch")
    if marble.get("carrier_use_cases") != ["chain", "recurring", "routine"]:
        problems.append("marblerun carrier_use_cases mismatch")
    if marble.get("use_case_state") != "not-evidenced":
        problems.append("marblerun use_case_state mismatch")

    return problems


def check_expected(contract: dict[str, Any], items: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []

    expected_path = Path(contract["fixtures"]["expected"])
    if not expected_path.is_absolute():
        expected_path = Path(__file__).parent.parent / expected_path

    expected = load_json(expected_path)

    if expected.get("schema") != EXPECTED_EXPECTED_SCHEMA:
        problems.append("expected schema mismatch")

    registry_keys = sorted(item.get("registry_key", "") for item in items)
    if expected.get("items") != registry_keys:
        problems.append(f"expected items mismatch: {expected.get('items')} vs {registry_keys}")

    if expected.get("item_count") != len(items):
        problems.append(
            f"expected item_count mismatch: {expected.get('item_count')} vs {len(items)}"
        )

    carriers = sorted({item.get("carrier", "") for item in items})
    if expected.get("carriers") != carriers:
        problems.append(f"expected carriers mismatch: {expected.get('carriers')} vs {carriers}")

    phrase_total = sum(len(item.get("trigger_phrases", [])) for item in items)
    if expected.get("trigger_phrase_total") != phrase_total:
        problems.append(
            f"expected trigger_phrase_total mismatch: "
            f"{expected.get('trigger_phrase_total')} vs {phrase_total}"
        )

    alignment = contract.get("toolchain_alignment", {})
    expected_alignment = expected.get("toolchain_alignment", {})
    if (
        expected_alignment.get("workflowhooker_workflow_tuev_present")
        is not alignment.get("workflowhooker", {}).get("workflow_tuev_present")
    ):
        problems.append("expected toolchain alignment mismatch for workflowhooker")
    if (
        expected_alignment.get("marblerun_workflow_tuev_present")
        is not alignment.get("marblerun", {}).get("workflow_tuev_present")
    ):
        problems.append("expected toolchain alignment mismatch for marblerun")
    if (
        expected_alignment.get("marblerun_carrier_use_cases")
        != alignment.get("marblerun", {}).get("carrier_use_cases")
    ):
        problems.append("expected marblerun carrier_use_cases mismatch")

    if expected.get("double_trigger_found") is not False:
        problems.append("expected double_trigger_found must be false")

    if expected.get("reconciliation") != "agreed":
        problems.append("expected reconciliation mismatch")

    return problems


def run_all(contract_path: Path) -> list[str]:
    problems: list[str] = []

    contract = load_json(contract_path)
    problems.extend(validate_contract(contract))
    problems.extend(check_toolchain_alignment(contract))

    fixtures = contract.get("fixtures", {})
    item_paths = fixtures.get("projection_items", [])
    items: list[dict[str, Any]] = []

    for rel_path in item_paths:
        item_path = Path(rel_path)
        if not item_path.is_absolute():
            item_path = contract_path.parent.parent / item_path
        try:
            item = load_json(item_path)
        except FileNotFoundError:
            problems.append(f"missing projection item file: {item_path}")
            continue
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON in {item_path}: {exc}")
            continue
        items.append(item)
        problems.extend(validate_item(item, contract))

    if len(items) == 3:
        problems.extend(reconcile_items(contract, items))
        problems.extend(check_double_trigger(items))
        problems.extend(check_expected(contract, items))

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        default="architecture/bach-skills-workflow-projection-contract.v1.json",
        help="path to the skills-workflow projection contract JSON (relative to repo root unless absolute)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path

    problems = run_all(contract_path)

    if problems:
        print("skills-workflow-projection check: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "skills-workflow-projection check: PASSED "
        "(schema+fixture conformance, not equivalence with a live BACH ControlCenter registry)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())