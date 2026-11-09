# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
import json

import ocean
import pytest
from tools.governance_bridge import (
    DEFAULT_CONTENT_GUARD_DIRECTIVE,
    FACTORY_GOVERNANCE_SCHEMA,
    enforce_factory_step4_governance,
)
from tools.gui_server import resolve_ocean_gui_app
from tools.learning_loop import (
    learn_and_reuse_nemofold_workflow,
    propose_review_adopt_loop,
)
from tools.ocean_stack_bridge import ocean_stack_status


def test_gux_001_002_universal_gui_fallback_and_cli(capsys):
    from tools.ocean_stack_bridge import load_universal_gui_module

    try:
        load_universal_gui_module()
    except ImportError:
        pytest.skip("ellmos-universal-gui checkout is not installed on this runner")
    app = resolve_ocean_gui_app(None, fallback_to_universal=True)
    report = app._capabilities(served=True)
    assert report["fallback_active"] is True
    assert report["engine"] == "ellmos-universal-gui"
    assert report["modules"]["ellmos-universal-gui"]["available"] is True

    events = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(event):
        events.append(event)

    asyncio.run(app({"type": "http", "method": "GET", "path": "/"}, receive, send))
    assert events[0]["status"] == 200
    assert b"GUX-002 FALLBACK ACTIVE" in b"".join(e.get("body", b"") for e in events[1:])

    rc = ocean.main(["gui", "--universal-fallback", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fallback_active"] is True
    assert out["engine"] == "ellmos-universal-gui"


def test_gux_028_038_factory_step4_governance_and_content_guard():
    raw_spec = {
        "id": "research-assistant",
        "governance_profile": "standard",
        "tools": ["read_file", "search_text", "read_file"],
        "system_prompt": "Du bist ein präziser Forschungsassistent.",
    }
    enforced = enforce_factory_step4_governance(
        raw_spec,
        content_guard_rules=["Kein Zugriff auf gesperrte LOCK.user-Pfade."],
    )
    assert enforced["schema"] == FACTORY_GOVERNANCE_SCHEMA
    assert enforced["governance_profile"] == "standard"
    assert enforced["tools_whitelist"] == ["read_file", "search_text"]
    assert enforced["content_guard_injected"] is True
    assert DEFAULT_CONTENT_GUARD_DIRECTIVE in enforced["system_prompt"]
    assert "Kein Zugriff auf gesperrte LOCK.user-Pfade." in enforced["system_prompt"]
    assert enforced["hooks"]["PreToolUse"] == "workflowhooker:pre-tool-gate"
    assert enforced["audit_trail"][-1]["event"] == "factory_step4_governance_enforced"


def test_gux_040_and_nemo_01_learning_loop_and_nemofold_reuse():
    loop_res = propose_review_adopt_loop(
        {"name": "Log Hygiene Check", "category": "dev", "description": "Prüft Log-Rotation."},
        reviewer_principal="operator:lukas",
        decision="accepted",
    )
    assert loop_res["adopted"] is True
    assert loop_res["skill_document"]["status"] == "adopted"

    nemo_res = learn_and_reuse_nemofold_workflow(
        [
            {"step": "fetch_uniprot_fasta"},
            {"step": "validate_msa_and_constraints"},
            {"step": "prepare_nemofold_job_manifest"},
        ],
        reviewer_principal="operator:lukas",
    )
    assert nemo_res["adopted"] is True
    assert nemo_res["reuse_ready"] is True
    assert len(nemo_res["reused_execution_plan"]) == 3
    assert all(step["automated"] is True for step in nemo_res["reused_execution_plan"])


def test_stack_status_includes_universal_gui_extension():
    import importlib.util

    status = ocean_stack_status()
    assert status["total_modules"] == 11
    unbound = [name for name, item in status["modules"].items() if not item["bound"]]
    assert status["bound_count"] == 11 - len(unbound)
    assert "ellmos-universal-gui" in status["capability_extensions"]
    if not unbound or importlib.util.find_spec("ellmos_universal_gui") is not None:
        assert status["capability_extensions"]["ellmos-universal-gui"]["bound"] is True
