# ruff: noqa: E402
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_memory_task_transit import (
    check_double_claim,
    check_expected,
    load_json,
    reconcile_receipts,
    run_all,
    validate_contract,
    validate_receipt,
)
CONTRACT = load_json(
    ROOT / "architecture" / "bach-memory-task-transit-contract.v1.json"
)
RECEIPT_DIR = ROOT / "tests" / "fixtures" / "memory_task_transit"
EXPECTED = RECEIPT_DIR / "expected.json"

BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")


class MemoryTaskTransitTests(unittest.TestCase):
    def test_a_contract_validates_clean(self):
        self.assertEqual([], validate_contract(CONTRACT))

    def test_b_fixtures_carry_no_live_environment_markers(self):
        for path in RECEIPT_DIR.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path} contains banned marker {banned!r}")

    def test_c_all_host_receipts_validate(self):
        for rel_path in CONTRACT["fixtures"]["host_receipts"]:
            receipt = load_json(ROOT / rel_path)
            self.assertEqual([], validate_receipt(receipt, CONTRACT), f"{rel_path} invalid")

    def test_d_receipts_reconcile(self):
        receipts = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["host_receipts"]
        ]
        self.assertEqual([], reconcile_receipts(CONTRACT, receipts))

    def test_e_no_double_claim(self):
        receipts = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["host_receipts"]
        ]
        self.assertEqual([], check_double_claim(receipts))

    def test_f_expected_document_matches_fixtures(self):
        receipts = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["host_receipts"]
        ]
        self.assertEqual([], check_expected(CONTRACT, receipts))

    def test_g_double_claim_detected_for_duplicate_host(self):
        receipt = load_json(RECEIPT_DIR / "mac-studio.json")
        duplicate = dict(receipt)
        duplicate["sequence"] = 9
        self.assertIn("double claim detected for host mac-studio", check_double_claim([receipt, duplicate]))

    def test_h_duplicate_sequence_detected(self):
        one = load_json(RECEIPT_DIR / "mac-studio.json")
        two = dict(one)
        two["host_id"] = "other-host"
        two["claim_salt_hash"] = "sha256:" + "0" * 64
        two["receipt_signature"] = "sha256:" + "1" * 64
        self.assertIn("duplicate sequence 1", check_double_claim([one, two]))

    def test_i_reconciliation_fails_on_divergent_logical_task_id(self):
        receipts = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["host_receipts"]
        ]
        receipts[1]["contents"]["logical_task_id"] = "sha256:" + "9" * 64
        problems = reconcile_receipts(CONTRACT, receipts)
        self.assertTrue(any("logical_task_id" in p for p in problems))

    def test_j_run_all_passes(self):
        self.assertEqual([], run_all(ROOT / "architecture" / "bach-memory-task-transit-contract.v1.json"))

    def test_k_expected_json_shape(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual("ellmos.open-ocean-memory-task-transit-expected.v1", expected["schema"])
        self.assertEqual(3, expected["host_count"])
        self.assertFalse(expected["double_claim_found"])
        self.assertEqual("agreed", expected["reconciliation"])


if __name__ == "__main__":
    unittest.main()
