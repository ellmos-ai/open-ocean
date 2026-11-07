# -*- coding: utf-8 -*-
"""Comprehensive tests for Open-Ocean's 11-module stack bridge, standalone
persona_routing, learning_loop, agent_library modules, and API/CLI reference (#2556).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    CANONICAL_INTERFACE_SYSTEM_SLOTS,
    ORIGIN_REMOVED_BADGE,
    PRIMARY_INTERFACE_INTEGRATED_ROLES,
    ModuleDeliveryCatalog,
    get_ocean_role_routing_catalog,
    project_module_library_and_routines,
    resolve_role_execution_target,
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
    expected_ext = {
        "ellmos-voice-io",
        "ellmos-talk",
        "ellmos-sensation",
        "ellmos-homecontrol",
        "ellmos-robotics",
        "ellmos-universal-gui",
    }
    assert set(report["capability_extensions"].keys()) == expected_ext
    missing_ext = sorted(n for n, i in report["capability_extensions"].items() if not i["bound"])
    if missing_ext:
        pytest.skip(f"sibling capability repos not available: {', '.join(missing_ext)}")
    assert report["capability_extensions_bound_count"] == 6
    for name, info in report["capability_extensions"].items():
        assert info["bound"] is True, f"Capability extension {name} failed to bind: {info}"

    from tools.escalation_ladder import evaluate_capability_permission

    cam_default = evaluate_capability_permission("camera")
    assert cam_default["allowed"] is False
    cam_enabled = evaluate_capability_permission("camera", {"camera": True})
    assert cam_enabled["allowed"] is True
    unknown_cap = evaluate_capability_permission("nuclear_reactor")
    assert unknown_cap["allowed"] is False



def _skip_unless_stack_fully_bound() -> None:
    report = ocean_stack_status()
    unbound = sorted(
        n
        for group in ("modules", "capability_extensions")
        for n, i in report[group].items()
        if not i["bound"]
    )
    if unbound:
        pytest.skip(f"stack not fully bound in this environment: {', '.join(unbound)}")


def test_ocean_cli_stack_status_returns_zero(capsys) -> None:
    _skip_unless_stack_fully_bound()
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


def test_interface_system_slots_and_two_stage_role_execution() -> None:
    assert "ticket-master" in PRIMARY_INTERFACE_INTEGRATED_ROLES
    assert "boss-coordinator" in PRIMARY_INTERFACE_INTEGRATED_ROLES
    canonical_ids = {s["id"] for s in CANONICAL_INTERFACE_SYSTEM_SLOTS}
    assert {"buddha_chat", "buddha_connector", "buddha_talk", "buddha_always_on"}.issubset(canonical_ids)

    cat = ModuleDeliveryCatalog()
    cat.install_or_update_module({
        "id": "ellmos-sensation",
        "version": "1.0.0",
        "roles": [{"id": "sensation-observer", "label": "Sensorik-Beobachter", "default_access": "cli"}],
        "interface_slots": [
            {
                "id": "interface_sensation",
                "label": "Sensoren & Kamera",
                "surface": "sensor",
                "required_on_install": False,
                "supports_model_fallbacks": True,
                "integrated_roles": ["personal-assistant", "ticket-master", "boss-coordinator"],
                "unassigned_behavior": "Ohne Besetzung ist die Sensorik-Schnittstelle deaktiviert.",
            }
        ],
    })
    vm_unoccupied = project_module_library_and_routines(cat)
    sensation_slot = next(s for s in vm_unoccupied["interface_slots"] if s["key"] == "ellmos-sensation:interface_sensation")
    assert sensation_slot["occupied"] is False
    assert "Nicht besetzt" in sensation_slot["status_badge"]

    occupied = cat.occupy_interface_slot(
        "ellmos-sensation:interface_sensation",
        backend="ollama",
        model="qwen3:8b",
        model_fallbacks=[{"backend": "anthropic", "model": "claude-haiku-4-5"}],
    )
    assert occupied["occupied"] is True
    assert occupied["status"] == "ready"
    assert len(occupied["model_fallbacks"]) == 1

    # Stage 1: Dynamic persona-routing on active interface slot when no Living agent pins the role
    stage1 = resolve_role_execution_target(
        "ticket-master",
        living_agents=[],
        active_interface_slot={
            "id": "buddha_chat",
            "occupied": True,
            "backend": "anthropic",
            "model": "claude-sonnet-4-6",
            "model_fallbacks": [{"backend": "ollama", "model": "qwen3:8b"}],
            "integrated_roles": list(PRIMARY_INTERFACE_INTEGRATED_ROLES),
        },
    )
    assert stage1["resolution_stage"] == "dynamic_persona_routing"
    assert stage1["integrated_in_interface"] is True
    assert stage1["requires_zero_idle_ram"] is True

    # Stage 2: Pinned Living agent with dedicated model binding takes priority over dynamic routing
    stage2 = resolve_role_execution_target(
        "foerderplaner",
        living_agents=[
            {
                "id": "living_foerderplaner",
                "role_id": "foerderplaner",
                "enabled": True,
                "backend": "openai",
                "model": "gpt-4.1",
                "model_fallbacks": [{"backend": "ollama", "model": "qwen3:8b"}],
            }
        ],
        active_interface_slot={
            "id": "buddha_chat",
            "occupied": True,
            "backend": "anthropic",
            "model": "claude-sonnet-4-6",
        },
    )
    assert stage2["resolution_stage"] == "pinned_living_agent"
    assert stage2["agent_id"] == "living_foerderplaner"
    assert stage2["backend"] == "openai"
    assert stage2["model"] == "gpt-4.1"
    assert stage2["requires_zero_idle_ram"] is False


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
    _skip_unless_stack_fully_bound()
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
