#!/usr/bin/env python3
"""Check the plugin-activation contract against synthetic activation records.

The checker verifies:
  * the contract document itself (shape, states, error codes; mandatory evidence the
    contract may extend but never weaken; no frozen hosts or fixed paths)
  * every positive fixture document is accepted without problems
  * every negative fixture document is rejected with (at least) the expected problem codes

A single document can also be checked with ``--document``.

Exit code 0 means every check passed. The status string deliberately says
"not-live-evidence": the checker proves contract and fixture conformance, not that any
host or consumer currently supports activation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DOC_SCHEMA = "ellmos.open-ocean-plugin-activation-record.v1"
STATES = ("plugged", "unplugged", "pending_restart", "unknown", "error")
KEY_FIELDS = ("consumer", "host", "plugin_id", "scope")
STEPS = ("plan", "lock_host_check", "backup", "native_write", "readback")
SCOPES = ("user", "project", "local", "none")
READBACK_VALUES = ("enabled", "disabled")
ROLLBACK = ("restored", "not_needed", "failed")
FLAG_SOURCES = ("plugin_sockets", "db_flag", "socket_flag")
DEFAULT_SOURCES = ("default", "default_true", "absence", "fallback")
# The checker's own minimum: a contract may add evidence, never remove any of these.
MINIMUM_EVIDENCE = {
    "plugged": ["source", "observed_at", "config_revision", "readback_ref", "readback_value"],
    "unplugged": ["source", "observed_at", "config_revision", "readback_ref", "readback_value"],
    "pending_restart": ["source", "observed_at", "config_revision", "readback_ref", "readback_value",
                        "requested_at", "runtime_active"],
    "unknown": ["reason_code", "observed_at"],
    "error": ["request_id", "error_code", "last_evidence"],
}
PATTERNS = {
    "consumer": re.compile(r"[a-z][a-z0-9_-]{1,40}"),
    "plugin_id": re.compile(r"[A-Za-z0-9][A-Za-z0-9._@/-]{0,120}"),
    "source": re.compile(r"[a-z][a-z0-9_]{1,60}"),
}
SHA_RE = re.compile(r"[0-9a-f]{64}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3}|\.\d{6})?(Z|[+-]\d{2}:\d{2})")
FROZEN_RE = re.compile(r"[A-Za-z]:\\|/Users/|/home/|ASUS-GEI|WORKSTATION-LG|mac-studio|\bhttps?://", re.I)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or TIME_RE.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if contract.get("schema") != "ellmos.open-ocean-plugin-activation.v1":
        problems.append("contract schema is wrong")
    states = {s.get("name"): s for s in contract.get("states", []) if isinstance(s, dict)}
    if set(states) != set(STATES):
        problems.append(f"contract states differ from {list(STATES)}")
    for name, minimum in MINIMUM_EVIDENCE.items():
        have = states.get(name, {}).get("required_evidence", [])
        for field in minimum:
            if field not in have:
                problems.append(f"contract weakens {name}: missing required evidence {field}")
    if contract.get("toggle_steps") != list(STEPS):
        problems.append("contract weakens toggle_steps: not the ordered sequence")
    codes = contract.get("error_codes", {})
    for code in sorted(CODES):
        if not present(codes.get(code)):
            problems.append(f"contract lacks a rule text for {code}")
    text = json.dumps({k: contract.get(k) for k in ("rules", "error_codes", "claim_boundary")})
    if FROZEN_RE.search(text):
        problems.append("contract freezes a host, path or URL in its rule text")
    for forbidden in FLAG_SOURCES:
        if forbidden not in contract.get("forbidden_sources", {}).get("flag_only", []):
            problems.append(f"contract weakens forbidden_sources: {forbidden}")
    for forbidden in DEFAULT_SOURCES:
        if forbidden not in contract.get("forbidden_sources", {}).get("default_or_absence", []):
            problems.append(f"contract weakens forbidden_sources: {forbidden}")
    return problems


CODES = {
    "E_SCHEMA", "E_TYPE", "E_ENUM", "E_KEY", "E_STATE", "E_MISSING_EVIDENCE", "E_HASH", "E_TIME",
    "E_NO_READBACK", "E_FLAG_ONLY", "E_DEFAULT_TRUE", "E_FOREIGN_HOST_WRITE", "E_MISMATCH_NO_ERROR",
    "E_PENDING_RUNTIME", "E_RUNTIME_NO_REF", "E_NO_BACKUP", "E_TOGGLE_ORDER", "E_UNKNOWN_NEEDS_REASON",
    "E_ERROR_NO_ROLLBACK",
}


def _key_problems(record: dict[str, Any], out: list[str]) -> None:
    for field in KEY_FIELDS:
        value = record.get(field)
        if not present(value):
            out.append(f"E_KEY:{field}")
        elif not isinstance(value, str):
            out.append(f"E_TYPE:{field}")
    for field in ("consumer", "plugin_id"):
        value = record.get(field)
        if isinstance(value, str) and PATTERNS[field].fullmatch(value) is None:
            out.append(f"E_ENUM:{field}")
    if isinstance(record.get("scope"), str) and record["scope"] not in SCOPES:
        out.append("E_ENUM:scope")


def _check_write(record: dict[str, Any], state: str, evidence: dict[str, Any], out: list[str]) -> bool:
    """Validate the optional write block; return True when a native write happened."""
    write = record.get("write")
    if write is None:
        return False
    if not isinstance(write, dict):
        out.append("E_TYPE:write")
        return False
    steps = write.get("steps")
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        out.append("E_TYPE:write.steps")
        return False
    if write.get("writer_host") != record.get("host"):
        out.append("E_FOREIGN_HOST_WRITE")
    expected = list(STEPS) if state != "error" else list(STEPS[: len(steps)])
    if steps != expected or (state == "error" and not steps):
        out.append("E_TOGGLE_ORDER")
    wrote = "native_write" in steps
    if wrote and (not present(write.get("backup_ref")) or "backup" not in steps[: steps.index("native_write")]):
        out.append("E_NO_BACKUP")
    requested, readback = write.get("requested_value"), evidence.get("readback_value")
    if state != "error" and requested is not None and present(readback) and requested != readback:
        out.append("E_MISMATCH_NO_ERROR")
    if state == "error" and wrote:
        if not present(write.get("backup_ref")) or write.get("rollback_outcome") not in ROLLBACK \
                or not present(evidence.get("last_evidence")):
            out.append("E_ERROR_NO_ROLLBACK")
    return wrote


def validate_record(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return ["E_TYPE:record"]
    out: list[str] = []
    _key_problems(record, out)
    state = record.get("state")
    if state not in STATES:
        return out + ["E_STATE"]
    evidence = record.get("evidence")
    if not isinstance(evidence, dict):
        return out + ["E_TYPE:evidence"]

    if state == "unknown":
        if not present(evidence.get("reason_code")):
            out.append("E_UNKNOWN_NEEDS_REASON")
        if "readback_value" in evidence:
            out.append("E_UNKNOWN_NEEDS_REASON")
    else:
        for field in MINIMUM_EVIDENCE[state]:
            if field == "runtime_active":  # null is the required value, so presence means key present
                if field not in evidence:
                    out.append(f"E_MISSING_EVIDENCE:{field}")
            elif not present(evidence.get(field)):
                out.append(f"E_MISSING_EVIDENCE:{field}")
        if state in ("plugged", "unplugged", "pending_restart"):
            if not present(evidence.get("readback_ref")) or not present(evidence.get("config_revision")):
                out.append("E_NO_READBACK")
            source = evidence.get("source")
            if isinstance(source, str):
                if source in FLAG_SOURCES:
                    out.append("E_FLAG_ONLY")
                elif source in DEFAULT_SOURCES:
                    out.append("E_DEFAULT_TRUE")
                elif PATTERNS["source"].fullmatch(source) is None:
                    out.append("E_ENUM:source")
            if not present(source) or evidence.get("default_applied") is True:
                out.append("E_DEFAULT_TRUE")
            if present(evidence.get("config_revision")) and not (
                    isinstance(evidence["config_revision"], str) and SHA_RE.fullmatch(evidence["config_revision"])):
                out.append("E_HASH")
            value = evidence.get("readback_value")
            if present(value) and value not in READBACK_VALUES:
                out.append("E_ENUM:readback_value")
            elif present(value) and (state == "plugged") != (value == "enabled") and state != "pending_restart":
                out.append("E_MISMATCH_NO_ERROR")
    _check_write(record, state, evidence, out)

    active = evidence.get("runtime_active")
    if state == "pending_restart" and active is not None:
        out.append("E_PENDING_RUNTIME")
    elif active is not None and not isinstance(active, bool):
        out.append("E_TYPE:runtime_active")
    elif isinstance(active, bool) and not present(evidence.get("runtime_ref")):
        out.append("E_RUNTIME_NO_REF")

    for field in ("observed_at", "requested_at"):
        if field in evidence and parse_time(evidence[field]) is None:
            out.append(f"E_TIME:{field}")
    seen, asked = parse_time(evidence.get("observed_at")), parse_time(evidence.get("requested_at"))
    if seen and asked and asked > seen:
        out.append("E_TIME:order")
    return out


def validate_document(doc: Any) -> list[str]:
    if not isinstance(doc, dict) or doc.get("schema") != DOC_SCHEMA or not isinstance(doc.get("records"), list):
        return ["E_SCHEMA"]
    out: list[str] = []
    keys: set[tuple] = set()
    for index, record in enumerate(doc["records"]):
        out += validate_record(record)
        if isinstance(record, dict):
            key = tuple(record.get(f) for f in KEY_FIELDS)
            if all(isinstance(k, str) for k in key):
                if key in keys:
                    out.append("E_KEY:duplicate")
                keys.add(key)
    return out


def run_fixtures(contract: dict[str, Any], repo_root: Path) -> list[str]:
    problems: list[str] = []
    directory = repo_root / contract["fixtures"]["directory"]
    expected = json.loads((repo_root / contract["fixtures"]["expected"]).read_text(encoding="utf-8"))
    for name in expected["positive"]:
        found = validate_document(json.loads((directory / name).read_text(encoding="utf-8")))
        if found:
            problems.append(f"positive fixture rejected: {name}: {found}")
    for name, codes in expected["negative"].items():
        found = validate_document(json.loads((directory / name).read_text(encoding="utf-8")))
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
    parser.add_argument("--contract", default="architecture/plugin-activation.v1.json")
    parser.add_argument("--document", default=None, help="check one record document instead of the fixtures")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = repo_root / contract_path
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    problems = validate_contract(contract)
    if args.document:
        problems += validate_document(json.loads(Path(args.document).read_text(encoding="utf-8")))
    else:
        problems += run_fixtures(contract, repo_root)

    out = {
        "schema": "ellmos.open-ocean-plugin-activation-check.v1",
        "status": "pass-contract-and-fixtures-not-live-evidence" if not problems else "fail",
        "problems": problems,
    }
    print(json.dumps(out, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
