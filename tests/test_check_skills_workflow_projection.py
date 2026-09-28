# ruff: noqa: E402
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_skills_workflow_projection import (
    check_double_trigger,
    check_expected,
    check_toolchain_alignment,
    load_json,
    reconcile_items,
    run_all,
    validate_contract,
    validate_item,
)
CONTRACT = load_json(
    ROOT / "architecture" / "bach-skills-workflow-projection-contract.v1.json"
)
ITEM_DIR = ROOT / "tests" / "fixtures" / "skills_workflow_projection"
EXPECTED = ITEM_DIR / "expected.json"

BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")


class SkillsWorkflowProjectionTests(unittest.TestCase):
    def test_a_contract_validates_clean(self):
        self.assertEqual([], validate_contract(CONTRACT))

    def test_b_fixtures_carry_no_live_environment_markers(self):
        for path in ITEM_DIR.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path} contains banned marker {banned!r}")

    def test_c_all_projection_items_validate(self):
        for rel_path in CONTRACT["fixtures"]["projection_items"]:
            item = load_json(ROOT / rel_path)
            self.assertEqual([], validate_item(item, CONTRACT), f"{rel_path} invalid")

    def test_d_items_reconcile(self):
        items = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["projection_items"]
        ]
        self.assertEqual([], reconcile_items(CONTRACT, items))

    def test_e_no_double_trigger(self):
        items = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["projection_items"]
        ]
        self.assertEqual([], check_double_trigger(items))

    def test_f_expected_document_matches_fixtures(self):
        items = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["projection_items"]
        ]
        self.assertEqual([], check_expected(CONTRACT, items))

    def test_g_double_trigger_detected_for_duplicate_phrase(self):
        item = load_json(ITEM_DIR / "marblerun-chain-skill.json")
        duplicate = dict(item)
        duplicate["projection_id"] = "sproj-2026-009"
        problems = check_double_trigger([item, duplicate])
        self.assertTrue(
            any(
                "duplicate trigger phrase" in problem and "starte kette" in problem
                for problem in problems
            )
        )

    def test_h_duplicate_projection_id_detected(self):
        one = load_json(ITEM_DIR / "marblerun-chain-skill.json")
        two = dict(one)
        two["registry_key"] = "other-key"
        two["projection_digest"] = "sha256:" + "1" * 64
        two["trigger_phrases"] = ["andere phrase"]
        problems = check_double_trigger([one, two])
        self.assertTrue(any("duplicate projection_id" in problem for problem in problems))

    def test_i_reconciliation_fails_on_empty_trigger_phrases(self):
        items = [
            load_json(ROOT / rel_path)
            for rel_path in CONTRACT["fixtures"]["projection_items"]
        ]
        items[1]["trigger_phrases"] = []
        problems = reconcile_items(CONTRACT, items)
        self.assertTrue(any("trigger_phrases" in problem for problem in problems))

    def test_j_run_all_passes(self):
        self.assertEqual([], run_all(ROOT / "architecture" / "bach-skills-workflow-projection-contract.v1.json"))

    def test_k_expected_json_shape(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual("ellmos.open-ocean-skills-workflow-projection-expected.v1", expected["schema"])
        self.assertEqual(3, expected["item_count"])
        self.assertFalse(expected["double_trigger_found"])
        self.assertEqual("agreed", expected["reconciliation"])

    def test_l_toolchain_alignment_findings_hold(self):
        self.assertEqual([], check_toolchain_alignment(CONTRACT))


if __name__ == "__main__":
    unittest.main()