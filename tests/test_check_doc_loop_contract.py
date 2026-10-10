import copy
import json
import unittest
from pathlib import Path

from tools.check_doc_loop_contract import is_utc, parse_time, run_fixtures, validate_chain, validate_contract

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

    def _full(self):
        return load("pos_full_chain.json")

    @staticmethod
    def _evidence(chain, state):
        return next(e for e in chain["entries"] if e["state"] == state)["evidence"]

    def test_o_every_mandatory_collection_and_object_has_a_strict_type(self):
        wrong_values = ({"a": 1}, "text", 7, None, True)
        targets = {
            "task_created": ["worker_binding"],
            "corrected": ["files", "differences", "archival", "open_requirements"],
            "reviewed": ["verdicts"],
            "repaired": ["remeasure"],
        }
        for state, fields in targets.items():
            for field in fields:
                for wrong in wrong_values:
                    chain = self._full()
                    evidence = self._evidence(chain, state)
                    if isinstance(evidence[field], dict) and isinstance(wrong, dict):
                        continue  # same type
                    evidence[field] = wrong
                    found = validate_chain(chain, CONTRACT)
                    self.assertTrue(
                        any(f.startswith(f"E_TYPE:{state}.{field}") or f.startswith(f"E_MISSING_EVIDENCE:{state}.{field}") for f in found),
                        f"{state}.{field}={wrong!r}: {found}",
                    )
        # a non-empty object instead of the list never passes silently
        chain = self._full()
        self._evidence(chain, "corrected")["files"] = {"path": "a", "before_sha256": "x" * 64, "after_sha256": "y" * 64}
        self.assertIn("E_TYPE:corrected.files", validate_chain(chain, CONTRACT))
        # elements of a list must be objects, nested lists must be lists
        for state, field in (("corrected", "files"), ("corrected", "differences"), ("corrected", "archival"),
                             ("corrected", "open_requirements"), ("reviewed", "verdicts")):
            chain = self._full()
            self._evidence(chain, state)[field].append("not-an-object")
            self.assertTrue(any(f.startswith(f"E_TYPE:{state}.{field}[]") for f in validate_chain(chain, CONTRACT)), field)
        chain = self._full()
        self._evidence(chain, "corrected")["archival"][0]["reader_checks"] = {"ref": "r"}
        self.assertIn("E_TYPE:corrected.archival.reader_checks", validate_chain(chain, CONTRACT))

    def test_p_interval_ref_has_a_form_that_is_no_time_value(self):
        good = ("config:consumer/routine-a", "routine:2035", "policy:docs.freshness", "config:a_b-c.d/e")
        bad = ("14", "2035", 14, 14.0, True, "every 14 days", "alle 14 Tage", "P14D", "PT36H", "14d", "config:", "config: 14",
               "cfg:routine", "routine:with space", "config:every-14-days", "config:14-days", "")
        for ref in good:
            chain = load("pos_trigger_planned_only.json")
            self._evidence(chain, "trigger_planned")["interval_ref"] = ref
            self.assertEqual([], validate_chain(chain, CONTRACT), repr(ref))
        for ref in bad:
            chain = load("pos_trigger_planned_only.json")
            self._evidence(chain, "trigger_planned")["interval_ref"] = ref
            found = validate_chain(chain, CONTRACT)
            self.assertTrue(
                any(f.startswith(("E_INTERVAL_REF", "E_FROZEN_INTERVAL", "E_MISSING_EVIDENCE:trigger_planned.interval_ref")) for f in found),
                f"{ref!r}: {found}",
            )
        weak = copy.deepcopy(CONTRACT)
        weak["reference_patterns"]["interval_ref"] = "^.*$"
        self.assertTrue(any("interval_ref reference form" in p for p in validate_contract(weak)))

    def test_q_archival_needs_both_check_kinds_utc_time_and_ordered_checks(self):
        def archive(chain):
            return self._evidence(chain, "corrected")["archival"][0]

        chain = self._full()
        self.assertEqual("archive", archive(chain)["action"])
        self.assertEqual([], validate_chain(chain, CONTRACT))
        for kind in ("reader", "link"):
            chain = self._full()
            archive(chain)["reader_checks"] = [c for c in archive(chain)["reader_checks"] if c["kind"] == kind]
            self.assertIn("E_ARCHIVE_CHECK_KINDS", validate_chain(chain, CONTRACT), kind)
        for value in (None, "2026-10-10T08:55:00", "2026-10-10T10:55:00+02:00", "yesterday", 7):
            chain = self._full()
            if value is None:
                del archive(chain)["archived_at"]
            else:
                archive(chain)["archived_at"] = value
            self.assertIn("E_ARCHIVE_TIME", validate_chain(chain, CONTRACT), repr(value))
        chain = self._full()
        archive(chain)["archived_at"] = "2026-10-10T08:55:00Z"  # UTC spelled with Z is fine
        self.assertEqual([], validate_chain(chain, CONTRACT))
        for stamp, label in (("2026-10-10T08:19:59+00:00", "before the run was observed"),
                             ("2026-10-10T08:56:00+00:00", "after archived_at")):
            chain = self._full()
            archive(chain)["reader_checks"][0]["checked_at"] = stamp
            self.assertTrue(any(f.startswith("E_ARCHIVE_ORDER") for f in validate_chain(chain, CONTRACT)), label)
        # boundary: exactly at the observed_at of the executed entry and exactly at archived_at is allowed
        chain = self._full()
        archive(chain)["reader_checks"][0]["checked_at"] = "2026-10-10T08:20:00+00:00"
        archive(chain)["reader_checks"][1]["checked_at"] = archive(chain)["archived_at"]
        self.assertEqual([], validate_chain(chain, CONTRACT))
        chain = self._full()
        archive(chain)["archived_at"] = "2026-10-10T09:00:01+00:00"
        self.assertTrue(any(f.startswith("E_ARCHIVE_ORDER:archived_at") for f in validate_chain(chain, CONTRACT)))
        # a kept item with active readers needs no archived_at, but its checks are still ordered
        chain = self._full()
        keep = self._evidence(chain, "corrected")["archival"][1]
        self.assertEqual("keep", keep["action"])
        keep["reader_checks"][0]["checked_at"] = "2026-10-10T09:00:01+00:00"
        self.assertTrue(any(f.startswith("E_ARCHIVE_ORDER") for f in validate_chain(chain, CONTRACT)))

    def test_r_utc_designator_z_is_parsed_without_python_311_features(self):
        # Python 3.10's fromisoformat rejects "Z"; the checker must normalize it itself.
        zulu, offset = parse_time("2026-10-10T08:55:00Z"), parse_time("2026-10-10T08:55:00+00:00")
        self.assertIsNotNone(zulu)
        self.assertEqual(zulu, offset)
        self.assertEqual(zulu.utcoffset().total_seconds(), 0)
        self.assertTrue(is_utc("2026-10-10T08:55:00Z"))
        self.assertTrue(is_utc("2026-10-10T08:55:00+00:00"))
        self.assertFalse(is_utc("2026-10-10T10:55:00+02:00"))
        self.assertFalse(is_utc("2026-10-10T08:55:00"))
        for bad in ("2026-10-10T08:55:00ZZ", "2026-10-10T08:55:00+00:00Z", "2026-10-10Z08:55:00", "Z", "", None, 5):
            self.assertIsNone(parse_time(bad), repr(bad))
        # fractional seconds and offsets in the isoformat() shape stay valid on every supported version
        self.assertIsNotNone(parse_time("2026-10-10T08:55:00.123456+00:00"))
        self.assertIsNotNone(parse_time("2026-10-10T08:55:00.123456Z"))
        # the whole check accepts Z for archived_at and for event times
        chain = self._full()
        self._evidence(chain, "corrected")["archival"][0]["archived_at"] = "2026-10-10T08:55:00Z"
        self._evidence(chain, "executed")["finished_at"] = "2026-10-10T08:20:00Z"
        self.assertEqual([], validate_chain(chain, CONTRACT))

    def test_i_fixtures_carry_no_live_environment_markers(self):
        for path in FIXTURES.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path.name} contains {banned!r}")


if __name__ == "__main__":
    unittest.main()
