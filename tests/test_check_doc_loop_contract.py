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
        needles = (
            "use opus for review", "archive at 75% fulfilled", "docs live in ../docs",
            "run every 14 days", "alle 14 Tage", "jeden 7 Tag", "each 30 days", "check per 2 weeks",
            "repeat after 14 days", "a 14-day cycle", "interval P14D", "interval PT36H", "interval P1Y2M",
        )
        for needle in needles:
            broken = copy.deepcopy(CONTRACT)
            broken["rules"]["monotonic"] += " " + needle
            self.assertTrue(any("freezes" in p for p in validate_contract(broken)), needle)
        # harmless wording stays allowed: priorities and ordinary numbers are not durations
        fine = copy.deepcopy(CONTRACT)
        fine["rules"]["monotonic"] += " Priority P1 and P2, SHA-256, 64 hex characters, ISO-8601."
        self.assertEqual([], validate_contract(fine))

    def test_j_contract_may_not_weaken_mandatory_evidence(self):
        for state in CONTRACT["states"]:
            for field in list(state["required_evidence"]):
                weak = copy.deepcopy(CONTRACT)
                next(s for s in weak["states"] if s["name"] == state["name"])["required_evidence"].remove(field)
                self.assertTrue(any("weakens" in p for p in validate_contract(weak)), f"{state['name']}.{field}")
        weak = copy.deepcopy(CONTRACT)
        next(s for s in weak["states"] if s["name"] == "task_created")["required_evidence"] = ["task_id"]
        problems = validate_contract(weak)
        self.assertTrue(any("weakens" in p and "task_created" in p for p in problems))
        # a weakened contract also cannot rescue a chain: the checker's own set still applies
        chain = load("pos_full_chain.json")
        next(e for e in chain["entries"] if e["state"] == "task_created")["evidence"].pop("readback_ref")
        self.assertTrue(any(p.startswith("E_MISSING_EVIDENCE:task_created.readback_ref") for p in validate_chain(chain, weak)))
        # extending is fine
        extended = copy.deepcopy(CONTRACT)
        next(s for s in extended["states"] if s["name"] == "executed")["required_evidence"].append("extra_field")
        self.assertEqual([], validate_contract(extended))

    def test_k_every_review_finding_has_its_own_negative_fixture(self):
        expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))["negative"]
        for name, codes in expected.items():
            found = validate_chain(load(name), CONTRACT)
            for code in codes:
                self.assertTrue(any(f == code or f.startswith(code + ":") for f in found), f"{name}: {code} not in {found}")
        for name in (
            "neg_readback_not_verified.json", "neg_repaired_without_measurement.json", "neg_run_finished_before_started.json",
            "neg_event_time_not_iso.json", "neg_review_duplicate_index.json", "neg_archive_with_active_reader.json",
            "neg_open_requirement_without_task.json", "neg_frozen_interval_every_n_days.json",
        ):
            self.assertIn(name, expected)

    def test_l_positive_chains_carry_no_copied_interval(self):
        for path in FIXTURES.glob("pos_*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("interval_days", text)
            self.assertNotIn("14", json.dumps(json.loads(text)["entries"][0]["evidence"].get("interval_ref", "")))

    def test_n_both_readmes_list_the_checker_and_both_language_docs_exist(self):
        for readme in ("README.md", "README_de.md"):
            self.assertIn("check_doc_loop_contract.py", (ROOT / readme).read_text(encoding="utf-8"), readme)
        for doc in ("OCEAN-DOC-LOOP.md", "OCEAN-DOKU-REGELKREIS.md"):
            self.assertTrue((ROOT / "architecture" / doc).is_file(), doc)

    def test_m_time_and_coverage_edges(self):
        chain = load("pos_full_chain.json")
        review = next(e for e in chain["entries"] if e["state"] == "reviewed")["evidence"]
        review["verdicts"] = [{"difference_index": True, "verdict": "confirmed"}, {"difference_index": 1, "verdict": "confirmed"}]
        self.assertIn("E_VERDICTS", validate_chain(chain, CONTRACT))
        chain = load("pos_full_chain.json")
        next(e for e in chain["entries"] if e["state"] == "task_created")["evidence"]["readback_verified"] = "true"
        self.assertIn("E_READBACK", validate_chain(chain, CONTRACT))

    def test_i_fixtures_carry_no_live_environment_markers(self):
        for path in FIXTURES.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path.name} contains {banned!r}")


if __name__ == "__main__":
    unittest.main()
