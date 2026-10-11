import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from tools import check_plugin_activation_contract as chk
from tools.check_plugin_activation_contract import run_fixtures, validate_contract, validate_document

ROOT = Path(__file__).parent.parent
CONTRACT = json.loads((ROOT / "architecture" / "plugin-activation.v1.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "tests" / "fixtures" / "plugin_activation"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def codes(found):
    return {c.split(":")[0] for c in found}


class PluginActivationContractTests(unittest.TestCase):
    def test_a_contract_validates_clean(self):
        self.assertEqual([], validate_contract(CONTRACT))

    def test_b_all_fixtures_behave_as_expected(self):
        self.assertEqual([], run_fixtures(CONTRACT, ROOT))

    def test_c_positives_cover_every_state_and_open_consumer(self):
        states = {r["state"] for n in EXPECTED["positive"] for r in load(n)["records"]}
        self.assertEqual(set(chk.STATES), states)
        self.assertEqual([], validate_document(load("pos_open_consumer.json")))
        self.assertEqual([], validate_document(load("pos_unknown_entry_absent.json")))

    def test_d_negatives_yield_exactly_their_codes(self):
        for name, expected in EXPECTED["negative"].items():
            self.assertTrue(set(expected) <= codes(validate_document(load(name))), name)
            extra = codes(validate_document(load(name))) - set(expected) - {"E_MISSING_EVIDENCE"}
            self.assertEqual(set(), extra, name)

    def test_e_every_error_code_has_a_negative_fixture(self):
        used = {c for v in EXPECTED["negative"].values() for c in v}
        self.assertEqual(chk.CODES, used)

    def test_f_missing_source_is_unknown_never_plugged(self):
        doc = load("pos_plugged_claude_user.json")
        del doc["records"][0]["evidence"]["source"]
        self.assertIn("E_DEFAULT_TRUE", validate_document(doc))

    def test_g_contract_may_not_weaken_mandatory_evidence(self):
        for state in CONTRACT["states"]:
            for field in list(state["required_evidence"]):
                weak = copy.deepcopy(CONTRACT)
                next(s for s in weak["states"] if s["name"] == state["name"])["required_evidence"].remove(field)
                self.assertTrue(any("weakens" in p for p in validate_contract(weak)), f"{state['name']}.{field}")
        weak = copy.deepcopy(CONTRACT)
        weak["forbidden_sources"]["flag_only"].remove("plugin_sockets")
        self.assertTrue(any("weakens" in p for p in validate_contract(weak)))
        weak = copy.deepcopy(CONTRACT)
        weak["toggle_steps"].reverse()
        self.assertTrue(any("weakens" in p for p in validate_contract(weak)))
        weak = copy.deepcopy(CONTRACT)
        del weak["error_codes"]["E_NO_BACKUP"]
        self.assertTrue(any("lacks a rule text" in p for p in validate_contract(weak)))

    def test_h_contract_rejects_frozen_hosts_and_paths(self):
        for needle in ("C:" + chr(92) + "Users", "/Users/x", "ASUS-GEI", "https://example.org"):
            broken = copy.deepcopy(CONTRACT)
            broken["rules"]["key_unique"] += " " + needle
            self.assertTrue(any("freezes" in p for p in validate_contract(broken)), needle)

    def test_i_negative_control_removed_rule_makes_fixture_pass(self):
        # Each rule, switched off, must let its negative fixture through: the rule really does the rejecting.
        cases = {
            "neg_flag_only.json": ("FLAG_SOURCES", ()),
            "neg_default_true_source.json": ("DEFAULT_SOURCES", ()),
        }
        for name, (attr, value) in cases.items():
            with mock.patch.object(chk, attr, value):
                self.assertEqual([], validate_document(load(name)), name)
        with mock.patch.object(chk, "STEPS", ("plan", "backup", "lock_host_check", "native_write", "readback")):
            self.assertNotIn("E_TOGGLE_ORDER", validate_document(load("neg_toggle_order.json")))
        with mock.patch.object(chk, "ROLLBACK", ("restored", "not_needed", "failed", None)):
            self.assertNotIn("E_ERROR_NO_ROLLBACK", validate_document(load("neg_error_no_rollback.json")))
        # old behavior (flag treated as truth, default as True) is red on the real checker
        legacy = {"schema": chk.DOC_SCHEMA, "records": [{
            "consumer": "bach_core", "host": "h", "plugin_id": "p", "scope": "none", "state": "plugged",
            "evidence": {"source": "plugin_sockets", "observed_at": "2026-10-11T08:00:00Z"}}]}
        self.assertTrue({"E_FLAG_ONLY", "E_NO_READBACK"} <= codes(validate_document(legacy)))

    def test_j_fixtures_contain_no_real_paths_or_hosts(self):
        for p in FIXTURES.glob("*.json"):
            self.assertIsNone(chk.FROZEN_RE.search(p.read_text(encoding="utf-8")), p.name)


if __name__ == "__main__":
    unittest.main()
