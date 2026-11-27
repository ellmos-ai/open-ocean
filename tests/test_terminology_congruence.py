"""Contract tests for the Ocean terminology congruence specification."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "architecture" / "terminology-congruence.v1.json"
DOC_PATH = ROOT / "architecture" / "TERMINOLOGIE-RESSOURCEN-UND-AGENTEN.md"


def test_terminology_congruence_spec_structure_and_disjointness() -> None:
    assert SPEC_PATH.is_file(), "terminology-congruence.v1.json fehlt"
    assert DOC_PATH.is_file(), "TERMINOLOGIE-RESSOURCEN-UND-AGENTEN.md fehlt"

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert spec["schema"] == "ellmos.ocean-terminology-congruence.v1"
    assert spec["schema_version"] == 1
    assert spec["policy"]["one_term_per_concept"] is True
    assert spec["policy"]["preserve_legacy_wire_compatibility"] is True

    concepts = spec["concepts"]
    assert len(concepts) == 6

    ids = [c["id"] for c in concepts]
    assert len(ids) == len(set(ids)), "Doppelte Konzept-IDs"

    canonical_terms = [c["canonical_de"] for c in concepts]
    assert len(canonical_terms) == len(set(canonical_terms)), "Zielbegriffe müssen eindeutig sein"

    by_id = {c["id"]: c for c in concepts}
    assert by_id["stage1_ram_allocation"]["canonical_de"] == "RAM-Zuteilung"
    assert by_id["stage1_ram_allocation"]["stage"] == 1
    assert by_id["stage2_model_time_allocation"]["canonical_de"] == "Modellzeit-Zuteilung"
    assert by_id["stage2_model_time_allocation"]["stage"] == 2
    assert by_id["local_model"]["canonical_de"] == "Lokales Modell"
    assert by_id["model_binding"]["canonical_de"] == "Modellbindung"
    assert by_id["configured_agent"]["canonical_de"] == "Agent"
    assert by_id["library_role_template"]["canonical_de"] == "Rollenvorlage"

    canonical_lower = {t.lower() for t in canonical_terms}
    forbidden_lower = {t.lower() for t in spec["policy"]["forbidden_in_new_ui_and_docs"]}
    assert canonical_lower.isdisjoint(forbidden_lower), "Zielbegriffe dürfen nicht in Verboten-Liste stehen"

    for concept in concepts:
        dep_lower = {t.lower() for t in concept["deprecated_ui_terms"]}
        assert canonical_lower.isdisjoint(dep_lower), f"Konflikt bei {concept['id']}"
        assert concept["code_symbols"], f"code_symbols fehlen bei {concept['id']}"


def test_terminology_markdown_mentions_every_canonical_term() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    doc = DOC_PATH.read_text(encoding="utf-8")
    for concept in spec["concepts"]:
        assert concept["canonical_de"] in doc, f"Zielbegriff {concept['canonical_de']!r} fehlt in Doku"
