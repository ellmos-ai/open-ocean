# ruff: noqa: E402
"""Tests for the swarm-radar-live-map checker (slice S9, task 1520)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_swarm_radar_live_map import (
    EXPECTED_EXPECTED_SCHEMA,
    check_collisions,
    check_double_agent,
    check_expected,
    load_json,
    reconcile_reports,
    run_all,
    validate_contract,
    validate_host_report,
)

CONTRACT_PATH = (
    ROOT / "architecture" / "bach-swarm-radar-live-map-contract.v1.json"
)
CONTRACT = load_json(CONTRACT_PATH)
REPORT_DIR = ROOT / "tests" / "fixtures" / "swarm_radar_live_map"
BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")


def _load_reports():
    """Load the three synthetic host reports from the fixtures."""
    return [
        load_json(ROOT / rel)
        for rel in CONTRACT["fixtures"]["host_reports"]
    ]


class SwarmRadarLiveMapTests(unittest.TestCase):
    """Schema-level checks for contract, fixtures and checker."""

    def test_a_contract_shape(self):
        self.assertEqual(validate_contract(CONTRACT), [])

    def test_b_no_banned_strings_in_report_files(self):
        for report_path in sorted(REPORT_DIR.glob("*.json")):
            raw = report_path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, raw)

    def test_c_host_reports_shape(self):
        reports = _load_reports()
        self.assertEqual(len(reports), 3)
        for report in reports:
            self.assertEqual(validate_host_report(report, CONTRACT), [])

    def test_d_reconciliation(self):
        reports = _load_reports()
        self.assertEqual(reconcile_reports(CONTRACT, reports), [])

    def test_e_no_collisions(self):
        reports = _load_reports()
        self.assertEqual(check_collisions(reports), [])

    def test_f_expected_live_map(self):
        reports = _load_reports()
        self.assertEqual(check_expected(CONTRACT, ROOT, reports), [])

    def test_g_collision_negative(self):
        reports = _load_reports()
        workstation = json.loads(json.dumps(reports[1]))
        workstation["leases"][0]["lease_target"] = (
            reports[0]["leases"][0]["lease_target"]
        )
        problems = check_collisions([reports[0], workstation])
        self.assertEqual(len(problems), 1)
        self.assertIn("collision detected", problems[0])

    def test_h_double_agent_negative(self):
        reports = _load_reports()
        workstation = json.loads(json.dumps(reports[1]))
        workstation["agents"][0]["agent_id"] = "agent-ms-alpha"
        problems = check_double_agent([reports[0], workstation])
        self.assertEqual(len(problems), 1)
        self.assertIn("double agent detected", problems[0])

    def test_i_empty_leases_negative(self):
        report = json.loads(json.dumps(_load_reports()[0]))
        report["leases"] = []
        problems = validate_host_report(report, CONTRACT)
        self.assertTrue(problems)

    def test_j_run_all(self):
        self.assertEqual(run_all(CONTRACT_PATH), [])

    def test_k_expected_fixture_fields(self):
        expected = load_json(REPORT_DIR / "expected.json")
        self.assertEqual(expected["schema"], EXPECTED_EXPECTED_SCHEMA)
        self.assertEqual(expected["host_count"], 3)
        self.assertFalse(expected["collision_found"])
        self.assertEqual(expected["collision_targets"], [])
        self.assertEqual(expected["reconciliation"], "agreed")


if __name__ == "__main__":
    unittest.main()
