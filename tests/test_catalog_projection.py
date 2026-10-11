"""Catalog projection (bach.catalog.v1) over a synthetic OCEAN workspace; no network, no service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.catalog_projection import KINDS, observe
from tools.gui_bridge import GuiBridge, mount_gui_bridge

# Frozen from BACH system/hub/_services/catalog_projection.py (_item, _Source, observe) and the GUI client
# ellmos-system-gui src/lib/catalog-projection.mjs (ITEM_KEYS, SOURCE_KEYS, parseCatalog).
ENVELOPE = {"schema", "generated_at", "host", "sources", "items", "counts", "count", "errors", "truncated",
            "architecture", "redactions"}
ITEM_KEYS = {"id", "type", "aliases", "name", "description", "version", "category", "status", "visibility",
             "repository", "pin", "provides", "requires", "optional", "relations", "measured", "git", "git_hosts",
             "source_ids"}
SOURCE_KEYS = {"id", "kind", "path_label", "host", "schema", "source_version", "generated_at", "generated_at_basis",
               "generated_at_raw", "modified_at", "availability", "error"}
PIN_KEYS = {"commit", "content_hash", "source_version", "verified"}
MEASURED_KEYS = {"installed", "runtime_active", "connection_state", "observed_at", "host", "evidence"}
RELATION_KEYS = {"kind", "target", "target_type", "requirement", "basis"}
HEADERS = {"x-test-session": "ok"}


def _workspace(tmp_path: Path, *, skills=True, modules=True) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    components = [
        {"ref": "module:alpha", "kind": "module", "from_bundles": ["b-one"], "requirement": "required", "status": "resolved",
         "detail": {"catalog_id": "alpha", "repository": "https://github.com/x/alpha", "kind": "tool", "visibility": "public",
                    "provides": ["a.cap"], "requires": ["b.cap"], "local_path": "C:\\Users\\someone\\OneDrive\\alpha"}},
        {"ref": "module:beta", "kind": "module", "from_bundles": ["b-one"], "requirement": "optional", "status": "unresolved",
         "detail": {"catalog_id": "beta", "binding": {"placement_id": "beta", "commit": "c" * 40}}},
        {"ref": "software:app", "kind": "software", "from_bundles": [], "requirement": "optional", "status": "unresolved",
         "detail": {"reason": "unknown component kind"}},
    ]
    state = {"schema": "ellmos.open-ocean-install-state.v1", "recorded_at": "2026-10-11T04:27:45+00:00",
             "workspace": str(ws), "plan": {"composition": {"id": "demo-system"}, "transaction": {
                 "components": components,
                 "fetch": [{"ref": "module:beta", "action": "fetched", "detail": {"sha": "d" * 40}}],
                 "activate": [{"skill_name": "demo-skill", "ref": "skill:demo-skill", "action": "activated"},
                              {"skill_name": "../evil", "ref": "skill:evil", "action": "activated"}],
                 "verify": {"results": [{"bundle_ref": "b-one", "pinned_hash": "e" * 64, "ok": True}]}}}}
    (ws / "ocean.install.json").write_text(json.dumps(state), encoding="utf-8")
    if modules:
        (ws / "modules" / "alpha").mkdir(parents=True)
    if skills:
        (ws / "skills" / "demo-skill").mkdir(parents=True)
        (ws / "skills" / "demo-skill" / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: 'Does demo things C:\\Users\\someone\\x'\n---\nbody\n", encoding="utf-8")
    return ws


def test_contract_shape_and_counts(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    assert ENVELOPE <= set(result) and result["schema"] == "bach.catalog.v1"
    assert all(set(i) >= ITEM_KEYS and set(i["pin"]) == PIN_KEYS and set(i["measured"]) == MEASURED_KEYS
               for i in result["items"])
    assert all(set(r) == RELATION_KEYS for i in result["items"] for r in i["relations"])
    assert all(set(s) == SOURCE_KEYS for s in result["sources"])
    assert result["count"] == len(result["items"])
    assert result["counts"] == {k: sum(1 for i in result["items"] if i["type"] == k) for k in KINDS}
    assert len({(i["type"], i["id"]) for i in result["items"]}) == len(result["items"])
    assert result["counts"] == {"module": 2, "bundle": 1, "stack": 1, "skill": 1, "satellite": 0}


def test_items_come_from_the_composition_not_from_mocks(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    by = {(i["type"], i["id"]): i for i in result["items"]}
    alpha, beta = by[("module", "alpha")], by[("module", "beta")]
    assert alpha["measured"]["installed"] is True and beta["measured"]["installed"] is False
    assert beta["pin"]["commit"] == "d" * 40 and beta["status"] == "unresolved"
    assert by[("bundle", "b-one")]["pin"] == {"commit": None, "content_hash": "e" * 64, "source_version": None, "verified": True}
    assert {r["target"] for r in by[("bundle", "b-one")]["relations"]} == {"module:alpha", "module:beta"}
    assert by[("skill", "demo-skill")]["description"] == "Does demo things <pfad>"
    assert ("skill", "../evil") not in by and ("stack", "systems/demo-system") in by
    assert all(i["git"]["state"] == "unknown" for i in result["items"])


def test_origin_and_state_in_every_answer(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    source = next(s for s in result["sources"] if s["id"] == "ocean_install_state")
    assert source["availability"] == "available" and source["generated_at"] == "2026-10-11T04:27:45+00:00"
    assert len(source["source_version"]) == 64 and result["origin"]["provider"] == "open-ocean"
    assert next(s for s in result["sources"] if s["id"] == "satellite_catalog")["availability"] == "missing"


def test_no_absolute_paths_in_output(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    text = json.dumps(result)
    assert "someone" not in text and str(tmp_path) not in text and result["redactions"] >= 1


@pytest.mark.parametrize("content", [None, "not json", "[]", '{"schema": "other"}'])
def test_broken_or_missing_install_state_is_availability_not_500(tmp_path, content):
    ws = tmp_path / "ws"
    ws.mkdir()
    if content is not None:
        (ws / "ocean.install.json").write_text(content, encoding="utf-8")
    result = observe(workspace=ws)
    assert result["items"] == [] and result["count"] == 0
    assert next(s for s in result["sources"] if s["id"] == "ocean_install_state")["availability"] in {"missing", "error"}


def test_kind_filter_and_validation(tmp_path):
    ws = _workspace(tmp_path)
    only = observe(workspace=ws, kind="skill")
    assert set(only["counts"]) == {"skill"} and {i["type"] for i in only["items"]} == {"skill"}
    with pytest.raises(ValueError):
        observe(workspace=ws, kind="plugin")


def test_missing_skills_dir_does_not_stop_modules(tmp_path):
    result = observe(workspace=_workspace(tmp_path, skills=False))
    assert result["counts"]["module"] == 2 and result["counts"]["skill"] == 0
    assert next(s for s in result["sources"] if s["id"] == "ocean_skills_dir")["availability"] == "missing"


def _client(provider):
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-test-session") != "ok":
            raise HTTPException(401, "login")
        return {"id": 1}
    mount_gui_bridge(app, GuiBridge(catalog=provider), auth, auth)
    return TestClient(app)


def test_route_requires_auth_and_serves_contract(tmp_path):
    ws = _workspace(tmp_path)
    client = _client(lambda **kw: observe(workspace=ws, **kw))
    assert client.get("/api/capabilities/catalog").status_code == 401
    ok = client.get("/api/capabilities/catalog?kind=skill", headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["schema"] == "bach.catalog.v1" and ok.json()["counts"] == {"skill": 1}
    assert client.get("/api/capabilities/catalog?kind=x", headers=HEADERS).status_code == 400


def test_route_without_provider_is_503_not_mock():
    response = _client(None).get("/api/capabilities/catalog", headers=HEADERS)
    assert response.status_code == 503 and response.json()["available"] is False


def _declared(bridge):
    return next(e for e in bridge.capabilities()["endpoints"] if e["path"] == "/api/capabilities/catalog")


def test_capability_declaration_follows_provider():
    assert _declared(GuiBridge())["available"] is False
    live = _declared(GuiBridge(catalog=lambda **kw: {}))
    assert live["available"] is True and live["runtime_verified"] is False


def test_no_page_is_configured_by_the_catalog_endpoint():
    # ellmos-system-gui boards read /api/capabilities/{skills/library,software,ocean}, not /catalog.
    pages = {p["id"]: p for p in GuiBridge(catalog=lambda **kw: {}).capabilities()["pages"]}
    assert all(pages[name]["status"] == "unavailable" for name in ("skills", "software"))
