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

    def test_independence_and_unknown_rules_are_stated(self):
        en = TEXTS["en"].lower()
        for phrase in ("different identity and a different instance", "`unknown`", "never evidence", "regenerated"):
            self.assertIn(phrase, en)

    def test_skills_projection_accepts_the_workflow(self):
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
