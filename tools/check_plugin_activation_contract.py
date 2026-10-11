#!/usr/bin/env python3
"""Check the plugin-activation contract against synthetic activation records.

The checker verifies:
  * the contract document itself: the normative sections (states, enums, patterns, field lists, rules, error
    codes) are pinned by SHA-256, so a removed, reversed, loosened or reworded rule is a problem; no host,
    path or URL appears anywhere in the contract
  * every positive fixture document is accepted without problems
  * every negative fixture document is rejected with (at least) the expected problem codes; every error code
    has exactly one fixture neg_<code>.json that raises exactly that code

A single document can also be checked with ``--document``.

Exit code 0 means every check passed. The status string deliberately says
"not-live-evidence": the checker proves contract and fixture conformance, not that any
host or consumer currently supports activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DOC_SCHEMA = "ellmos.open-ocean-plugin-activation-record.v1"
STATES = ("plugged", "unplugged", "pending_restart", "unknown", "error")
KEY_FIELDS = ("consumer", "host", "plugin_id", "scope")
RECORD_REQUIRED = ("consumer", "host", "plugin_id", "scope", "state", "evidence")
RECORD_OPTIONAL = ("write", "extensions")
STEPS = ("plan", "lock_host_check", "backup", "native_write", "readback")
SCOPES = ("user", "project", "local", "none")
READBACK_VALUES = ("enabled", "disabled")
ROLLBACK = ("restored", "not_needed", "failed")
PHASES = ("read", "write")
FLAG_SOURCES = ("plugin_sockets", "db_flag", "socket_flag")
DEFAULT_SOURCES = ("default", "default_true", "absence", "fallback")
_READBACK = ["source", "observed_at", "config_revision", "readback_ref", "readback_at", "readback_sha256", "readback_value"]
# state -> (required, optional) evidence fields
EVIDENCE = {
    "plugged": (_READBACK, ["runtime_active", "runtime_ref", "default_applied"]),
    "unplugged": (_READBACK, ["runtime_active", "runtime_ref", "default_applied"]),
    "pending_restart": (_READBACK + ["runtime_active"], ["runtime_ref", "default_applied"]),
    "unknown": (["reason_code", "observed_at"], []),
    "error": (["request_id", "error_code", "last_evidence", "phase"], ["observed_at", "readback_value"]),
}
WRITE_REQUIRED = ("requested_value", "writer_host", "requested_at", "steps", "reached_step")
WRITE_AFTER_NATIVE = ("backup_ref", "native_write_at")
PATTERNS = {  # ASCII identifiers; fullmatch only
    "consumer": re.compile(r"[a-z][a-z0-9_-]{1,40}"),
    "host": re.compile(r"[a-z0-9][a-z0-9._-]{0,62}"),
    "plugin_id": re.compile(r"[A-Za-z0-9][A-Za-z0-9._@/-]{0,120}"),
    "source": re.compile(r"[a-z][a-z0-9_]{1,60}"),
    "reason_code": re.compile(r"[a-z][a-z0-9_]{1,60}"),
}
SHA_RE = re.compile(r"[0-9a-f]{64}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3}|\.\d{6})?(Z|[+-]\d{2}:\d{2})")
# What the contract and the fixtures must not freeze (this is all the checker recognizes): drive paths with / or \, UNC
# paths, /Users/ and /home/ prefixes, http(s) URLs and the three named hosts.
FROZEN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"
    r"|\\\\[^\\\s]+\\[^\\\s]+"
    r"|/Users/|/home/|\bhttps?://|ASUS-GEI|WORKSTATION-LG|mac-studio", re.I)
TEXT_FIELDS = ("readback_ref", "request_id", "error_code", "last_evidence", "runtime_ref")
CODES = {
    "E_SCHEMA", "E_TYPE", "E_ENUM", "E_KEY", "E_STATE", "E_UNKNOWN_FIELD", "E_MISSING_EVIDENCE", "E_HASH", "E_TIME",
    "E_NO_READBACK", "E_REVISION_MISMATCH", "E_STALE_READBACK", "E_ORDER", "E_FLAG_ONLY", "E_DEFAULT_TRUE", "E_FOREIGN_HOST_WRITE",
    "E_MISMATCH_NO_ERROR", "E_PENDING_RUNTIME", "E_RUNTIME_NO_REF", "E_NO_BACKUP", "E_TOGGLE_ORDER", "E_REACHED_STEP",
    "E_WRITE_REQUIRED", "E_UNKNOWN_NEEDS_REASON", "E_ERROR_NO_ROLLBACK",
}
# SHA-256 of the canonical JSON (sorted keys, compact) of each normative contract section. An edit of any of these
# sections is a new contract version: change the version and these pins together.
NORMATIVE_SHA256 = {
    "claim_boundary": "bba13f8e64d33edf2dcc562d413ad2647ce57879af7af88c2af753acb2d3f9d8",
    "key_fields": "41f9440ca166c5a2452ed72fa13e647bdcc3b73aae4b33876b7ea392b25d7149",
    "record_fields": "f37a69eeda91aee2343dce0e7cadbfd2387353527ade5f03fe9dc23022c1acd3",
    "states": "d4201d2b8709eadd2ded5168a2c4e1bc873613e1de4516b8f2cce94f2da41dd4",
    "enums": "b978e94337be726d0aa2c78577b9e92787c5312fcc2da90e2625505e358d1a06",
    "patterns": "c0daf74caa890bf3812b1ce768c4abce6122cc48ceedb432756f53bd7aaf11d9",
    "known_values": "5572b88ce42cde2ba03ea2038a9f7a7bc6822aa2c8b9cade580db515ab62496b",
    "forbidden_sources": "9ec01378d56625f8da01da5fb373f10bb78e8dc7f8f421209f1ac2c10d90da45",
    "toggle_steps": "18815bc9d7a4e645c23b4a79c93c713c2c8ec2a579733fdb8f247fae37667632",
    "write_fields": "ae0b169cb114f892fcca752e757a44cd0fadcf3e1daa51bd7ec2bc946ca716d5",
    "error_codes": "7c8745941257a6c25cb1e9a09d5707af214f3ebc595495562e7feeedca252f2f",
    "rules": "ba17ef1d93152ef7733b048578d127df7fc3b46152417094ff018afca93cbc1f",
}


def section_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def walk_strings(node: Any):
    """Every string in a JSON value (keys and values), unescaped, so backslashes are real backslashes."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(key)
            yield from walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_strings(value)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or TIME_RE.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def is_text(value: Any) -> bool:
    """Non-empty string without surrounding whitespace or control characters."""
    return isinstance(value, str) and value != "" and value == value.strip() and value.isprintable()


