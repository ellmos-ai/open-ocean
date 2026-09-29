"""Swarm radar live map checker for slice S9 (BACH task 1520).

Schema-level alignment checker for the swarm-radar-live-map artifact.
It validates the contract shape and hold, the three synthetic host
reports, cross-host reconciliation, the double-agent prohibition, the
lease-target collision avoidance rule and the expected live map.

The checker validates schema and fixture conformance only. It does not
check equivalence with a live BACH swarm or a live lease table, and it
performs no live cutover of any BACH, agent or lease runtime.
"""

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_SCHEMA = "ellmos.open-ocean-bach-swarm-radar-live-map.v1"
EXPECTED_REPORT_SCHEMA = "ellmos.open-ocean-swarm-radar-host-report.v1"
EXPECTED_EXPECTED_SCHEMA = (
    "ellmos.open-ocean-swarm-radar-live-map-expected.v1"
)
EXPECTED_RADAR_SCOPE = "swarm-radar-live-map"
EXPECTED_LEASE_MODE = "claim-insert-or-replace"
EXPECTED_STATUS = (
    "swarm-radar-live-map-schema-specified-fixtures-green-no-live-cutover"
)
REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "hold",
    "provenance",
    "radar_scope",
    "hosts",
    "host_report_schema",
    "required_report_fields",
    "agent_fields",
    "lease_fields",
    "lease_mode",
    "collision_avoidance",
    "double_agent_prohibition",
    "reconciliation",
    "fixtures",
    "classification",
    "next_gates",
]
BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
HOST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def load_json(path):
    """Load a JSON file from disk and return the parsed object."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _banned_problems(obj):
    """Detect banned strings inside a serialized JSON object."""
    text = json.dumps(obj, sort_keys=True)
    return [
        f"banned string present: {banned}"
        for banned in BANNED_STRINGS
        if banned in text
    ]


def validate_contract(contract):
    """Validate the contract shape, hold and classification."""
    problems = []
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"]
    if contract.get("schema") != EXPECTED_SCHEMA:
        problems.append(
            f"contract schema mismatch: {contract.get('schema')!r}"
        )
    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")
    hold = contract.get("hold")
    if not isinstance(hold, dict):
        problems.append("contract hold must be a JSON object")
    elif hold.get("bach_mode") != "read-only":
        problems.append(
            f"hold bach_mode mismatch: {hold.get('bach_mode')!r}"
        )
    if contract.get("status") != EXPECTED_STATUS:
        problems.append(
            f"contract status mismatch: {contract.get('status')!r}"
        )
    if contract.get("radar_scope") != EXPECTED_RADAR_SCOPE:
        problems.append(
            f"contract radar_scope mismatch: {contract.get('radar_scope')!r}"
        )
    if contract.get("lease_mode") != EXPECTED_LEASE_MODE:
        problems.append(
            f"contract lease_mode mismatch: {contract.get('lease_mode')!r}"
        )
    if contract.get("host_report_schema") != EXPECTED_REPORT_SCHEMA:
        problems.append(
            "contract host_report_schema mismatch: "
            f"{contract.get('host_report_schema')!r}"
        )
    hosts = contract.get("hosts")
    if not isinstance(hosts, list) or len(hosts) != 3:
        problems.append("contract hosts must be a list of 3 host ids")
    else:
        for host_id in hosts:
            if not isinstance(host_id, str) or not HOST_ID_RE.match(host_id):
                problems.append(
                    f"invalid host id in contract hosts: {host_id!r}"
                )
    fixtures = contract.get("fixtures")
    if not isinstance(fixtures, dict):
        problems.append("contract fixtures must be a JSON object")
    else:
        host_reports = fixtures.get("host_reports")
        if not isinstance(host_reports, list) or len(host_reports) != 3:
            problems.append(
                "fixtures host_reports must be a list of 3 paths"
            )
        else:
            for rel in host_reports:
                if not isinstance(rel, str):
                    problems.append(
                        f"host report path must be a string: {rel!r}"
                    )
        expected = fixtures.get("expected")
        if not isinstance(expected, str):
            problems.append("fixtures expected must be a string path")
    classification = contract.get("classification")
    if not isinstance(classification, dict):
        problems.append("contract classification must be a JSON object")
    elif classification.get("parity") != "not-accepted":
        problems.append(
            "classification parity must be not-accepted: "
            f"{classification.get('parity')!r}"
        )
    problems.extend(_banned_problems(contract))
    return problems


def validate_host_report(report, contract):
    """Validate one synthetic host report against the contract."""
    problems = []
    if not isinstance(report, dict):
        return ["host report must be a JSON object"]
    schema = report.get("schema")
    if schema != contract.get("host_report_schema"):
        problems.append(f"host report schema mismatch: {schema!r}")
    for field in contract.get("required_report_fields", []):
        if field not in report:
            problems.append(f"missing required report field: {field}")
            return problems
    host_id = report.get("host_id")
    if not isinstance(host_id, str) or not HOST_ID_RE.match(host_id):
        problems.append(f"invalid host_id in report: {host_id!r}")
    elif host_id not in contract.get("hosts", []):
        problems.append(f"unknown host_id: {host_id!r}")
    if report.get("radar_scope") != contract.get("radar_scope"):
        problems.append(
            f"radar_scope mismatch on host {host_id}: "
            f"{report.get('radar_scope')!r}"
        )
    agents = report.get("agents")
    if not isinstance(agents, list) or not agents:
        problems.append(f"agents must be a non-empty list on host {host_id}")
    else:
        for agent in agents:
            if not isinstance(agent, dict):
                problems.append(
                    f"agent must be a JSON object on host {host_id}"
                )
                continue
            for field in contract.get("agent_fields", []):
                if field not in agent:
                    problems.append(
                        f"missing agent field on host {host_id}: {field}"
                    )
    leases = report.get("leases")
    if not isinstance(leases, list) or not leases:
        problems.append(f"leases must be a non-empty list on host {host_id}")
    else:
        for lease in leases:
            if not isinstance(lease, dict):
                problems.append(
                    f"lease must be a JSON object on host {host_id}"
                )
                continue
            for field in contract.get("lease_fields", []):
                if field not in lease:
                    problems.append(
                        f"missing lease field on host {host_id}: {field}"
                    )
            if lease.get("lease_mode") != contract.get("lease_mode"):
                problems.append(
                    f"lease_mode mismatch on host {host_id}: "
                    f"{lease.get('lease_mode')!r}"
                )
            token = lease.get("lease_token")
            if not isinstance(token, str) or not SHA256_RE.fullmatch(token):
                problems.append(
                    f"invalid lease_token on host {host_id}: {token!r}"
                )
    problems.extend(_banned_problems(report))
    return problems


def reconcile_reports(contract, reports):
    """Validate cross-host reconciliation via the contract rules."""
    problems = []
    reconciliation = contract.get("reconciliation")
    if not isinstance(reconciliation, dict):
        return ["contract reconciliation must be a JSON object"]
    scope_fields = reconciliation.get("scope_fields", [])
    agent_fields = reconciliation.get("agent_fields", [])
    lease_fields = reconciliation.get("lease_fields", [])
    for report in reports:
        if not isinstance(report, dict):
            problems.append("host report must be a JSON object")
            continue
        host_id = report.get("host_id")
        for field in scope_fields:
            value = report.get(field)
            expected = contract.get(field)
            if field not in report:
                problems.append(
                    f"reconciliation missing scope field on host "
                    f"{host_id}: {field}"
                )
            elif value != expected:
                problems.append(
                    f"reconciliation mismatch on {field}: {value!r} "
                    f"on host {host_id} vs {expected!r}"
                )
        agents = report.get("agents", [])
        if isinstance(agents, list):
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                for field in agent_fields:
                    if field not in agent:
                        problems.append(
                            f"reconciliation missing agent field on host "
                            f"{host_id}: {field}"
                        )
        leases = report.get("leases", [])
        if isinstance(leases, list):
            for lease in leases:
                if not isinstance(lease, dict):
                    continue
                for field in lease_fields:
                    if field not in lease:
                        problems.append(
                            f"reconciliation missing lease field on host "
                            f"{host_id}: {field}"
                        )
                if lease.get("lease_mode") != contract.get("lease_mode"):
                    problems.append(
                        f"lease_mode mismatch on host {host_id}: "
                        f"{lease.get('lease_mode')!r}"
                    )
    return problems


def check_double_agent(reports):
    """Detect agent ids that appear on more than one host."""
    problems = []
    owners = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        host_id = report.get("host_id")
        for agent in report.get("agents", []):
            if not isinstance(agent, dict):
                continue
            agent_id = agent.get("agent_id")
            if agent_id in owners:
                problems.append(
                    f"double agent detected for agent_id {agent_id} "
                    f"on hosts {owners[agent_id]}, {host_id}"
                )
            else:
                owners[agent_id] = host_id
    return problems


def check_collisions(reports):
    """Detect lease targets acquired on more than one host."""
    problems = []
    holders = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        host_id = report.get("host_id")
        for lease in report.get("leases", []):
            if not isinstance(lease, dict):
                continue
            target = lease.get("lease_target")
            holders.setdefault(target, set()).add(host_id)
    for target in sorted(holders):
        hosts = holders[target]
        if len(hosts) > 1:
            problems.append(
                f"collision detected for lease_target '{target}' "
                f"on hosts {', '.join(sorted(hosts))}"
            )
    return problems


def check_expected(contract, repo_root, reports):
    """Validate the expected live map against the host reports."""
    problems = []
    fixtures = contract.get("fixtures", {})
    if not isinstance(fixtures, dict):
        return ["contract fixtures must be a JSON object"]
    expected_rel = fixtures.get("expected")
    if not isinstance(expected_rel, str):
        return ["contract fixtures expected must be a string path"]
    try:
        expected = load_json(repo_root / expected_rel)
    except FileNotFoundError:
        return [f"missing expected map file: {expected_rel}"]
    except json.JSONDecodeError:
        return [f"invalid JSON in expected map file: {expected_rel}"]
    if not isinstance(expected, dict):
        return ["expected map must be a JSON object"]
    if expected.get("schema") != EXPECTED_EXPECTED_SCHEMA:
        problems.append(
            f"expected map schema mismatch: {expected.get('schema')!r}"
        )
    host_ids = sorted(report.get("host_id") for report in reports)
    if host_ids != expected.get("hosts"):
        problems.append("expected hosts mismatch")
    if len(host_ids) != expected.get("host_count"):
        problems.append("expected host_count mismatch")
    active_agent_total = sum(
        1
        for report in reports
        for agent in report.get("agents", [])
        if isinstance(agent, dict)
        and agent.get("status") == "active"
    )
    if active_agent_total != expected.get("active_agent_total"):
        problems.append("expected active_agent_total mismatch")
    lease_targets = sorted(
        {
            lease.get("lease_target")
            for report in reports
            for lease in report.get("leases", [])
            if isinstance(lease, dict)
            and isinstance(lease.get("lease_target"), str)
        }
    )
    if lease_targets != expected.get("lease_targets"):
        problems.append("expected lease_targets mismatch")
    if len(lease_targets) != expected.get("lease_target_count"):
        problems.append("expected lease_target_count mismatch")
    target_hosts = {}
    for report in reports:
        host_id = report.get("host_id")
        for lease in report.get("leases", []):
            if not isinstance(lease, dict):
                continue
            target = lease.get("lease_target")
            if isinstance(target, str):
                target_hosts.setdefault(target, set()).add(host_id)
    collision_targets = sorted(
        target
        for target, hosts in target_hosts.items()
        if len(hosts) > 1
    )
    if bool(collision_targets) != expected.get("collision_found"):
        problems.append("expected collision_found mismatch")
    if collision_targets != expected.get("collision_targets"):
        problems.append("expected collision_targets mismatch")
    return problems


def run_all(contract_path):
    """Run every swarm-radar-live-map check and return the problems."""
    repo_root = Path(__file__).resolve().parent.parent
    path = Path(contract_path)
    if not path.is_absolute():
        if (Path.cwd() / path).exists():
            path = Path.cwd() / path
        else:
            path = repo_root / path
    try:
        contract = load_json(path)
    except FileNotFoundError:
        return [f"missing contract file: {contract_path}"]
    except json.JSONDecodeError:
        return [f"invalid JSON in contract file: {contract_path}"]
    contract_root = path.resolve().parent.parent
    problems = validate_contract(contract)
    reports = []
    fixtures = contract.get("fixtures", {})
    host_reports = []
    if isinstance(fixtures, dict):
        candidate_reports = fixtures.get("host_reports")
        if isinstance(candidate_reports, list):
            host_reports = candidate_reports
    for rel in host_reports:
        if not isinstance(rel, str):
            problems.append(f"host report path must be a string: {rel!r}")
            continue
        try:
            report = load_json(contract_root / rel)
        except FileNotFoundError:
            problems.append(f"missing host report file: {rel}")
            continue
        except json.JSONDecodeError:
            problems.append(f"invalid JSON in {rel}")
            continue
        reports.append(report)
        problems.extend(validate_host_report(report, contract))
    if len(reports) == 3:
        problems.extend(reconcile_reports(contract, reports))
        problems.extend(check_double_agent(reports))
        problems.extend(check_collisions(reports))
        problems.extend(check_expected(contract, contract_root, reports))
    return problems


def main():
    """Parse arguments, run all checks and print the outcome."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate the swarm-radar-live-map contract and its fixtures"
        )
    )
    parser.add_argument(
        "--contract",
        default="architecture/bach-swarm-radar-live-map-contract.v1.json",
    )
    args = parser.parse_args()
    problems = run_all(args.contract)
    if problems:
        for problem in problems:
            print(f"FAILED {problem}")
        return 1
    print(
        "swarm-radar-live-map check: PASSED (schema+fixture conformance, "
        "not equivalence with a live BACH swarm or live lease table)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())