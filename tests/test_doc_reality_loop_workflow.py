"""The doc-reality-loop workflow text: aligned with ocean-doc-loop.v1, free of frozen values, DE/EN parity,
and accepted by the skills projection (tools/project_workflows.py)."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tools.check_doc_loop_contract import EXPECTED_STATES, frozen_hits
from tools.project_workflows import load_skills_from_registry, render_skills_markdown

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows" / "doc-reality-loop"
CONTRACT = json.loads((ROOT / "architecture" / "ocean-doc-loop.v1.json").read_text(encoding="utf-8"))
TEXTS = {lang: (WORKFLOW / name).read_text(encoding="utf-8") for lang, name in (("en", "SKILL.md"), ("de", "SKILL.de.md"))}


CHAIN = json.loads((ROOT / "tests" / "fixtures" / "doc_loop" / "pos_full_chain.json").read_text(encoding="utf-8"))
ENTRY = {e["state"]: e for e in CHAIN["entries"]}
STEP_STATE = {"0": "trigger_planned", "1": "task_created", "3": "executed", "5": "corrected", "6": "reviewed", "7": "repaired"}


def sections(text: str) -> dict[str, str]:
    """Step sections by their number: '### 5. Correct (`corrected`)' -> '5'."""
    found = {}
    parts = re.split(r"^### (\d+)\. ", text, flags=re.M)
    for number, body in zip(parts[1::2], parts[2::2]):
        found[number] = body.split(chr(10) + "## ")[0]
    return found


def ticks(text: str) -> set[str]:
    return {t for t in re.findall(r"`([^`]+)`", text) if "SKILL" not in t}


def frontmatter(text: str) -> dict[str, str]:
    block = text.split("---", 2)[1]
    return dict(re.findall(r"^([a-z_]+):\s*(\S.*)$", block, re.M))


class DocRealityLoopWorkflowTests(unittest.TestCase):
    def test_no_frozen_values_in_either_language(self):
        for lang, text in TEXTS.items():
            self.assertEqual(frozen_hits(text), [], lang)

    def test_every_contract_state_variant_and_field_is_named(self):
        for lang, text in TEXTS.items():
            for state in EXPECTED_STATES:
                self.assertIn(f"`{state}`", text, f"{lang}: {state}")
            for variant in CONTRACT["variants"]:
                self.assertIn(f"`{variant}`", text, f"{lang}: {variant}")
            for field in CONTRACT["configuration_fields"]["fields"]:
                self.assertIn(f"`{field}`", text, f"{lang}: {field}")
            for verdict in CONTRACT["enums"]["verdict"]:
                self.assertIn(f"`{verdict}`", text, f"{lang}: {verdict}")

    def test_states_appear_in_contract_order(self):
        for lang, text in TEXTS.items():
            positions = [text.index(f"(`{state}`)") for state in EXPECTED_STATES]
            self.assertEqual(positions, sorted(positions), lang)

    def test_german_and_english_have_the_same_structure(self):
        def headings(text):
            return [len(m.group(1)) for m in re.finditer(r"^(#{1,3}) ", text, re.M)]
        self.assertEqual(headings(TEXTS["en"]), headings(TEXTS["de"]))
        for lang, text in TEXTS.items():
            meta = frontmatter(text)
            self.assertEqual(meta["name"], "doc-reality-loop")
            self.assertEqual(meta["contract"], "architecture/ocean-doc-loop.v1.json")
            self.assertEqual(meta["language"], lang)
            self.assertTrue((ROOT / meta["contract"]).is_file())

    def test_every_required_and_nested_field_is_named_in_its_step(self):
        """Field names come from the contract and its positive chain fixture, never typed in here."""
        nested = {
            "4": CONTRACT["difference_fields"] + CONTRACT["scope_fields"] + CONTRACT["enums"]["surface"],
            "5": (CONTRACT["archival_fields"] + CONTRACT["reader_check_fields"] + CONTRACT["open_requirement_fields"]
                  + CONTRACT["enums"]["archival_action"] + CONTRACT["enums"]["reader_kind"] + ["archived_at"]
                  + list(ENTRY["corrected"]["evidence"]["files"][0])),
            "6": list(ENTRY["reviewed"]["evidence"]["verdicts"][0]) + CONTRACT["enums"]["verdict"],
            "7": CONTRACT["remeasure_fields"],
            "0": CONTRACT["enums"]["marker_source"],
            "3": CONTRACT["enums"]["exit_state"],
        }
        for lang, text in TEXTS.items():
            secs = sections(text)
            for number, state in STEP_STATE.items():
                required = next(st["required_evidence"] for st in CONTRACT["states"] if st["name"] == state)
                for field in required + ["observed_at"]:
                    self.assertIn(f"`{field}`", secs[number], f"{lang} step {number} ({state}): {field}")
            for number, fields in nested.items():
                for field in fields:
                    self.assertIn(f"`{field}`", secs[number], f"{lang} step {number}: {field}")
            self.assertIn("`observed_at`", text.split("### 0.")[0], lang)

    def test_exit_gate_and_register_only_archival_in_both_languages(self):
        for lang, text in TEXTS.items():
            secs = sections(text)
            self.assertRegex(secs["3"], r"`succeeded`\W+\w+ \w+ `exit_code` 0", lang)
            self.assertIn("`corrected`", secs["3"], lang)
            for token in ("`document_id`", "`archive_policy.reader_audit_not_before`", "`keep`", "`archive_policy`"):
                self.assertIn(token, secs["5"], f"{lang}: {token}")
            self.assertIn("`document_id`", secs["2"], lang)

    def test_german_and_english_name_the_same_fields_per_step(self):
        en, de = sections(TEXTS["en"]), sections(TEXTS["de"])
        self.assertEqual(sorted(en), sorted(de))
        for number in en:
            self.assertEqual(ticks(en[number]), ticks(de[number]), f"step {number}")
        self.assertEqual(ticks(TEXTS["en"].split("## Steps")[0]), ticks(TEXTS["de"].split("## Schritte")[0]))

    def test_archive_policy_is_configuration_of_the_consuming_system(self):
        self.assertIn("consuming system", TEXTS["en"])
        self.assertIn("nutzenden Systems", TEXTS["de"])
        self.assertNotIn("of the consumer", TEXTS["en"])
        self.assertNotRegex(TEXTS["de"], r"des Nutzers")

    def test_independence_and_unknown_rules_are_stated(self):
        en = TEXTS["en"].lower()
        for phrase in ("different identity and a different instance", "`unknown`", "never evidence", "regenerated"):
            self.assertIn(phrase, en)

    def test_skills_projection_accepts_a_registry_entry_for_the_workflow(self):
        # The canonical skills registry (resolve_bundles.DEFAULT_SKILLS_REGISTRY) lives outside this repository
        # (OneDrive .SKILLS/registry/components.json, deployed from the skill source). This test only proves that the
        # projection tool accepts an entry of that shape for this workflow; it does not claim native registration.
        meta = frontmatter(TEXTS["en"])
        registry = {"components": [{"id": f"skill:docs:{meta['name']}", "name": meta["name"], "category": meta["category"],
                                    "status": meta["status"], "path": "workflows/doc-reality-loop/SKILL.md",
                                    "requirement": "optional", "bundles": []}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills.registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            skills, _ = load_skills_from_registry(path)
        self.assertEqual([s.ref for s in skills], ["skill:doc-reality-loop"])
        self.assertEqual(skills[0].detail["category"], "docs")
        self.assertIn("doc-reality-loop", render_skills_markdown(skills))


if __name__ == "__main__":
    unittest.main()