def ident_ok(field: str, value: Any) -> bool:
    return isinstance(value, str) and value.isascii() and PATTERNS[field].fullmatch(value) is not None


def validate_contract(contract: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if contract.get("schema") != "ellmos.open-ocean-plugin-activation.v1":
        problems.append("contract schema is wrong")
    if contract.get("normative_sections") != list(NORMATIVE_SHA256):
        problems.append("contract weakens normative_sections: the pinned section list changed")
    for name, pinned in NORMATIVE_SHA256.items():
        if name not in contract:
            problems.append(f"contract weakens {name}: section removed")
        elif section_hash(contract[name]) != pinned:
            problems.append(f"contract weakens {name}: normative section differs from the pinned v1 text")
    texts = contract.get("error_codes") if isinstance(contract.get("error_codes"), dict) else {}
    for code in sorted(CODES):
        if not is_text(texts.get(code)):
            problems.append(f"contract lacks a rule text for {code}")
    if any(FROZEN_RE.search(text) for text in walk_strings(contract)):
        problems.append("contract freezes a host, path or URL")
    return problems


def _check_write(record: dict[str, Any], state: str, evidence: dict[str, Any], out: list[str]) -> dict[str, datetime | None]:
    times: dict[str, datetime | None] = {}
    write = record.get("write")
    if write is None:  # absent and null are the same; states that need a write block report E_WRITE_REQUIRED
        return times
    if not isinstance(write, dict):
        out.append("E_TYPE:write")
        return times
    allowed = set(WRITE_REQUIRED) | set(WRITE_AFTER_NATIVE) | ({"rollback_outcome"} if state == "error" else set())
    for field in sorted(set(write) - allowed):
        out.append(f"E_UNKNOWN_FIELD:write.{field}")
    if "requested_value" not in write:
        out.append("E_MISSING_EVIDENCE:write.requested_value")
    elif write["requested_value"] not in READBACK_VALUES:
        out.append("E_ENUM:write.requested_value")
    if "writer_host" not in write:
        out.append("E_MISSING_EVIDENCE:write.writer_host")
    elif not ident_ok("host", write["writer_host"]):
        out.append("E_ENUM:writer_host")
    elif write["writer_host"] != record.get("host"):
        out.append("E_FOREIGN_HOST_WRITE")

    if "requested_at" not in write:
        out.append("E_MISSING_EVIDENCE:write.requested_at")
    else:
        times["requested_at"] = parse_time(write["requested_at"])
        if times["requested_at"] is None:
            out.append("E_TIME:write.requested_at")

    steps = write.get("steps")
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        out.append("E_TYPE:write.steps")
        steps = None
    elif not steps or steps != (list(STEPS) if state != "error" else list(STEPS[: len(steps)])):
        out.append("E_TOGGLE_ORDER")
    reached = write.get("reached_step")
    if reached not in STEPS or (steps and reached != steps[-1]):
        out.append("E_REACHED_STEP")
    if steps and "native_write" in steps:
        if not is_text(write.get("backup_ref")):
            out.append("E_NO_BACKUP")
        if "native_write_at" not in write:
            out.append("E_MISSING_EVIDENCE:write.native_write_at")
        else:
            times["native_write_at"] = parse_time(write["native_write_at"])
            if times["native_write_at"] is None:
                out.append("E_TIME:write.native_write_at")
        if state == "error" and write.get("rollback_outcome") not in ROLLBACK:
            out.append("E_ERROR_NO_ROLLBACK")
    requested, readback = write.get("requested_value"), evidence.get("readback_value")
    if state != "error" and requested in READBACK_VALUES and readback in READBACK_VALUES and requested != readback:
        out.append("E_MISMATCH_NO_ERROR")
    return times


def validate_record(record: Any) -> list[str]:
    if not isinstance(record, dict):
        return ["E_TYPE:record"]
    out: list[str] = []
    for field in sorted(set(record) - set(RECORD_REQUIRED) - set(RECORD_OPTIONAL)):
        out.append(f"E_UNKNOWN_FIELD:{field}")
    if "extensions" in record and not isinstance(record["extensions"], dict):
        out.append("E_TYPE:extensions")
    for field in KEY_FIELDS:
        if field not in record or record[field] in (None, ""):
            out.append(f"E_KEY:{field}")
        elif not isinstance(record[field], str):
            out.append(f"E_TYPE:{field}")
        elif field == "scope":
            if record[field] not in SCOPES:
                out.append("E_ENUM:scope")
        elif not ident_ok(field, record[field]):
            out.append(f"E_ENUM:{field}")
    state = record.get("state")
    if state not in STATES:
        return out + ["E_STATE"]
    evidence = record.get("evidence")
    if not isinstance(evidence, dict):
        return out + ["E_TYPE:evidence"]

    required, optional = EVIDENCE[state]
    for field in sorted(set(evidence) - set(required) - set(optional)):
        out.append(f"E_UNKNOWN_FIELD:evidence.{field}")
    readback_missing = False
    for field in required:
        if field in evidence:
            continue
        if field in ("readback_ref", "readback_at", "readback_sha256", "config_revision"):
            readback_missing = True
        elif field == "source":
            out.append("E_DEFAULT_TRUE")  # an absent source is the default-true error, not just a missing field
        elif field == "reason_code":
            out.append("E_UNKNOWN_NEEDS_REASON")
        else:
            out.append(f"E_MISSING_EVIDENCE:{field}")
    if readback_missing:
        out.append("E_NO_READBACK")

    for field in TEXT_FIELDS:
        if field in evidence and not is_text(evidence[field]):
            out.append(f"E_TYPE:{field}")
    if "reason_code" in evidence and not ident_ok("reason_code", evidence["reason_code"]):
        out.append("E_ENUM:reason_code")
    if "phase" in evidence and evidence["phase"] not in PHASES:
        out.append("E_ENUM:phase")
    if "readback_value" in evidence and evidence["readback_value"] not in READBACK_VALUES:
        out.append("E_ENUM:readback_value")
    for field in ("config_revision", "readback_sha256"):
        if field in evidence and not (isinstance(evidence[field], str) and SHA_RE.fullmatch(evidence[field])):
            out.append("E_HASH")
    if "default_applied" in evidence:
        if type(evidence["default_applied"]) is not bool:
            out.append("E_TYPE:default_applied")
        elif evidence["default_applied"]:
            out.append("E_DEFAULT_TRUE")
    if "source" in evidence:
        source = evidence["source"]
        if not isinstance(source, str):
            out.append("E_TYPE:source")
        elif source in FLAG_SOURCES:
            out.append("E_FLAG_ONLY")
        elif source in DEFAULT_SOURCES:
            out.append("E_DEFAULT_TRUE")
        elif not ident_ok("source", source):
            out.append("E_ENUM:source")

    if state == "unknown" and "readback_value" in evidence:
        out.append("E_UNKNOWN_NEEDS_REASON")
    if state in ("plugged", "unplugged", "pending_restart"):
        a, b = evidence.get("config_revision"), evidence.get("readback_sha256")
        if all(isinstance(x, str) and SHA_RE.fullmatch(x) for x in (a, b)) and a != b:
            out.append("E_REVISION_MISMATCH")
        value = evidence.get("readback_value")
        if state != "pending_restart" and value in READBACK_VALUES and (state == "plugged") != (value == "enabled"):
            out.append("E_MISMATCH_NO_ERROR")
        if state == "pending_restart" and record.get("write") is None:
            out.append("E_WRITE_REQUIRED")
    if state == "error" and evidence.get("phase") == "write" and record.get("write") is None:
        out.append("E_WRITE_REQUIRED")

    active = evidence.get("runtime_active")
    if state == "pending_restart" and active is not None:
        out.append("E_PENDING_RUNTIME")
    elif active is not None and type(active) is not bool:
        out.append("E_TYPE:runtime_active")
    elif type(active) is bool and "runtime_ref" not in evidence:
        out.append("E_RUNTIME_NO_REF")

    times = _check_write(record, state, evidence, out)
    for field in ("readback_at", "observed_at"):
        if field in evidence:
            times[field] = parse_time(evidence[field])
            if times[field] is None:
                out.append(f"E_TIME:{field}")
    # strict order requested_at < native_write_at < readback_at, then readback_at <= observed_at. A read-back that is not
    # strictly after the write (earlier or equal) is stale; an unordered request/write pair or a read-back after the
    # observation is E_ORDER.
    requested, native, readback, observed = (times.get(k) for k in ("requested_at", "native_write_at", "readback_at", "observed_at"))
    if requested and native and not requested < native:
        out.append("E_ORDER")
    for before in (requested, native):
        if before and readback and not before < readback:
            out.append("E_STALE_READBACK")
    if readback and observed and observed < readback:
        out.append("E_ORDER")
    return list(dict.fromkeys(out))


def validate_document(doc: Any) -> list[str]:
    if not isinstance(doc, dict) or doc.get("schema") != DOC_SCHEMA or not isinstance(doc.get("records"), list):
        return ["E_SCHEMA"]
    out: list[str] = []
    keys: set[tuple] = set()
    for record in doc["records"]:
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
        if name.startswith("neg_e_"):  # the one fixture of a code raises exactly that code
            bare = {item.split(":")[0] for item in found}
            if bare != set(codes):
                problems.append(f"negative fixture {name} raises {sorted(bare)} instead of exactly {sorted(codes)}")
    listed = set(expected["positive"]) | set(expected["negative"])
    on_disk = {p.name for p in directory.glob("*.json") if p.name != "expected.json"}
    if listed != on_disk:
        problems.append(f"fixture list and directory differ: {sorted(listed ^ on_disk)}")
    for code in sorted(CODES):
        names = [n for n, c in expected["negative"].items() if n.startswith("neg_e_") and c == [code]]
        if names != [f"neg_{code.lower()}.json"]:
            problems.append(f"{code} needs exactly one fixture neg_{code.lower()}.json, found {names}")
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
