"""Prepare exact detached-checkout K9 sources or reject incomplete JUnit evidence.

Only source bytes and checkout metadata are read. Product code is not executed.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.parity_probes import bach_k9_dbsync_remaining_probe as probe  # noqa: E402


def _regular(path: Path) -> bytes:
    path = probe.safe_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise probe.ProbeRefusal("independent-regular-file-required")
    return path.read_bytes()


def prepare(checkouts: dict[str, Path], destination: Path) -> dict:
    required = probe.contract()["sources"]
    if set(checkouts) != set(required):
        raise probe.ProbeRefusal("all-four-explicit-checkouts-required")
    destination = probe.safe_path(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise probe.ProbeRefusal("fresh-output-and-existing-parent-required")
    result = {"schema": "ellmos.k9.ci-source-manifest.v1", "rc": 0, "sources": {}}
    for name, expected in required.items():
        root = probe.safe_path(checkouts[name])
        if root == destination or root in destination.parents:
            raise probe.ProbeRefusal("output-inside-source-checkout-refused")
        git = probe.safe_path(root / ".git")
        if not git.is_dir():
            raise probe.ProbeRefusal("detached-full-checkout-required")
        head = _regular(git / "HEAD").decode("ascii").strip()
        if head != expected["commit"]:
            raise probe.ProbeRefusal("detached-checkout-pin-mismatch")
        files = {}
        for relative, wanted in expected["files"].items():
            data = _regular(root / relative)
            actual = probe.digest(data.replace(b"\r\n", b"\n"))
            if actual != wanted:
                raise probe.ProbeRefusal("source-closure-bytes-mismatch")
            files[relative] = actual
        result["sources"][name] = {"root": str(root), "commit": head, "files": files}
    # No output is created until every checkout and all 14 source hashes pass.
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return result


def check_junit(path: Path) -> dict:
    data = _regular(path)
    if len(data) > 8 * 1024 * 1024:
        raise probe.ProbeRefusal("junit-size-limit")
    root = ET.fromstring(data)
    if root.tag not in {"testsuites", "testsuite"}:
        raise probe.ProbeRefusal("junit-root-required")
    cases = list(root.iter("testcase"))
    suites = [item for item in root.iter("testsuite") if list(item.findall("testcase"))]
    declared = sum(int(item.attrib["tests"]) for item in suites)
    reference = json.loads(_regular(ROOT / "tests/fixtures/k9_remaining/ci-case-ids.v1.json"))
    if (reference.get("schema") != "ellmos.k9.ci-case-ids.v1"
            or reference.get("test_source_path") != "tests/test_bach_k9_dbsync_remaining_contract.py"
            or reference.get("test_source_sha256") != "b2af003597d76eb1ab65b66d38321a95fcabccd5f9ebd277cf068b6e389ec909"
            or reference.get("tests") != 146):
        raise probe.ProbeRefusal("fixed-k9-case-contract-required")
    expected = [(item["classname"], item["name"]) for item in reference["cases"]]
    if (len(expected) != 146 or len(set(expected)) != 146
            or any(cls != "tests.test_bach_k9_dbsync_remaining_contract"
                   or not isinstance(name, str) or not name for cls, name in expected)):
        raise probe.ProbeRefusal("unique-complete-k9-case-contract-required")
    source = _regular(ROOT / reference["test_source_path"])
    if probe.digest(source.replace(b"\r\n", b"\n")) != reference["test_source_sha256"]:
        raise probe.ProbeRefusal("case-contract-source-mismatch")
    actual = [(case.attrib.get("classname"), case.attrib.get("name")) for case in cases]
    if (declared != len(cases) or len(actual) != len(set(actual))
            or set(actual) != set(expected)):
        raise probe.ProbeRefusal("exact-k9-case-identities-required")
    if any(list(root.iter(tag)) for tag in ("skipped", "failure", "error")):
        raise probe.ProbeRefusal("k9-errors-failures-or-skips-refused")
    if any(int(item.attrib.get(key, "0")) for item in root.iter("testsuite")
           for key in ("errors", "failures", "skipped")):
        raise probe.ProbeRefusal("k9-nonzero-junit-counters-refused")
    return {"rc": 0, "tests": len(cases), "errors": 0, "failures": 0, "skipped": 0,
            "junit_sha256": probe.digest(data), "parity_accepted": False,
            "host_or_runtime_acceptance": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest")
    for name in ("bach-old", "bach-current", "ocean", "carrier"):
        manifest.add_argument("--" + name, type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    junit = commands.add_parser("junit")
    junit.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            checkouts = {name: getattr(args, name.replace("-", "_"))
                         for name in ("bach-old", "bach-current", "ocean", "carrier")}
            result = prepare(checkouts, args.output)
            summary = {"rc": 0, "sources": {name: value["commit"]
                       for name, value in result["sources"].items()},
                       "source_files": sum(len(value["files"])
                       for value in result["sources"].values())}
        else:
            summary = check_junit(args.path)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except (probe.ProbeRefusal, OSError, ValueError, KeyError, ET.ParseError) as error:
        print(json.dumps({"rc": 2, "error_class": type(error).__name__,
                          "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
