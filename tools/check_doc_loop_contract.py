#!/usr/bin/env python3
"""Check the documentation-loop contract against synthetic evidence chains.

The checker verifies:
  * the contract document itself (shape, states, rules, mandatory evidence sets and the
    interval reference form that the contract may extend but never weaken, no frozen
    model/path/fan-out/time/archive values)
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = "ellmos.open-ocean-doc-loop.v1"
EXPECTED_STATES = ["trigger_planned", "task_created", "executed", "corrected", "reviewed", "repaired"]
# Mandatory evidence per state, held here independently of the contract file: a contract
# may add fields but removing one is reported as weakening.
REQUIRED_EVIDENCE = {
    "trigger_planned": ["routine", "interval_ref", "marker_source", "next_due_at"],
    "task_created": ["task_id", "title_sha256", "worker_binding", "readback_verified", "readback_ref", "readback_sha256", "created_at"],
    "executed": ["run_id", "host", "instance", "product_version", "exit_state", "exit_code", "started_at", "finished_at", "result_id", "author_id", "author_instance"],
    "corrected": ["files", "differences", "diff_ref", "corrected_at", "archival", "open_requirements"],
    "reviewed": ["reviewer_id", "reviewer_instance", "verdicts", "accepted_at"],
    "repaired": ["repair_success_at", "remeasure", "regression"],
}
# Strict value types of the mandatory fields. "int" excludes bool; "int|none" allows a null.
FIELD_TYPES = {
    "trigger_planned": {"routine": "str", "interval_ref": "str", "marker_source": "str", "next_due_at": "str"},
    "task_created": {"task_id": "int", "title_sha256": "str", "worker_binding": "dict", "readback_verified": "bool",
                     "readback_ref": "str", "readback_sha256": "str", "created_at": "str"},
    "executed": {"run_id": "str", "host": "str", "instance": "str", "product_version": "str", "exit_state": "str",
                 "exit_code": "int|none", "started_at": "str", "finished_at": "str", "result_id": "str",
                 "author_id": "str", "author_instance": "str"},
    "corrected": {"files": "list", "differences": "list", "diff_ref": "str", "corrected_at": "str",
                  "archival": "list", "open_requirements": "list"},
    "reviewed": {"reviewer_id": "str", "reviewer_instance": "str", "verdicts": "list", "accepted_at": "str"},
    "repaired": {"repair_success_at": "str", "remeasure": "dict", "regression": "bool"},
}
EMPTY_LIST_OK = {("corrected", "archival"), ("corrected", "open_requirements")}
NULL_OK = {("executed", "exit_code")}
INTERVAL_REF_PATTERN = r"^(config|routine|policy):[A-Za-z0-9._/-]+$"
INTERVAL_REF_RE = re.compile(INTERVAL_REF_PATTERN)
REQUIRED_TOP_KEYS = [
    "schema", "status", "recorded_at", "claim_boundary", "variants", "states", "enums",
    "difference_fields", "scope_fields", "archival_fields", "reader_check_fields",
    "open_requirement_fields", "remeasure_fields", "reference_patterns", "rules",
    "configuration_fields", "fixtures", "next_gates",
]
EXPECTED_RULES = {
    "monotonic", "no_skipping", "marker_is_not_evidence", "task_status_is_not_evidence",
    "failed_execution_stops", "independent_review", "hash_bound_correction", "verdict_coverage",
    "repair_needs_review", "readback_is_evidence", "event_time_order", "archival_needs_reader_check",
    "open_requirements_kept", "interval_is_configuration", "strict_types",
}
MARKER_KEYS = {"last_run", "dispatch_marker", "task_status"}
SHA_RE = re.compile(r"[0-9a-f]{64}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3}|\.\d{6})?(?:Z|[+-]\d{2}:\d{2})")
UNIT = r"(?:day|days|tag|tage|tagen|hour|hours|stunde|stunden|week|weeks|woche|wochen|minute|minutes|minuten|month|months|monat|monate|monaten)"
# Frozen values from the legacy workflows must not enter the contract or the fixtures.
FROZEN_PATTERNS = {
    "model name": re.compile(r"\b(opus|sonnet|haiku|gemini|gpt|claude|codex|kimi)\b", re.I),
    "fixed archive percentage": re.compile(r"\b\d{2}\s*(%|percent|prozent)", re.I),
    "fixed path": re.compile(r"(\.\./docs|skills/docs|[A-Za-z]:\\|OneDrive)", re.I),
    "fixed fan-out": re.compile(r"\b\d+\s*(parallel|agents|agenten|helper|helfer)\b", re.I),
    "fixed interval": re.compile(r"\b(?:every|alle|jede[nrms]?|each|per|pro)\s+\d+\s*" + UNIT + r"\b", re.I),
    "fixed duration": re.compile(r"\b\d+\s*[- ]?\s*" + UNIT + r"\b", re.I),
    "ISO duration": re.compile(r"\bP(?=\d|T\d)(?:\d+[YMWD])*(?:T(?:\d+[HMS])+)?\b"),
}
# Pairs along the chain; each present pair must be non-decreasing.
TIME_ORDER = [
    ("task_created", "created_at"),
    ("executed", "started_at"),
    ("executed", "finished_at"),
    ("corrected", "corrected_at"),
    ("reviewed", "accepted_at"),
    ("repaired", "remeasure.measured_at"),
    ("repaired", "repair_success_at"),
]


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    # One exact shape on every supported Python (3.10 is lenient about stray characters and needs
    # 3 or 6 fractional digits): extended ISO-8601 with seconds and a mandatory Z or numeric offset.
    if TIME_RE.fullmatch(value) is None:
        return None
    try:
        # Python < 3.11 rejects a trailing "Z"; spell it as an explicit UTC offset.
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def is_utc(value: Any) -> bool:
    parsed = parse_time(value)
    return parsed is not None and parsed.utcoffset() == timedelta(0)


def present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def type_ok(value: Any, spec: str) -> bool:
    kinds = {
        "str": lambda v: isinstance(v, str),
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "bool": lambda v: isinstance(v, bool),
        "list": lambda v: isinstance(v, list),
        "dict": lambda v: isinstance(v, dict),
        "none": lambda v: v is None,
    }
    return any(kinds[part](value) for part in spec.split("|"))


def dict_items(value: Any) -> list[dict[str, Any]]:
    """The dict elements of a list; anything else is skipped here (the type check reports it)."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def frozen_hits(text: str) -> list[str]:
    return [f"{label}: {m.group(0)!r}" for label, pattern in FROZEN_PATTERNS.items() if (m := pattern.search(text))]


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if contract.get("schema") != SCHEMA:
        problems.append("contract schema mismatch")
    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")
    states = contract.get("states", [])
    if [state.get("name") for state in states] != EXPECTED_STATES:
        problems.append("states mismatch or wrong order")
    for state in states:
        name = state.get("name")
        missing = set(REQUIRED_EVIDENCE.get(name, [])) - set(state.get("required_evidence", []))
        if missing:
            problems.append(f"contract weakens required evidence of {name}: {sorted(missing)}")
    if set(contract.get("rules", {})) != EXPECTED_RULES:
        problems.append("rules set mismatch")
    if contract.get("reference_patterns", {}).get("interval_ref") != INTERVAL_REF_PATTERN:
        problems.append("contract weakens the interval_ref reference form")
    boundary = str(contract.get("claim_boundary", ""))
    if "unknown" not in boundary or "starts no workflow" not in boundary:
        problems.append("claim_boundary must state unknown semantics and the absence of a runtime")
    for hit in frozen_hits(json.dumps(contract, ensure_ascii=False)):
        problems.append(f"contract freezes a {hit}")
    if "configuration_fields" in contract and not contract["configuration_fields"].get("fields"):
        problems.append("configuration_fields.fields is empty")
    return problems


