"""Catalog projection (bach.catalog.v1) over a synthetic OCEAN workspace; no network, no service."""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools import catalog_projection
from tools.catalog_projection import KINDS, observe
from tools.gui_bridge import GuiBridge, mount_gui_bridge

# Field sets and types frozen from BACH system/hub/_services/catalog_projection.py (_item, _Source, observe) and the
# GUI client ellmos-system-gui src/lib/catalog-projection.mjs (ITEM_KEYS, SOURCE_KEYS, parseCatalog and helpers).
ENVELOPE = {"schema", "generated_at", "host", "sources", "items", "counts", "count", "errors", "truncated",
            "architecture", "redactions"}
ADDITIVE_TOP = {"origin"}
ADDITIVE_ITEM = {"path_label", "languages"}
ITEM_KEYS = {"id", "type", "aliases", "name", "description", "version", "category", "status", "visibility",
             "repository", "pin", "provides", "requires", "optional", "relations", "measured", "git", "git_hosts",
             "source_ids"}
SOURCE_KEYS = {"id", "kind", "path_label", "host", "schema", "source_version", "generated_at", "generated_at_basis",
               "generated_at_raw", "modified_at", "availability", "error"}
PIN_KEYS = {"commit", "content_hash", "source_version", "verified"}
MEASURED_KEYS = {"installed", "runtime_active", "connection_state", "observed_at", "host", "evidence"}
RELATION_KEYS = {"kind", "target", "target_type", "requirement", "basis"}
GIT_KEYS = {"state", "branch", "last_commit", "last_commit_raw", "observed_at", "observed_at_basis", "observed_at_raw",
            "host", "source"}
UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$")
HEADERS = {"x-test-session": "ok"}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _opt_str(value):
    return value is None or isinstance(value, str)


def _opt_bool(value):
    return value is None or isinstance(value, bool)


