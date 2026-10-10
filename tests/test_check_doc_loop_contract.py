import copy
import json
import unittest
from pathlib import Path

from tools.check_doc_loop_contract import run_fixtures, validate_chain, validate_contract

ROOT = Path(__file__).parent.parent
CONTRACT = json.loads((ROOT / "architecture" / "ocean-doc-loop.v1.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "tests" / "fixtures" / "doc_loop"
BANNED_STRINGS = ("@", "C:" + chr(92) + "Users", "OneDrive", "bach.db")


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class DocLoopContractTests(unittest.TestCase):
    def test_a_contract_validates_clean(self):
        self.assertEqual([], validate_contract(CONTRACT))

    def test_b_all_fixtures_behave_as_expected(self):
        self.assertEqual([], run_fixtures(CONTRACT, ROOT))

    def test_c_full_chain_is_accepted(self):
        self.assertEqual([], validate_chain(load("pos_full_chain.json"), CONTRACT))

    def test_d_failed_run_is_recorded_honestly_but_cannot_continue(self):
        self.assertEqual([], validate_chain(load("pos_failed_execution_stops.json"), CONTRACT))
        self.assertIn("E_FAILED_NOT_STOPPED", validate_chain(load("neg_failed_run_then_corrected.json"), CONTRACT))

    def test_e_marker_and_task_status_are_not_evidence(self):
        codes = validate_chain(load("neg_last_run_as_execution.json"), CONTRACT)
        self.assertTrue(any(c.startswith("E_MARKER_AS_EVIDENCE") for c in codes))
        codes = validate_chain(load("neg_done_without_report.json"), CONTRACT)
        self.assertTrue(any(c.startswith("E_TASK_STATUS_AS_EVIDENCE") for c in codes))

    def test_f_review_must_be_independent(self):
        chain = load("pos_full_chain.json")
        for field in ("reviewer_id", "reviewer_instance"):
            broken = copy.deepcopy(chain)
            executed = next(e for e in broken["entries"] if e["state"] == "executed")["evidence"]
            reviewed = next(e for e in broken["entries"] if e["state"] == "reviewed")["evidence"]
            reviewed[field] = executed["author_id" if field == "reviewer_id" else "author_instance"]
            self.assertIn("E_SAME_REVIEWER", validate_chain(broken, CONTRACT), field)

    def test_g_unknown_list_must_be_exact(self):
        chain = load("pos_trigger_planned_only.json")
        chain["unknown"] = chain["unknown"][:-1]
        self.assertIn("E_UNKNOWN_LIST", validate_chain(chain, CONTRACT))

    def test_h_contract_rejects_frozen_values(self):
        for needle in ("use opus for review", "archive at 75% fulfilled", "docs live in ../docs"):
            broken = copy.deepcopy(CONTRACT)
            broken["rules"]["monotonic"] += " " + needle
            self.assertTrue(any("freezes" in p for p in validate_contract(broken)), needle)

    def test_i_fixtures_carry_no_live_environment_markers(self):
        for path in FIXTURES.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path.name} contains {banned!r}")


if __name__ == "__main__":
    unittest.main()
