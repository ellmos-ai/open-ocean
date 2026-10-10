#!/usr/bin/env python3
"""Check the documentation-loop contract against synthetic evidence chains.

The checker verifies:
  * the contract document itself (shape, states, rules, no frozen model/path/fan-out/time values)
  * every positive fixture chain is accepted without problems
  * every negative fixture chain is rejected with (at least) the expected problem codes

A single evidence chain can also be checked with ``--chain``.

Exit code 0 means every check passed. The emitted status string deliberately says
"not-live-evidence": the checker proves contract and fixture conformance, not that any
host currently runs the loop.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "ellmos.open-ocean-doc-loop.v1"
EXPECTED_STATES = ["trigger_planned", "task_created", "executed", "corrected", "reviewed", "repaired"]
REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "variants",
    "states",
    "enums",
    "difference_fields",
    "scope_fields",
    "rules",
    "configuration_fields",
    "fixtures",
    "next_gates",
]
EXPECTED_RULES = {
    "monotonic",
    "no_skipping",
    "marker_is_not_evidence",
    "task_status_is_not_evidence",
    "failed_execution_stops",
    "independent_review",
    "hash_bound_correction",
    "verdict_coverage",
    "repair_needs_review",
}
MARKER_KEYS = {"last_run", "dispatch_marker", "task_status"}
SHA_RE = re.compile(r"[0-9a-f]{64}")
# Frozen values from the legacy workflows must not enter the contract.
FROZEN_PATTERNS = {
    "model name": re.compile(r"\b(opus|sonnet|haiku|gemini|gpt|claude|codex|kimi)\b", re.I),
    "fixed archive percentage": re.compile(r"\b\d{2}\s*(%|percent|prozent)", re.I),
    "fixed path": re.compile(r"(\.\./docs|skills/docs|[A-Za-z]:\\|OneDrive)", re.I),
    "fixed fan-out": re.compile(r"\b\d+\s*(parallel|agents|agenten|helper|helfer)\b", re.I),
}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if contract.get("schema") != SCHEMA:
        problems.append("contract schema mismatch")
    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")
    names = [state.get("name") for state in contract.get("states", [])]
    if names != EXPECTED_STATES:
        problems.append("states mismatch or wrong order")
    for state in contract.get("states", []):
        if not state.get("required_evidence"):
            problems.append(f"state without required evidence: {state.get('name')}")
    if set(contract.get("rules", {})) != EXPECTED_RULES:
        problems.append("rules set mismatch")
    boundary = str(contract.get("claim_boundary", ""))
    if "unknown" not in boundary or "starts no workflow" not in boundary:
        problems.append("claim_boundary must state unknown semantics and the absence of a runtime")
    payload = json.dumps(contract, ensure_ascii=False)
    for label, pattern in FROZEN_PATTERNS.items():
        match = pattern.search(payload)
        if match:
            problems.append(f"contract freezes a {label}: {match.group(0)!r}")
    if "configuration_fields" in contract and not contract["configuration_fields"].get("fields"):
        problems.append("configuration_fields.fields is empty")
    return problems


def _missing(contract: dict[str, Any], state: str, evidence: dict[str, Any]) -> list[str]:
    required = next((s["required_evidence"] for s in contract["states"] if s["name"] == state), [])
    # None is a legal value only where the contract says so (exit_code of a failed run).
    return [
        f"E_MISSING_EVIDENCE:{state}.{field}"
        for field in required
        if field not in evidence
        or (not present(evidence[field]) and not (state == "executed" and field == "exit_code"))
    ]


def validate_chain(chain: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if chain.get("variant") not in contract["variants"]:
        problems.append("E_VARIANT")
    entries = chain.get("entries")
    if not isinstance(entries, list) or not entries:
        return problems + ["E_NO_ENTRIES"]

    seen: list[str] = []
    last_time: datetime | None = None
    by_state: dict[str, dict[str, Any]] = {}
    for entry in entries:
        state = entry.get("state")
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        if state not in EXPECTED_STATES:
            problems.append(f"E_STATE_UNKNOWN:{state}")
            continue
        if state in by_state:
            problems.append(f"E_DUPLICATE_STATE:{state}")
            continue
        if seen and EXPECTED_STATES.index(state) < EXPECTED_STATES.index(seen[-1]):
            problems.append(f"E_ORDER:{state}")
        seen.append(state)
        by_state[state] = evidence
        stamp = parse_time(entry.get("observed_at"))
        if stamp is None:
            problems.append(f"E_TIMESTAMP:{state}")
        elif last_time is not None and stamp < last_time:
            problems.append(f"E_TIME_ORDER:{state}")
        if stamp is not None:
            last_time = stamp if last_time is None or stamp > last_time else last_time
        problems += _missing(contract, state, evidence)
        if EXPECTED_STATES.index(state) >= EXPECTED_STATES.index("executed"):
            for key in sorted(MARKER_KEYS & set(evidence)):
                code = "E_TASK_STATUS_AS_EVIDENCE" if key == "task_status" else "E_MARKER_AS_EVIDENCE"
                problems.append(f"{code}:{state}")

    # no skipping / exact unknown list
    top = max((EXPECTED_STATES.index(s) for s in by_state), default=-1)
    for name in EXPECTED_STATES[: top + 1]:
        if name not in by_state:
            problems.append(f"E_SKIPPED:{name}")
    if sorted(chain.get("unknown", [])) != sorted(set(EXPECTED_STATES) - set(by_state)):
        problems.append("E_UNKNOWN_LIST")

    executed = by_state.get("executed")
    if executed is not None:
        exit_state = executed.get("exit_state")
        exit_code = executed.get("exit_code")
        if exit_state not in contract["enums"]["exit_state"]:
            problems.append("E_EXIT_STATE")
        elif exit_state == "succeeded" and (not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code != 0):
            problems.append("E_EXIT_CODE")
        elif exit_state != "succeeded" and any(s in by_state for s in EXPECTED_STATES[3:]):
            problems.append("E_FAILED_NOT_STOPPED")

    corrected = by_state.get("corrected")
    differences: list[Any] = []
    if corrected is not None:
        for file in corrected.get("files", []):
            before, after = file.get("before_sha256"), file.get("after_sha256")
            if not (isinstance(before, str) and isinstance(after, str) and SHA_RE.fullmatch(before) and SHA_RE.fullmatch(after)):
                problems.append("E_HASH")
            elif before == after:
                problems.append("E_HASH_UNCHANGED")
            if not present(file.get("path")):
                problems.append("E_HASH")
        differences = corrected.get("differences", []) if isinstance(corrected.get("differences"), list) else []
        for diff in differences:
            if any(not present(diff.get(field)) for field in contract["difference_fields"]):
                problems.append("E_DIFFERENCE_FIELDS")
                continue
            scope = diff["scope"] if isinstance(diff["scope"], dict) else {}
            if any(not present(scope.get(field)) for field in contract["scope_fields"]) \
                    or scope.get("surface") not in contract["enums"]["surface"]:
                problems.append("E_DIFFERENCE_SCOPE")

    reviewed = by_state.get("reviewed")
    if reviewed is not None and executed is not None:
        if reviewed.get("reviewer_id") == executed.get("author_id") \
                or reviewed.get("reviewer_instance") == executed.get("author_instance"):
            problems.append("E_SAME_REVIEWER")
        verdicts = reviewed.get("verdicts", [])
        if not isinstance(verdicts, list) or len(verdicts) != len(differences) \
                or any(v.get("verdict") not in contract["enums"]["verdict"] for v in verdicts):
            problems.append("E_VERDICTS")

    repaired = by_state.get("repaired")
    if repaired is not None:
        if "reviewed" not in by_state:
            problems.append("E_REPAIR_NEEDS_REVIEW")
        remeasure = repaired.get("remeasure") if isinstance(repaired.get("remeasure"), dict) else {}
        if remeasure.get("equal") is not True or repaired.get("regression") is not False:
            problems.append("E_REPAIR")
    return problems


def run_fixtures(contract: dict[str, Any], repo_root: Path) -> list[str]:
    problems: list[str] = []
    directory = repo_root / contract["fixtures"]["directory"]
    expected = json.loads((repo_root / contract["fixtures"]["expected"]).read_text(encoding="utf-8"))
    for name in expected["positive"]:
        chain = json.loads((directory / name).read_text(encoding="utf-8"))
        found = validate_chain(chain, contract)
        if found:
            problems.append(f"positive fixture rejected: {name}: {found}")
    for name, codes in expected["negative"].items():
        chain = json.loads((directory / name).read_text(encoding="utf-8"))
        found = validate_chain(chain, contract)
        if not found:
            problems.append(f"negative fixture accepted: {name}")
        for code in codes:
            if not any(item == code or item.startswith(code + ":") for item in found):
                problems.append(f"negative fixture {name} lacks expected problem {code}: {found}")
    listed = set(expected["positive"]) | set(expected["negative"])
    on_disk = {p.name for p in directory.glob("*.json") if p.name != "expected.json"}
    if listed != on_disk:
        problems.append(f"fixture list and directory differ: {sorted(listed ^ on_disk)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        default="architecture/ocean-doc-loop.v1.json",
        help="path to the contract JSON (relative to repo root unless absolute)",
    )
    parser.add_argument("--chain", default=None, help="check one evidence chain JSON instead of the fixtures")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    problems = validate_contract(contract)
    if args.chain:
        problems += validate_chain(json.loads(Path(args.chain).read_text(encoding="utf-8")), contract)
    else:
        problems += run_fixtures(contract, repo_root)

    out = {
        "schema": "ellmos.open-ocean-doc-loop-check.v1",
        "status": "pass-contract-and-fixtures-not-live-evidence" if not problems else "fail",
        "problems": problems,
    }
    print(json.dumps(out, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