def _required(contract: dict[str, Any], state: str) -> list[str]:
    declared = next((s.get("required_evidence", []) for s in contract["states"] if s.get("name") == state), [])
    return list(dict.fromkeys(REQUIRED_EVIDENCE[state] + list(declared)))


def _missing(contract: dict[str, Any], state: str, evidence: dict[str, Any]) -> list[str]:
    found = []
    for field in _required(contract, state):
        if field not in evidence:
            found.append(f"E_MISSING_EVIDENCE:{state}.{field}")
            continue
        value = evidence[field]
        if (state, field) in EMPTY_LIST_OK and isinstance(value, list):
            continue
        if (state, field) in NULL_OK and value is None:
            continue
        if not present(value) and not (isinstance(value, bool) and FIELD_TYPES.get(state, {}).get(field) == "bool"):
            found.append(f"E_MISSING_EVIDENCE:{state}.{field}")
    return found


def _types(state: str, evidence: dict[str, Any]) -> list[str]:
    return [
        f"E_TYPE:{state}.{field}"
        for field, spec in FIELD_TYPES[state].items()
        if field in evidence and not type_ok(evidence[field], spec)
    ]


def _get(evidence: dict[str, Any], dotted: str) -> Any:
    node: Any = evidence
    for part in dotted.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def _check_scope(scope: Any, contract: dict[str, Any], code: str, problems: list[str]) -> None:
    if not isinstance(scope, dict):
        problems.append(code)
        return
    if any(not isinstance(scope.get(field), str) or not scope.get(field) for field in contract["scope_fields"]) \
            or scope.get("surface") not in contract["enums"]["surface"]:
        problems.append(code)


