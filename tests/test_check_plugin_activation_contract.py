import copy
import json
import re
import unittest
from pathlib import Path
from unittest import mock

from tools import check_plugin_activation_contract as chk
from tools.check_plugin_activation_contract import run_fixtures, validate_contract, validate_document

ROOT = Path(__file__).parent.parent
CONTRACT = json.loads((ROOT / "architecture" / "plugin-activation.v1.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "tests" / "fixtures" / "plugin_activation"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
STEPS = ["plan", "lock_host_check", "backup", "native_write", "readback"]


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bare(found):
    return {c.split(":")[0] for c in found}


def first(doc):
    return doc["records"][0]


def drop(mapping, key):
    del mapping[key]


def repair_fixture(code, doc):
    """The smallest repair of the single defect of neg_<code>: afterwards the document must be accepted."""
    if code == "E_SCHEMA":
        doc.update(schema=chk.DOC_SCHEMA)
        return doc
    r = first(doc)
    ev, w = r["evidence"], r.get("write")
    repairs = {
        "E_TYPE": lambda: ev.update(default_applied=False),
        "E_ENUM": lambda: r.update(scope="user"),
        "E_KEY": lambda: r.update(plugin_id="example-plugin@example-market"),
        "E_STATE": lambda: r.update(state="plugged"),
        "E_UNKNOWN_FIELD": lambda: drop(ev, "surprise"),
        "E_MISSING_EVIDENCE": lambda: ev.update(observed_at="2026-10-11T08:00:00Z"),
        "E_HASH": lambda: ev.update(config_revision="a" * 64),
        "E_TIME": lambda: ev.update(observed_at="2026-10-11T08:00:00Z"),
        "E_NO_READBACK": lambda: ev.update(readback_ref="readback:list-1"),
        "E_REVISION_MISMATCH": lambda: ev.update(readback_sha256="a" * 64),
        "E_STALE_READBACK": lambda: ev.update(readback_at="2026-10-11T07:59:50Z"),
        "E_FLAG_ONLY": lambda: ev.update(source="claude_settings_user"),
        "E_DEFAULT_TRUE": lambda: ev.update(source="claude_settings_user"),
        "E_FOREIGN_HOST_WRITE": lambda: w.update(writer_host="host-a"),
        "E_MISMATCH_NO_ERROR": lambda: w.update(requested_value="enabled"),
        "E_PENDING_RUNTIME": lambda: ev.update(runtime_active=None),
        "E_RUNTIME_NO_REF": lambda: ev.update(runtime_ref="runtime:probe-1"),
        "E_NO_BACKUP": lambda: w.update(backup_ref="backup:settings-1"),
        "E_TOGGLE_ORDER": lambda: w.update(steps=STEPS),
        "E_REACHED_STEP": lambda: w.update(reached_step="readback"),
        "E_WRITE_REQUIRED": lambda: r.update(write={
            "requested_value": "enabled", "writer_host": "host-a", "steps": STEPS, "reached_step": "readback",
            "backup_ref": "backup:settings-1", "native_write_at": "2026-10-11T07:59:30Z"}),
        "E_UNKNOWN_NEEDS_REASON": lambda: ev.update(reason_code="no_native_source"),
        "E_ERROR_NO_ROLLBACK": lambda: w.update(rollback_outcome="restored"),
    }
    repairs[code]()
    return doc


class PluginActivationContractTests(unittest.TestCase):
    def test_a_contract_validates_clean_and_matches_the_checker_constants(self):
        self.assertEqual([], validate_contract(CONTRACT))
        states = {s["name"]: s for s in CONTRACT["states"]}
        self.assertEqual(set(chk.STATES), set(states))
        for name, (required, optional) in chk.EVIDENCE.items():
            self.assertEqual(required, states[name]["required_evidence"], name)
            self.assertEqual(optional, states[name]["optional_evidence"], name)
        self.assertEqual(list(chk.STEPS), CONTRACT["toggle_steps"])
        self.assertEqual(list(chk.KEY_FIELDS), CONTRACT["key_fields"])
        self.assertEqual(list(chk.RECORD_REQUIRED), CONTRACT["record_fields"]["required"])
        self.assertEqual(list(chk.RECORD_OPTIONAL), CONTRACT["record_fields"]["optional"])
        self.assertEqual(list(chk.FLAG_SOURCES), CONTRACT["forbidden_sources"]["flag_only"])
        self.assertEqual(list(chk.DEFAULT_SOURCES), CONTRACT["forbidden_sources"]["default_or_absence"])
        self.assertEqual({k: v.pattern for k, v in chk.PATTERNS.items()},
                         {k: v[1:-1] for k, v in CONTRACT["patterns"].items() if k != "note"})
        self.assertEqual(list(chk.SCOPES), CONTRACT["enums"]["scope"])
        self.assertEqual(list(chk.ROLLBACK), CONTRACT["enums"]["rollback_outcome"])
        self.assertEqual(list(chk.PHASES), CONTRACT["enums"]["phase"])
        self.assertEqual(list(chk.READBACK_VALUES), CONTRACT["enums"]["readback_value"])
        self.assertEqual(list(chk.READBACK_VALUES), CONTRACT["enums"]["requested_value"])
        self.assertEqual(set(chk.CODES), set(CONTRACT["error_codes"]))
        self.assertEqual(list(chk.WRITE_REQUIRED), CONTRACT["write_fields"]["required"])
        self.assertEqual(list(chk.WRITE_AFTER_NATIVE), CONTRACT["write_fields"]["required_after_native_write"])

    def test_b_all_fixtures_behave_as_expected(self):
        self.assertEqual([], run_fixtures(CONTRACT, ROOT))

    def test_c_positives_cover_every_state_and_open_consumer(self):
        states = {r["state"] for n in EXPECTED["positive"] for r in load(n)["records"]}
        self.assertEqual(set(chk.STATES), states)
        for name in ("pos_open_consumer.json", "pos_unknown_entry_absent.json", "pos_extensions_object.json",
                     "pos_foreign_host_display_only.json", "pos_error_read_phase.json"):
            self.assertEqual([], validate_document(load(name)), name)

    def test_d_every_error_code_has_exactly_one_fixture_that_raises_exactly_it(self):
        one_to_one = {n: c for n, c in EXPECTED["negative"].items() if n.startswith("neg_e_")}
        self.assertEqual({f"neg_{code.lower()}.json" for code in chk.CODES}, set(one_to_one))
        for code in chk.CODES:
            name = f"neg_{code.lower()}.json"
            self.assertEqual([code], one_to_one[name], name)
            self.assertEqual({code}, bare(validate_document(load(name))), name)
        for name, expected in EXPECTED["negative"].items():  # variants raise at least their codes
            self.assertTrue(set(expected) <= bare(validate_document(load(name))), name)

    def test_e_negative_control_each_fixture_is_clean_after_its_single_repair(self):
        for code in sorted(chk.CODES):
            doc = repair_fixture(code, load(f"neg_{code.lower()}.json"))
            self.assertEqual([], validate_document(doc), code)

    def test_f_rule_switched_off_lets_its_fixture_through(self):
        with mock.patch.object(chk, "FLAG_SOURCES", ()):
            self.assertNotIn("E_FLAG_ONLY", validate_document(load("neg_e_flag_only.json")))
        doc = load("neg_e_default_true.json")
        first(doc)["evidence"]["source"] = "default"
        self.assertIn("E_DEFAULT_TRUE", validate_document(doc))
        with mock.patch.object(chk, "DEFAULT_SOURCES", ()):
            self.assertNotIn("E_DEFAULT_TRUE", validate_document(doc))
        with mock.patch.object(chk, "STEPS", ("plan", "backup", "lock_host_check", "native_write", "readback")):
            self.assertNotIn("E_TOGGLE_ORDER", validate_document(load("neg_e_toggle_order.json")))
        with mock.patch.object(chk, "ROLLBACK", ("restored", "not_needed", "failed", None)):
            self.assertNotIn("E_ERROR_NO_ROLLBACK", validate_document(load("neg_e_error_no_rollback.json")))
        with mock.patch.object(chk, "SHA_RE", re.compile(r".*")):
            self.assertNotIn("E_HASH", validate_document(load("neg_e_hash.json")))
        with mock.patch.object(chk, "SCOPES", ("user", "project", "local", "none", "global")):
            self.assertNotIn("E_ENUM", validate_document(load("neg_e_enum.json")))
        with mock.patch.object(chk, "PHASES", ("read", "write", "other")):
            bad = load("pos_error_read_phase.json")
            first(bad)["evidence"]["phase"] = "other"
            self.assertEqual([], validate_document(bad))
        bad = load("pos_error_read_phase.json")
        first(bad)["evidence"]["phase"] = "other"
        self.assertIn("E_ENUM", bare(validate_document(bad)))

    def test_g_removing_any_required_field_is_rejected(self):
        base = {"plugged": "pos_plugged_claude_user.json", "unplugged": "pos_unplugged.json",
                "pending_restart": "pos_pending_restart.json", "unknown": "pos_unknown_gemini.json",
                "error": "pos_error_mismatch_rolled_back.json"}
        for state, name in base.items():
            for field in chk.EVIDENCE[state][0]:
                doc = load(name)
                del first(doc)["evidence"][field]
                self.assertTrue(validate_document(doc), f"{state}.{field}")
        for field in chk.WRITE_REQUIRED + chk.WRITE_AFTER_NATIVE:
            for name in ("pos_plugged_claude_user.json", "pos_pending_restart.json"):
                doc = load(name)
                del first(doc)["write"][field]
                self.assertTrue(validate_document(doc), f"{name}.write.{field}")
        for field in chk.RECORD_REQUIRED:
            doc = load("pos_plugged_claude_user.json")
            del first(doc)[field]
            self.assertTrue(validate_document(doc), field)
        doc = load("pos_pending_restart.json")
        del first(doc)["write"]
        self.assertIn("E_WRITE_REQUIRED", validate_document(doc))
        doc = load("pos_error_mismatch_rolled_back.json")
        del first(doc)["write"]
        self.assertIn("E_WRITE_REQUIRED", validate_document(doc))
        doc = load("pos_error_mismatch_rolled_back.json")
        del first(doc)["write"]["reached_step"]
        self.assertIn("E_REACHED_STEP", validate_document(doc))

    def test_h_wrong_types_unknown_fields_and_padding_are_rejected_everywhere(self):
        wrong = (None, True, 1, 1.5, [], {}, "", "  ", " x", "x\n")
        paths = [("pos_plugged_claude_user.json", "evidence", f) for f in
                 ("source", "observed_at", "config_revision", "readback_ref", "readback_at", "readback_sha256", "readback_value")]
        paths += [("pos_plugged_claude_user.json", "write", f) for f in
                  ("requested_value", "writer_host", "steps", "reached_step", "backup_ref", "native_write_at")]
        paths += [("pos_error_mismatch_rolled_back.json", "evidence", f) for f in
                  ("request_id", "error_code", "last_evidence", "phase")]
        paths += [("pos_plugged_claude_user.json", None, f) for f in ("consumer", "host", "plugin_id", "scope", "state")]
        for name, block, field in paths:
            for value in wrong:
                doc = load(name)
                target = first(doc) if block is None else first(doc)[block]
                target[field] = value
                self.assertTrue(validate_document(doc), f"{name}.{block}.{field} = {value!r}")
        for name, block in (("pos_plugged_claude_user.json", None), ("pos_plugged_claude_user.json", "evidence"),
                            ("pos_plugged_claude_user.json", "write"), ("pos_unknown_gemini.json", "evidence")):
            doc = load(name)
            (first(doc) if block is None else first(doc)[block])["surprise_field"] = 1
            self.assertIn("E_UNKNOWN_FIELD", bare(validate_document(doc)), f"{name}.{block}")
        for value in (1, "true", 0, None, "", [], {}):  # flags are exactly true or false
            doc = load("pos_plugged_claude_user.json")
            first(doc)["evidence"]["default_applied"] = value
            self.assertTrue(validate_document(doc), repr(value))
        doc = load("pos_plugged_claude_user.json")
        first(doc)["evidence"]["default_applied"] = False
        self.assertEqual([], validate_document(doc))

    def test_i_normative_contract_sections_cannot_be_weakened_reversed_or_reworded(self):
        def changed(edit):
            broken = copy.deepcopy(CONTRACT)
            edit(broken)
            return validate_contract(broken)

        mutations = {
            "writer rule removed": lambda c: c["rules"].pop("writer_only_at_data_host"),
            "default rule reversed": lambda c: c["rules"].update(no_default_true="There is a default state plugged."),
            "consumer pattern loosened": lambda c: c["patterns"].update(consumer="^.*$"),
            "host pattern loosened": lambda c: c["patterns"].update(host="^.*$"),
            "known value added": lambda c: c["known_values"]["consumer"].append("fixed-host"),
            "evidence field removed": lambda c: c["states"][0]["required_evidence"].remove("readback_sha256"),
            "evidence field added": lambda c: c["states"][0]["required_evidence"].append("extra"),
            "optional evidence added": lambda c: c["states"][4]["optional_evidence"].append("extra"),
            "enum widened": lambda c: c["enums"]["scope"].append("global"),
            "steps reversed": lambda c: c["toggle_steps"].reverse(),
            "forbidden source removed": lambda c: c["forbidden_sources"]["flag_only"].remove("plugin_sockets"),
            "error code text reworded": lambda c: c["error_codes"].update(E_NO_BACKUP="Backups are optional."),
            "error code removed": lambda c: c["error_codes"].pop("E_NO_BACKUP"),
            "write field removed": lambda c: c["write_fields"]["required"].remove("requested_value"),
            "record fields changed": lambda c: c["record_fields"]["optional"].append("anything"),
            "key field removed": lambda c: c["key_fields"].remove("host"),
            "section list shortened": lambda c: c["normative_sections"].remove("rules"),
            "section deleted": lambda c: c.pop("patterns"),
        }
        for label, edit in mutations.items():
            self.assertTrue(any("weakens" in p or "lacks a rule text" in p for p in changed(edit)), label)

    def test_j_whole_contract_is_searched_for_hosts_paths_and_urls(self):
        needles = ("C:" + chr(92) + "Users", "/Users/x", "/home/x", "ASUS-GEI", "mac-studio", "https://example.org")
        for place in (("provenance", "ticket"), ("claim_boundary",), ("normative_note",), ("fixtures", "note")):
            for needle in needles:
                broken = copy.deepcopy(CONTRACT)
                node = broken
                for part in place[:-1]:
                    node = node[part]
                node[place[-1]] = str(node[place[-1]]) + " " + needle
                self.assertTrue(any("freezes" in p for p in validate_contract(broken)), f"{place} {needle}")
        broken = copy.deepcopy(CONTRACT)
        broken["known_values"]["consumer"].append("ASUS-GEI")
        problems = validate_contract(broken)
        self.assertTrue(any("freezes" in p for p in problems) and any("weakens" in p for p in problems))

    def test_k_fixtures_contain_no_real_paths_or_hosts(self):
        for p in FIXTURES.glob("*.json"):
            self.assertIsNone(chk.FROZEN_RE.search(p.read_text(encoding="utf-8")), p.name)

    def test_l_docs_describe_the_checker_call_in_both_languages(self):
        for name in ("PLUGIN-ACTIVATION.md", "PLUGIN-AKTIVIERUNG.md"):
            text = (ROOT / "architecture" / name).read_text(encoding="utf-8")
            self.assertIn("python tools/check_plugin_activation_contract.py --document", text, name)
        self.assertNotIn("Plugin-Kabel", (ROOT / "architecture" / "PLUGIN-AKTIVIERUNG.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
