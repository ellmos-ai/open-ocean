# -*- coding: utf-8 -*-
"""Comprehensive tests for Open-Ocean's 11-module stack bridge, standalone
persona_routing, learning_loop, agent_library modules, and API/CLI reference (#2556).
"""
from __future__ import annotations

import json
from pathlib import Path

from ocean import main as ocean_main
from tools.agent_library import (
    AutomationLifecycleRegistry,
    build_desktop_attach_receipt,
    build_full_agent_library_catalog,
    build_shared_completion_selection_contract,
    validate_remote_attach_origin,
)
from tools.generate_api_cli_reference import (
    build_reference_artifacts,
    write_reference_files,
)
from tools.learning_loop import (
    API_ROUTES,
    collect_skill_candidates_job,
    elaborate_candidate_with_skill_gaertner,
    validate_learning_candidate,
    validate_skill_creator_house_format,
)
from tools.ocean_stack_bridge import ocean_stack_status
from tools.persona_routing import (
    ORIGIN_REMOVED_BADGE,
    ModuleDeliveryCatalog,
    get_ocean_role_routing_catalog,
    project_module_library_and_routines,
    validate_persona_routing_manifest,
)


def test_ocean_stack_bridge_binds_all_11_canonical_modules() -> None:
    report = ocean_stack_status()
    assert report["schema"] == "ocean.stack-bindings.v1"
    expected_modules = {
        "ocean-resources",
        "task-master",
        "ellmos-worker",
        "review-policy",
        "escalation-ladder",
        "persona-routing",
        "learning-loop",
        "agent-library",
        "capability-views",
        "governance-bridge",
        "doc-keeper",
    }
    assert set(report["modules"].keys()) == expected_modules
    assert report["total_modules"] == 11
    assert report["bound_count"] == 11
    for name, info in report["modules"].items():
        assert info["bound"] is True, f"Module {name} failed to bind: {info}"


def test_ocean_cli_stack_status_returns_zero(capsys) -> None:
    rc = ocean_main(["stack-status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bound_count"] == 11


def test_persona_routing_and_module_delivery_projection() -> None:
    cat_info = get_ocean_role_routing_catalog()
    assert cat_info["total_roles"] >= 13
    assert len(cat_info["coordinators"]) == 6

    res = validate_persona_routing_manifest({
        "id": "demo",
        "roles": [{"id": "r1", "kind": "expert", "capabilities": ["dev"]}],
        "maintenance": [{"id": "m1", "interval_ref": "routine:daily", "entrypoint": "run.py"}],
    })
    assert res["valid"] is True

    cat = ModuleDeliveryCatalog()
    cat.install_or_update_module({
        "id": "ellmos-skill-creator",
        "version": "1.0.0",
        "roles": [{"id": "skill-gaertner", "label": "Skill-Gärtner", "default_access": "cli"}],
        "maintenance": [
            {
                "id": "drift-job",
                "label": "Drift-Scan",
                "class": "job",
                "trigger": "@daily",
                "requires_model": False,
                "difficulty": "low",
                "requirements": ["python3"],
            },
        ],
    })
    cat.instantiate_agent("ellmos-skill-creator:skill-gaertner", "inst-1")
    vm = project_module_library_and_routines(cat)
    assert len(vm["agent_library"]) == 1
    cat.uninstall_module("ellmos-skill-creator")
    vm_after = project_module_library_and_routines(cat)
    assert vm_after["agent_instances"][0]["origin_badge"] == ORIGIN_REMOVED_BADGE


def test_learning_loop_skill_keeper_pipeline() -> None:
    raw = collect_skill_candidates_job([
        {"name": "PDF Prüfbericht", "description": "Prüft PDFs", "category": "dev"},
    ])
    assert len(raw) == 1
    doc = elaborate_candidate_with_skill_gaertner(raw[0], agent_role="skill-gaertner")
    assert validate_skill_creator_house_format(doc) == []
    assert API_ROUTES["chat_backend_hermes_preserved"] is True

    cand = validate_learning_candidate({
        "candidate_id": "c-1",
        "target_skill_id": "pdf-pruefbericht",
        "origin_session_id": "s-1",
        "evidence_refs": ["ev-1"],
        "proposed_diff_sha256": "a" * 64,
        "review_state": "accepted",
        "reviewer_principal": "operator:lukas",
    })
    assert cand["valid"] is True
    assert cand["promotable"] is True


def test_agent_library_and_automation_and_desktop_contracts(tmp_path: Path) -> None:
    full_lib = build_full_agent_library_catalog(tmp_path)
    assert full_lib["tabs"] == ["templates", "prompt_agents", "chains"]
    assert len(full_lib["templates"]) >= 13

    reg = AutomationLifecycleRegistry()
    reg.register_entry({
        "id": "tagger-mini",
        "family": "mini_agent",
        "trigger": "event",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    })
    started = reg.trigger_start("tagger-mini", start_trigger="event", dedup_key="evt-1")
    assert started["state"] == "running"
    stopped = reg.stop_entry("tagger-mini", expected_fence=started["fence"])
    assert stopped["state"] == "ready"

    shared = build_shared_completion_selection_contract(
        consumer="ocean",
        gui_version="0.2.30",
        host="mac-studio",
        device="operator-mac",
        provider="anthropic",
    )
    assert shared["carrier_product"] == "ellmos-system-gui"
    assert shared["guards"]["action_allowed"] is True

    allowed = ["http://127.0.0.1:8810"]
    attach = validate_remote_attach_origin("http://127.0.0.1:8810/agenten/living", allowed)
    assert attach["remote_ipc_enabled"] is False
    receipt = build_desktop_attach_receipt(
        host="asus-gei",
        platform_name="windows-x86_64",
        origin_url="http://127.0.0.1:8810",
        allowed_origins=allowed,
        capabilities_status=200,
        fence=1,
    )
    assert len(receipt["receipt_sha256"]) == 64


def test_api_cli_reference_generator_has_zero_drift(tmp_path: Path) -> None:
    written = write_reference_files(tmp_path)
    assert written["readme"].is_file()
    assert written["cli"].is_file()
    assert written["manifest"].is_file()

    repo_docs = Path(__file__).resolve().parents[1] / "docs" / "api"
    expected = build_reference_artifacts()
    assert (repo_docs / "README.md").read_text(encoding="utf-8") == expected["api_markdown"]
    assert (repo_docs / "cli-reference.md").read_text(encoding="utf-8") == expected["cli_markdown"]
    saved_manifest = json.loads((repo_docs / "reference-manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["sha256"] == expected["manifest"]["sha256"]
    assert saved_manifest["module_binding_count"] == 11