def _check_archival(item: dict[str, Any], contract: dict[str, Any], executed_seen: datetime | None,
                    corrected_seen: datetime | None, problems: list[str]) -> None:
    if any(field not in item for field in contract["archival_fields"]) \
            or item.get("action") not in contract["enums"]["archival_action"]:
        problems.append("E_ARCHIVAL_FIELDS")
        return
    archive = item["action"] == "archive"
    checks_raw = item["reader_checks"]
    if not isinstance(checks_raw, list) or any(not isinstance(c, dict) for c in checks_raw):
        problems.append("E_TYPE:corrected.archival.reader_checks")
        return
    checks = checks_raw
    valid = [c for c in checks if all(f in c for f in contract["reader_check_fields"])
             and c.get("kind") in contract["enums"]["reader_kind"] and isinstance(c.get("active"), bool)
             and isinstance(c.get("ref"), str) and c.get("ref") and parse_time(c.get("checked_at")) is not None]
    if archive:
        if not checks or len(valid) != len(checks):
            problems.append("E_ARCHIVE_UNCHECKED")
        else:
            kinds = {c["kind"] for c in valid}
            if kinds != set(contract["enums"]["reader_kind"]):
                problems.append("E_ARCHIVE_CHECK_KINDS")
            if any(c["active"] for c in valid):
                problems.append("E_ARCHIVE_ACTIVE_READER")
        archived = item.get("archived_at")
        if not is_utc(archived):
            problems.append("E_ARCHIVE_TIME")
    else:
        archived = None
    archived_at = parse_time(archived) if archive and is_utc(archived) else None
    for check in valid:
        stamp = parse_time(check["checked_at"])
        if (executed_seen is not None and stamp < executed_seen) \
                or (archived_at is not None and stamp > archived_at) \
                or (corrected_seen is not None and stamp > corrected_seen):
            problems.append("E_ARCHIVE_ORDER:checked_at")
    if archived_at is not None and corrected_seen is not None and archived_at > corrected_seen:
        problems.append("E_ARCHIVE_ORDER:archived_at")


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
    observed: dict[str, datetime] = {}
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
        else:
            observed[state] = stamp
            if last_time is not None and stamp < last_time:
                problems.append(f"E_TIME_ORDER:{state}")
            last_time = stamp if last_time is None or stamp > last_time else last_time
        problems += _missing(contract, state, evidence)
        problems += _types(state, evidence)
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

    # event timestamps: format, not after the entry, ordered along the chain
    event_times: list[tuple[str, datetime]] = []
    for state, field in TIME_ORDER:
        if state not in by_state:
            continue
        raw = _get(by_state[state], field)
        if raw is None:
            continue  # missing is reported by E_MISSING_EVIDENCE
        stamp = parse_time(raw)
        if stamp is None:
            problems.append(f"E_EVENT_TIME:{state}.{field}")
            continue
        if state in observed and stamp > observed[state]:
            problems.append(f"E_EVENT_AFTER_OBSERVED:{state}.{field}")
        event_times.append((f"{state}.{field}", stamp))
    for (left_name, left), (right_name, right) in zip(event_times, event_times[1:]):
        if right < left:
            problems.append(f"E_EVENT_ORDER:{right_name}<{left_name}")
    if "trigger_planned" in by_state and "next_due_at" in by_state["trigger_planned"] \
            and parse_time(by_state["trigger_planned"]["next_due_at"]) is None:
        problems.append("E_EVENT_TIME:trigger_planned.next_due_at")

    # trigger: the interval is only a reference to configuration, in a form that is no time value
    trigger = by_state.get("trigger_planned")
    if trigger is not None:
        ref = trigger.get("interval_ref")
        if "interval_ref" in trigger:
            if not isinstance(ref, str) or INTERVAL_REF_RE.fullmatch(ref) is None:
                problems.append("E_INTERVAL_REF")
            if isinstance(ref, str) and frozen_hits(ref):
                problems.append("E_FROZEN_INTERVAL")
        if "marker_source" in trigger and trigger.get("marker_source") not in contract["enums"]["marker_source"]:
            problems.append("E_MARKER_SOURCE")

    # task read-back
    task = by_state.get("task_created")
    if task is not None:
        if task.get("readback_verified") is not True or not present(task.get("readback_ref")) \
                or not is_sha(task.get("readback_sha256")):
            problems.append("E_READBACK")

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
        for file in dict_items(corrected.get("files")):
            before, after = file.get("before_sha256"), file.get("after_sha256")
            if not (is_sha(before) and is_sha(after)):
                problems.append("E_HASH")
            elif before == after:
                problems.append("E_HASH_UNCHANGED")
            if not present(file.get("path")):
                problems.append("E_HASH")
        if isinstance(corrected.get("files"), list) and any(not isinstance(f, dict) for f in corrected["files"]):
            problems.append("E_TYPE:corrected.files[]")
        if isinstance(corrected.get("differences"), list):
            differences = corrected["differences"]
            if any(not isinstance(d, dict) for d in differences):
                problems.append("E_TYPE:corrected.differences[]")
        for diff in dict_items(differences):
            if any(not present(diff.get(field)) for field in contract["difference_fields"]):
                problems.append("E_DIFFERENCE_FIELDS")
                continue
            _check_scope(diff["scope"], contract, "E_DIFFERENCE_SCOPE", problems)
        archival = corrected.get("archival")
        if isinstance(archival, list):
            for item in archival:
                if not isinstance(item, dict):
                    problems.append("E_TYPE:corrected.archival[]")
                    continue
                _check_archival(item, contract, observed.get("executed"), observed.get("corrected"), problems)
        open_requirements = corrected.get("open_requirements")
        if isinstance(open_requirements, list):
            for req in open_requirements:
                if not isinstance(req, dict):
                    problems.append("E_TYPE:corrected.open_requirements[]")
                    continue
                task_id = req.get("task_id")
                if any(not isinstance(req.get(f), str) or not req.get(f) for f in ("statement", "source")) \
                        or not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1:
                    problems.append("E_REQUIREMENT_NO_TASK")

    reviewed = by_state.get("reviewed")
    if reviewed is not None and executed is not None:
        if reviewed.get("reviewer_id") == executed.get("author_id") \
                or reviewed.get("reviewer_instance") == executed.get("author_instance"):
            problems.append("E_SAME_REVIEWER")
        verdicts = reviewed.get("verdicts")
        if isinstance(verdicts, list):
            if any(not isinstance(v, dict) for v in verdicts):
                problems.append("E_TYPE:reviewed.verdicts[]")
            items = dict_items(verdicts)
            indices = [v.get("difference_index") for v in items]
            if len(items) != len(verdicts) \
                    or any(v.get("verdict") not in contract["enums"]["verdict"] for v in items) \
                    or any(not isinstance(i, int) or isinstance(i, bool) for i in indices) \
                    or sorted(indices) != list(range(len(differences))):
                problems.append("E_VERDICTS")

    repaired = by_state.get("repaired")
    if repaired is not None:
        if "reviewed" not in by_state:
            problems.append("E_REPAIR_NEEDS_REVIEW")
        remeasure = repaired.get("remeasure") if isinstance(repaired.get("remeasure"), dict) else {}
        if remeasure.get("equal") is not True or repaired.get("regression") is not False:
            problems.append("E_REPAIR")
        if any(not present(remeasure.get(field)) for field in contract["remeasure_fields"] if field != "equal") \
                or not is_sha(remeasure.get("measurement_sha256")):
            problems.append("E_MEASUREMENT")
        else:
            _check_scope(remeasure.get("scope"), contract, "E_MEASUREMENT", problems)
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