def _strs(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


ARCHITECTURE_KEYS = {"basis", "source_id", "available", "areas", "edges", "layers", "icons", "ui", "edges_note"}
OBSERVED_BASIS = {"declared", "no_timezone", "unparsable", "absent"}


def check_git(git: dict) -> None:
    assert set(git) == GIT_KEYS and git["state"] in {"unknown", "clean", "dirty"}
    assert all(_opt_str(git[k]) for k in ("branch", "last_commit", "last_commit_raw", "observed_at", "observed_at_raw",
                                          "host", "source"))
    assert git["observed_at_basis"] in OBSERVED_BASIS


def check_architecture(arch: dict) -> None:
    """Shape of BACH catalog_projection._empty_architecture / _architecture (areas, edges, layers, icons, ui)."""
    assert set(arch) == ARCHITECTURE_KEYS and arch["basis"] == "declared" and isinstance(arch["source_id"], str)
    assert isinstance(arch["available"], bool) and _opt_str(arch["edges_note"])
    for key in ("areas", "edges", "layers"):
        assert isinstance(arch[key], list) and all(isinstance(entry, dict) for entry in arch[key])
    assert all(isinstance(entry.get("id"), str) for entry in arch["areas"] + arch["layers"])
    assert all(isinstance(entry.get("from"), str) and isinstance(entry.get("to"), str) for entry in arch["edges"])
    assert isinstance(arch["icons"], dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in arch["icons"].items())
    assert isinstance(arch["ui"], dict)


def check_contract(result: dict) -> None:
    """Type check of EVERY contract field; additive fields are explicitly allowed (origin, path_label, languages)."""
    assert ENVELOPE <= set(result) <= ENVELOPE | ADDITIVE_TOP, set(result) ^ ENVELOPE
    assert result["schema"] == "bach.catalog.v1" and UTC_TIME.match(result["generated_at"])
    assert set(result["host"]) == {"id", "source"} and _opt_str(result["host"]["id"])
    assert result["host"]["source"] in {"measured", "declared"}
    assert _is_int(result["count"]) and _is_int(result["redactions"]) and isinstance(result["truncated"], bool)
    assert isinstance(result["counts"], dict) and all(k in KINDS and _is_int(v) for k, v in result["counts"].items())
    assert result["count"] == len(result["items"])
    check_architecture(result["architecture"])
    assert isinstance(result["errors"], list)
    for error in result["errors"]:
        assert set(error) == {"source", "reason", "item"} and isinstance(error["source"], str)
        assert isinstance(error["reason"], str) and _opt_str(error["item"])
    ids = set()
    for source in result["sources"]:
        assert set(source) == SOURCE_KEYS and isinstance(source["id"], str) and isinstance(source["kind"], str)
        assert isinstance(source["path_label"], str) and source["availability"] in {"available", "missing", "error"}
        assert source["generated_at_basis"] in {"declared", "file_mtime", "absent", "no_timezone", "unparsable"}
        assert all(_opt_str(source[k]) for k in ("host", "schema", "source_version", "generated_at",
                                                 "generated_at_raw", "modified_at", "error"))
        ids.add(source["id"])
    seen = set()
    for item in result["items"]:
        assert ITEM_KEYS <= set(item) <= ITEM_KEYS | ADDITIVE_ITEM, set(item) ^ ITEM_KEYS
        assert item["type"] in KINDS and isinstance(item["id"], str) and item["id"]
        assert isinstance(item["name"], str) and item["name"]
        assert all(_opt_str(item[k]) for k in ("description", "version", "category", "status", "visibility", "repository"))
        assert all(_strs(item[k]) for k in ("aliases", "provides", "requires", "optional", "source_ids"))
        assert item["source_ids"] and set(item["source_ids"]) <= ids
        assert set(item["pin"]) == PIN_KEYS and all(_opt_str(item["pin"][k]) for k in ("commit", "content_hash", "source_version"))
        assert _opt_bool(item["pin"]["verified"])
        assert set(item["measured"]) == MEASURED_KEYS and _opt_bool(item["measured"]["installed"])
        assert _opt_bool(item["measured"]["runtime_active"])
        assert isinstance(item["measured"]["connection_state"], str) and item["measured"]["connection_state"]
        assert all(_opt_str(item["measured"][k]) for k in ("observed_at", "host", "evidence"))
        check_git(item["git"])
        assert isinstance(item["git_hosts"], list) and all(isinstance(entry, dict) for entry in item["git_hosts"])
        for entry in item["git_hosts"]:
            check_git(entry)
        assert isinstance(item["relations"], list)
        assert "languages" not in item or _strs(item["languages"])
        for relation in item["relations"]:
            assert set(relation) == RELATION_KEYS and relation["basis"] == "declared"
            assert all(isinstance(relation[k], str) and relation[k] for k in ("kind", "target", "target_type"))
            assert relation["requirement"] in {"required", "recommended", "optional", None}
        assert (item["type"], item["id"]) not in seen
        seen.add((item["type"], item["id"]))
        assert _opt_str(item.get("path_label"))
    for kind, value in result["counts"].items():
        assert value == sum(1 for i in result["items"] if i["type"] == kind)


def _workspace(tmp_path: Path, *, skills=True, modules=True) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    components = [
        {"ref": "module:alpha", "kind": "module", "from_bundles": ["b-one"], "requirement": "required", "status": "resolved",
         "detail": {"catalog_id": "alpha", "repository": "https://github.com/x/alpha", "kind": "tool", "visibility": "public",
                    "provides": ["a.cap"], "requires": ["b.cap"], "source_commit": "f" * 40,
                    "local_path": "C:\\Users\\someone\\OneDrive\\alpha"}},
        {"ref": "module:beta", "kind": "module", "from_bundles": ["b-one"], "requirement": "optional", "status": "unresolved",
         "detail": {"catalog_id": "beta", "binding": {"placement_id": "beta", "commit": "c" * 40}}},
        {"ref": "module:gamma", "kind": "module", "from_bundles": [], "requirement": "optional", "status": "resolved",
         "detail": {"catalog_id": "gamma"}},
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
        (ws / "modules" / "alpha" / ".git").mkdir(parents=True)
        (ws / "modules" / "alpha" / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (ws / "modules" / "gamma").mkdir(parents=True)  # placed copy without any identity proof
    if skills:
        (ws / "skills" / "demo-skill").mkdir(parents=True)
        (ws / "skills" / "demo-skill" / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: 'Does demo things C:\\\\Users\\\\someone\\\\x'\n---\nbody\n", encoding="utf-8")
    return ws


def test_contract_types_and_counts(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    check_contract(result)
    assert result["counts"] == {"module": 3, "bundle": 1, "stack": 1, "skill": 1, "satellite": 0}


def test_contract_check_has_a_negative_control(tmp_path):
    good = observe(workspace=_workspace(tmp_path))
    mutations = [
        lambda r: r.__setitem__("count", "4"),
        lambda r: r["items"][0]["pin"].__setitem__("verified", "yes"),
        lambda r: r["items"][0]["measured"].__setitem__("installed", "true"),
        lambda r: r["items"][0].__setitem__("provides", "x"),
        lambda r: r["items"][0].__setitem__("unexpected", 1),
        lambda r: r.__setitem__("surprise", 1),
        lambda r: r["sources"][0].__setitem__("availability", "ok"),
        lambda r: r["items"][0]["relations"].append({"kind": "contains"}),
        lambda r: r["items"][0]["git"].__setitem__("state", "weird"),
        lambda r: r["items"][0]["git"].__setitem__("branch", 5),
        lambda r: r["items"][0]["git"].__setitem__("observed_at_basis", "file_mtime"),
        lambda r: r["items"][0]["git"].__delitem__("source"),
        lambda r: r["items"][0].__setitem__("git_hosts", ["x"]),
        lambda r: r["items"][0].__setitem__("git_hosts", [{"state": "unknown"}]),
        lambda r: r["items"][0].__setitem__("languages", "de"),
        lambda r: r["items"][0].__setitem__("languages", [1]),
        lambda r: r["architecture"].__setitem__("basis", "measured"),
        lambda r: r["architecture"].__setitem__("available", "no"),
        lambda r: r["architecture"].__setitem__("areas", {}),
        lambda r: r["architecture"].__setitem__("areas", ["a"]),
        lambda r: r["architecture"].__setitem__("edges", [{"from": 1, "to": "b"}]),
        lambda r: r["architecture"].__setitem__("icons", {"a": 1}),
        lambda r: r["architecture"].__setitem__("ui", []),
        lambda r: r["architecture"].__setitem__("edges_note", 3),
        lambda r: r["architecture"].__delitem__("layers"),
    ]
    for mutate in mutations:
        broken = copy.deepcopy(good)
        mutate(broken)
        with pytest.raises(AssertionError):
            check_contract(broken)


def test_contract_check_accepts_populated_substructures(tmp_path):
    good = observe(workspace=_workspace(tmp_path))
    git = {"state": "clean", "branch": "main", "last_commit": "2026-10-01T00:00:00+00:00", "last_commit_raw": None,
           "observed_at": None, "observed_at_basis": "absent", "observed_at_raw": None, "host": "h", "source": "repos.json"}
    good["items"][0]["git_hosts"] = [git]
    good["items"][0]["languages"] = ["de", "en"]
    good["architecture"].update(available=True, areas=[{"id": "a", "dir": "x"}], layers=[{"id": "l"}],
                                edges=[{"from": "a", "to": "b"}], icons={"a": "*"}, ui={"k": 1}, edges_note="n")
    check_contract(good)


def test_items_come_from_the_composition_not_from_mocks(tmp_path):
    result = observe(workspace=_workspace(tmp_path))
    by = {(i["type"], i["id"]): i for i in result["items"]}
    alpha, beta, gamma = by[("module", "alpha")], by[("module", "beta")], by[("module", "gamma")]
    assert alpha["measured"]["installed"] is True and alpha["measured"]["evidence"] == "install_state+git_head"
    assert beta["measured"]["installed"] is False
    assert gamma["measured"]["installed"] is None and gamma["measured"]["evidence"] == "install_state+directory_without_proof"
    assert beta["pin"]["commit"] == "d" * 40 and beta["status"] == "unresolved"
    assert alpha["pin"]["commit"] is None  # detail.source_commit is not an install proof
    assert by[("bundle", "b-one")]["pin"] == {"commit": None, "content_hash": "e" * 64, "source_version": None, "verified": True}
    assert {r["target"] for r in by[("bundle", "b-one")]["relations"]} == {"module:alpha", "module:beta"}
    assert by[("skill", "demo-skill")]["description"] == "Does demo things <pfad>"
    assert ("skill", "../evil") not in by and ("stack", "systems/demo-system") in by
    assert all(i["git"]["state"] == "unknown" for i in result["items"])


def test_empty_head_file_is_no_proof(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "modules" / "alpha" / ".git" / "HEAD").write_text("", encoding="utf-8")
    by = {i["id"]: i for i in observe(workspace=ws, kind="module")["items"]}
    assert by["alpha"]["measured"]["installed"] is None


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
    check_contract(result)
    assert result["items"] == [] and result["count"] == 0
    assert next(s for s in result["sources"] if s["id"] == "ocean_install_state")["availability"] in {"missing", "error"}


def test_kind_filter_and_validation(tmp_path):
    ws = _workspace(tmp_path)
    only = observe(workspace=ws, kind="skill")
    check_contract(only)
    assert set(only["counts"]) == {"skill"} and {i["type"] for i in only["items"]} == {"skill"}
    with pytest.raises(ValueError):
        observe(workspace=ws, kind="plugin")


def test_missing_skills_dir_does_not_stop_modules(tmp_path):
    result = observe(workspace=_workspace(tmp_path, skills=False))
    assert result["counts"]["module"] == 3 and result["counts"]["skill"] == 0
    assert next(s for s in result["sources"] if s["id"] == "ocean_skills_dir")["availability"] == "missing"


# --- handle-final-path check (no check-then-open gap) ---------------------------------------------------------

def test_read_is_refused_when_the_opened_handle_lies_outside_the_workspace(tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    # Simulate a swap between the path check and open(): the handle's final path is outside the workspace.
    monkeypatch.setattr(catalog_projection, "_final_path", lambda fd: str(outside / "ocean.install.json"))
    result = observe(workspace=ws)
    source = next(s for s in result["sources"] if s["id"] == "ocean_install_state")
    assert source["availability"] == "error" and result["items"] == []


def test_read_fails_closed_when_the_platform_cannot_report_the_final_path(tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    monkeypatch.setattr(catalog_projection, "_final_path", lambda fd: None)
    result = observe(workspace=ws)
    assert next(s for s in result["sources"] if s["id"] == "ocean_install_state")["availability"] == "error"


def test_real_final_path_is_available_on_this_platform(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("x", encoding="utf-8")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        final = catalog_projection._final_path(fd)
    finally:
        os.close(fd)
    assert final is not None and catalog_projection._inside(final, tmp_path)
    assert not catalog_projection._inside(final, tmp_path / "other")


def test_workspace_symlink_to_outside_is_not_followed(tmp_path):
    ws = _workspace(tmp_path)
    secret = tmp_path / "outside-modules"
    (secret / ".git").mkdir(parents=True)
    (secret / ".git" / "HEAD").write_text("ref: x\n", encoding="utf-8")
    try:
        os.symlink(secret, ws / "modules" / "delta", target_is_directory=True)
    except (OSError, NotImplementedError):
        junction = subprocess.run(["cmd", "/c", "mklink", "/J", str(ws / "modules" / "delta"), str(secret)],
                                  capture_output=True) if os.name == "nt" else None
        if junction is None or junction.returncode != 0:
            pytest.skip("neither symlink nor junction could be created on this host; the final-path "
                        "behaviour is covered by the monkeypatched final-path tests above")
    state = json.loads((ws / "ocean.install.json").read_text(encoding="utf-8"))
    state["plan"]["transaction"]["components"].append(
        {"ref": "module:delta", "kind": "module", "from_bundles": [], "requirement": "optional", "status": "resolved",
         "detail": {"catalog_id": "delta"}})
    (ws / "ocean.install.json").write_text(json.dumps(state), encoding="utf-8")
    delta = next(i for i in observe(workspace=ws, kind="module")["items"] if i["id"] == "delta")
    assert delta["measured"]["installed"] is not True


# --- route -----------------------------------------------------------------------------------------------------

def _client(provider):
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-test-session") != "ok":
            raise HTTPException(401, "login")
        return {"id": 1}
    mount_gui_bridge(app, GuiBridge(catalog=provider), auth, auth)
    return TestClient(app, follow_redirects=False)


def test_route_requires_auth_and_serves_contract(tmp_path):
    ws = _workspace(tmp_path)
    client = _client(lambda **kw: observe(workspace=ws, **kw))
    ok = client.get("/api/capabilities/catalog?kind=skill", headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["counts"] == {"skill": 1}
    check_contract(ok.json())


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "PROPFIND", "FOO"])
@pytest.mark.parametrize("path", ["/api/capabilities/catalog", "/api/capabilities/catalog/",
                                  "/api/capabilities/catalog?kind=x", "/api/capabilities/catalog?host="])
def test_unauthenticated_callers_see_only_the_auth_answer(method, path):
    called = []
    response = _client(lambda **kw: called.append(kw) or {}).request(method, path)
    assert response.status_code == 401 and not called  # no 405, no slash redirect, no 422, no provider call


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_authenticated_non_get_is_405(method):
    response = _client(lambda **kw: {}).request(method, "/api/capabilities/catalog", headers=HEADERS)
    assert response.status_code == 405 and response.headers["allow"] == "GET"


@pytest.mark.parametrize("query", ["kind=x", "kind=", "host=", "host=" + "h" * 81, "kind=x&host="])
def test_invalid_query_is_422_like_bach(query):
    response = _client(lambda **kw: {}).get("/api/capabilities/catalog?" + query, headers=HEADERS)
    assert response.status_code == 422 and isinstance(response.json()["detail"], list)
    assert all(d["loc"][0] == "query" for d in response.json()["detail"])


def test_valid_query_bounds_are_accepted(tmp_path):
    ws = _workspace(tmp_path)
    client = _client(lambda **kw: observe(workspace=ws, **kw))
    assert client.get("/api/capabilities/catalog?host=" + "h" * 80, headers=HEADERS).status_code == 200
    assert client.get("/api/capabilities/catalog/?kind=module", headers=HEADERS).status_code == 200


def test_route_without_provider_is_503_not_mock():
    response = _client(None).get("/api/capabilities/catalog", headers=HEADERS)
    assert response.status_code == 503 and response.json()["available"] is False


def _declared(bridge):
    return next(e for e in bridge.capabilities()["endpoints"] if e["path"] == "/api/capabilities/catalog")


def test_capability_declaration_follows_provider():
    assert _declared(GuiBridge())["available"] is False
    live = _declared(GuiBridge(catalog=lambda **kw: {}))
    assert live["available"] is True and live["runtime_verified"] is False


def test_ocean_page_is_declared_unavailable_not_absent():
    # ellmos-system-gui main f67174d has /skills/ocean; this PR does not serve what that page reads.
    pages = {p["id"]: p for p in GuiBridge(catalog=lambda **kw: {}).capabilities()["pages"]}
    assert pages["ocean"]["path"] == "/skills/ocean" and pages["ocean"]["status"] == "unavailable"
    # ellmos-system-gui boards read /api/capabilities/{skills/library,software,ocean}, not /catalog.
    assert all(pages[name]["status"] == "unavailable" for name in ("skills", "software", "ocean"))
