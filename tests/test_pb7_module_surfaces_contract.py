# -*- coding: utf-8 -*-
"""Contract tests for PB-7 Module Surface Grid & Robotics/Homecontrol Demo Marking (#3991)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.ocean_stack_bridge import load_module_surfaces, ocean_stack_status

ROOT = Path(__file__).resolve().parents[1]
MODULE_SURFACES_PATH = ROOT / "architecture" / "module-surfaces.v1.json"
COMPONENT_BINDINGS_PATH = ROOT / "architecture" / "component-bindings.v1.json"


def _check_surface_contract(entry: dict[str, Any], entry_id: str) -> None:
    """Verify that every module entry has either a non-empty ui.surfaces[] list of /... routes OR agent_only: true."""
    agent_only = entry.get("agent_only")
    ui = entry.get("ui")

    assert isinstance(agent_only, bool), f"{entry_id}: agent_only must be a boolean"
    assert isinstance(ui, dict), f"{entry_id}: ui must be a dict"
    surfaces = ui.get("surfaces")
    assert isinstance(surfaces, list), f"{entry_id}: ui.surfaces must be a list"

    if agent_only is True:
        # agent_only modules do not expose user-facing UI surfaces
        assert len(surfaces) == 0, f"{entry_id}: agent_only module must have empty ui.surfaces"
    else:
        # non-agent-only modules must have a non-empty list of /... routes
        assert len(surfaces) > 0, f"{entry_id}: non-agent-only module must have non-empty ui.surfaces"
        for route in surfaces:
            assert isinstance(route, str), f"{entry_id}: route {route!r} must be a string"
            assert route.startswith("/"), f"{entry_id}: route {route!r} must start with '/'"
            assert len(route) > 1, f"{entry_id}: route {route!r} cannot be just '/'"


def test_module_surfaces_v1_manifest_contract() -> None:
    """Verify architecture/module-surfaces.v1.json structure and completeness."""
    assert MODULE_SURFACES_PATH.is_file(), f"{MODULE_SURFACES_PATH} must exist"
    data = json.loads(MODULE_SURFACES_PATH.read_text(encoding="utf-8"))

    assert data.get("schema") == "ellmos.open-ocean.module-surfaces.v1"
    assert data.get("id") == "module-surfaces"
    assert isinstance(data.get("modules"), dict)
    modules = data["modules"]
    assert len(modules) >= 18, f"Expected at least 18 modules, found {len(modules)}"

    for mod_id, mod_info in modules.items():
        assert mod_info.get("id") == mod_id
        _check_surface_contract(mod_info, mod_id)

    # Demo-mode markings for physical / hardware extensions (PB-7)
    homecontrol = modules.get("ellmos-homecontrol")
    assert homecontrol is not None, "ellmos-homecontrol must be in module-surfaces.v1.json"
    assert homecontrol.get("demo_mode") is True, "ellmos-homecontrol must have demo_mode: true"
    assert homecontrol.get("integration_status") == "demo", "ellmos-homecontrol must have integration_status == 'demo'"

    robotics = modules.get("ellmos-robotics")
    assert robotics is not None, "ellmos-robotics must be in module-surfaces.v1.json"
    assert robotics.get("demo_mode") is True, "ellmos-robotics must have demo_mode: true"
    assert robotics.get("integration_status") == "demo", "ellmos-robotics must have integration_status == 'demo'"


def test_component_bindings_surface_contract() -> None:
    """Verify architecture/component-bindings.v1.json bindings adhere to PB-7 surface contract."""
    assert COMPONENT_BINDINGS_PATH.is_file(), f"{COMPONENT_BINDINGS_PATH} must exist"
    data = json.loads(COMPONENT_BINDINGS_PATH.read_text(encoding="utf-8"))

    assert data.get("schema") == "ellmos.open-ocean.component-bindings.v1"
    bindings = data.get("bindings")
    assert isinstance(bindings, list), "bindings must be a list"
    assert len(bindings) >= 13, f"Expected at least 13 bundle bindings, found {len(bindings)}"

    for b in bindings:
        b_ref = b.get("bundle_ref")
        assert b_ref, f"binding {b} missing bundle_ref"
        _check_surface_contract(b, b_ref)


def test_ocean_stack_bridge_module_surfaces_integration() -> None:
    """Verify tools.ocean_stack_bridge loads and injects module surfaces into stack status."""
    surfaces_data = load_module_surfaces()
    assert surfaces_data.get("schema") == "ellmos.open-ocean.module-surfaces.v1"
    assert "ellmos-homecontrol" in surfaces_data.get("modules", {})
    assert "ellmos-robotics" in surfaces_data.get("modules", {})

    status = ocean_stack_status()
    assert status.get("schema") == "ocean.stack-bindings.v1"
    exts = status.get("capability_extensions", {})

    assert "ellmos-homecontrol" in exts
    assert exts["ellmos-homecontrol"].get("demo_mode") is True
    assert exts["ellmos-homecontrol"].get("integration_status") == "demo"

    assert "ellmos-robotics" in exts
    assert exts["ellmos-robotics"].get("demo_mode") is True
    assert exts["ellmos-robotics"].get("integration_status") == "demo"
