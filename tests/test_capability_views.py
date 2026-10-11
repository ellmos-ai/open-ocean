"""GUI board inventories (ocean, skills/library, software) over a synthetic OCEAN workspace; no service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.capability_views import ocean_inventory, skill_library
from tools.gui_bridge import GuiBridge, PAGE_REQUIRES, mount_gui_bridge, bridge_from_workspace
from tests.test_catalog_projection import _workspace

# Frozen from BACH hub/_services/capability_inventory_service.py (_base, ocean_inventory) and
# hub/_services/skill_source_service.py (source_catalog, skill_library).
OCEAN_TOP = {"schema", "kind", "items", "sources", "errors", "truncated", "catalog", "count"}
OCEAN_ITEM = {"id", "name", "description", "version", "source_version", "code_present", "installed", "runtime_active",
              "evidence", "path"}
LIB_TOP = {"schema", "skills", "count", "categories", "source", "declared_only_included"}
LIB_ITEM = {"id", "name", "category", "version", "symbol", "source_version", "evidence_type", "source_kind", "role",
            "description"}
HEADERS = {"x-test-session": "ok"}


def test_ocean_inventory_contract(tmp_path):
    result = ocean_inventory(workspace=_workspace(tmp_path))
    assert set(result) == OCEAN_TOP and result["schema"] == "bach.capability-inventory.v1"
    # GUI rule (ellmos-system-gui software-catalog.mjs catalogMatches)
    assert result["kind"] == "ocean" and result["catalog"] == "ocean-host-sources"
    assert all(set(i) == OCEAN_ITEM for i in result["items"]) and result["count"] == len(result["items"]) == 3
    by = {i["id"]: i for i in result["items"]}
    assert by["alpha"]["installed"] is True and by["alpha"]["code_present"] is True
    assert by["beta"]["installed"] is False and by["beta"]["code_present"] is False
    # a directory without an identity proof (placed copy): present, but not claimed as installed
    assert by["gamma"]["installed"] is None and by["gamma"]["code_present"] is True
    assert all(i["runtime_active"] is None and i["path"].startswith("<workspace>/") for i in result["items"])
    assert result["sources"][0]["available"] is True and result["errors"] == []
    assert "someone" not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


def test_ocean_inventory_without_install_state_is_honest_empty(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    result = ocean_inventory(workspace=ws)
    assert result["items"] == [] and result["count"] == 0 and result["sources"][0]["available"] is False


def test_skill_library_contract(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "skills" / "other").mkdir()
    (ws / "skills" / "other" / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
    (ws / "skills" / ".hidden").mkdir()
    result = skill_library(workspace=ws)
    assert set(result) == LIB_TOP and result["schema"] == "bach.skill-library.v1"
    assert result["source"] == "current_SKILL.md" and result["declared_only_included"] is False
    assert all(set(i) == LIB_ITEM for i in result["skills"]) and result["count"] == len(result["skills"]) == 2
    by = {i["id"]: i for i in result["skills"]}
    assert by["demo-skill"]["role"].startswith("Does demo things") and len(by["demo-skill"]["source_version"]) == 64
    assert by["other"]["version"] == "ohne Versionsnummer" and by["other"]["category"] == "general"
    assert result["categories"] == ["general"]


def test_skill_library_without_skills_dir_raises(tmp_path):
    ws = _workspace(tmp_path, skills=False)
    with pytest.raises(OSError):
        skill_library(workspace=ws)


def _client(bridge):
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-test-session") != "ok":
            raise HTTPException(401, "login")
        return {"id": 1}
    mount_gui_bridge(app, bridge, auth, auth)
    return TestClient(app, follow_redirects=False)


def test_routes_auth_and_contract(tmp_path):
    ws = _workspace(tmp_path)
    bridge = GuiBridge(ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    client = _client(bridge)
    for path in ("/api/capabilities/ocean", "/api/capabilities/skills/library", "/api/capabilities/software"):
        assert client.get(path).status_code == 401
    assert client.get("/api/capabilities/ocean", headers=HEADERS).json()["catalog"] == "ocean-host-sources"
    assert client.get("/api/capabilities/skills/library", headers=HEADERS).json()["count"] == 1


def test_software_is_503_with_machine_readable_reason_never_mock():
    response = _client(GuiBridge()).get("/api/capabilities/software", headers=HEADERS)
    assert response.status_code == 503
    assert response.json() == {"available": False, "reason": "source-not-in-composition", "runtime_verified": False}


def test_unreadable_source_is_503_not_500(tmp_path):
    def broken():
        raise OSError("boom /secret/path/x")
    response = _client(GuiBridge(ocean=broken, skills=broken)).get("/api/capabilities/ocean", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"detail": "Ocean-Quellen nicht lesbar"}
    unconfigured = _client(GuiBridge()).get("/api/capabilities/skills/library", headers=HEADERS)
    assert unconfigured.status_code == 503 and unconfigured.json()["reason"] == "source-not-configured"


def _pages(bridge):
    return {p["id"]: p for p in bridge.capabilities()["pages"]}


def test_page_is_configured_only_when_all_its_endpoints_are_served(tmp_path):
    ws = _workspace(tmp_path)
    bridge = GuiBridge(ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    pages = _pages(bridge)
    # gui is None here, so nothing can be configured; the endpoint-level missing list is what we assert
    assert pages["ocean"]["requires"] == PAGE_REQUIRES["ocean"] and "GET /api/capabilities/ocean" not in pages["ocean"]["missing"]
    assert pages["skills"]["missing"] and "PUT /api/capabilities/skills/{id}/source" in pages["skills"]["missing"]
    assert "GET /api/capabilities/skills/library" not in pages["skills"]["missing"]
    assert pages["software"]["missing"] == ["GET /api/capabilities/software"] or "GET /api/capabilities/software" in pages["software"]["missing"]
    bare = _pages(GuiBridge())
    assert "GET /api/capabilities/ocean" in bare["ocean"]["missing"]


def test_ocean_page_configured_with_verified_gui_skills_and_software_never(tmp_path):
    ws = _workspace(tmp_path)

    class _Gui:  # minimal stand-in for a verified release
        source_commit, archive_sha256, installed_verified = "a" * 40, "b" * 64, True
    bridge = GuiBridge(gui=_Gui(), ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    pages = _pages(bridge)
    assert pages["ocean"]["status"] == "configured" and pages["ocean"]["missing"] == []
    assert pages["skills"]["status"] == "unavailable" and pages["software"]["status"] == "unavailable"
    declared = {(e["method"], e["path"]): e for e in bridge.capabilities()["endpoints"]}
    assert declared[("GET", "/api/capabilities/ocean")]["available"] is True
    assert declared[("GET", "/api/capabilities/software")]["reason"] == "source-not-in-composition"


def test_bridge_from_workspace_wires_both_providers(tmp_path):
    ws = _workspace(tmp_path)
    bridge = bridge_from_workspace(ws)
    assert bridge.providers["ocean"] is not None and bridge.providers["skills"] is not None
    bare = tmp_path / "bare"
    bare.mkdir()
    assert bridge_from_workspace(bare).providers["ocean"] is None


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "PROPFIND", "FOO"])
@pytest.mark.parametrize("path", ["/api/capabilities/ocean", "/api/capabilities/ocean/",
                                  "/api/capabilities/skills/library", "/api/capabilities/skills/library/",
                                  "/api/capabilities/software", "/api/capabilities/software/"])
def test_unauthenticated_callers_see_only_the_auth_answer(tmp_path, method, path):
    ws = _workspace(tmp_path)
    bridge = GuiBridge(ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    response = _client(bridge).request(method, path)
    assert response.status_code == 401  # no 405, no slash redirect, no 503 detail


@pytest.mark.parametrize("path", ["/api/capabilities/ocean", "/api/capabilities/skills/library",
                                  "/api/capabilities/software"])
def test_authenticated_non_get_is_405(path):
    response = _client(GuiBridge()).request("POST", path, headers=HEADERS)
    assert response.status_code == 405 and response.headers["allow"] == "GET"
