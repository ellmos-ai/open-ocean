"""GUI board inventories (ocean, skills/library, software) over a synthetic OCEAN workspace; no service."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.capability_views import ocean_inventory, skill_library
from tools.catalog_projection import _redact
from tools.gui_bridge import GuiBridge, mount_gui_bridge, bridge_from_workspace
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
    assert response.json() == {"available": False, "reason": "source-not-in-composition"}


def test_unreadable_source_is_503_not_500(tmp_path):
    def broken():
        raise OSError("boom /secret/path/x")
    response = _client(GuiBridge(ocean=broken, skills=broken)).get("/api/capabilities/ocean", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"detail": "Ocean-Quellen nicht lesbar"}
    unconfigured = _client(GuiBridge()).get("/api/capabilities/skills/library", headers=HEADERS)
    assert unconfigured.status_code == 503 and unconfigured.json()["reason"] == "source-not-configured"


def _pages(bridge):
    return {p["id"]: p for p in bridge.capabilities()["pages"]}


MANIFEST = Path(__file__).parent / "fixtures" / "gui-page-reads.v1.f6696e5.json"  # ellmos-system-gui#35 @f6696e5


class _Gui:  # minimal stand-in for a verified release carrying the GUI's page-reads manifest
    source_commit, archive_sha256, installed_verified = "a" * 40, "b" * 64, True
    payload = {"dist/page-reads.v1.json": MANIFEST.read_bytes()}


def test_page_is_configured_only_when_all_its_endpoints_are_served(tmp_path):
    ws = _workspace(tmp_path)
    bridge = GuiBridge(gui=_Gui(), ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    pages = _pages(bridge)
    assert pages["ocean"]["requires"] == ["GET /api/capabilities/ocean"] and pages["ocean"]["missing"] == []
    assert pages["skills"]["requires"] == ["GET /api/capabilities/skills/library"] and pages["skills"]["status"] == "configured"
    assert pages["software"]["missing"] == ["GET /api/capabilities/software"]
    bare = _pages(GuiBridge(gui=_Gui()))
    assert bare["ocean"]["missing"] == ["GET /api/capabilities/ocean"] and bare["ocean"]["status"] == "unavailable"
    # without a verified release there is no manifest: nothing is configured and the reason says why
    none = _pages(GuiBridge(ocean=lambda: ocean_inventory(workspace=ws)))
    assert all(p["status"] == "unavailable" and p["missing"] == ["verified-gui-release", "page-reads-manifest-missing"] for p in none.values())


def test_ocean_and_skills_pages_configured_with_verified_gui_software_not(tmp_path):
    ws = _workspace(tmp_path)
    bridge = GuiBridge(gui=_Gui(), ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    pages = _pages(bridge)
    assert pages["ocean"]["status"] == "configured" and pages["ocean"]["missing"] == []
    assert pages["skills"]["status"] == "configured" and pages["software"]["status"] == "unavailable"
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


# --- skill sources: BACH limits, strict UTF-8, yaml.safe_load frontmatter, id rule, symbol allow-list ----------------

yaml = pytest.importorskip("yaml")


def _skill(ws, name, content: bytes | str):
    folder = ws / "skills" / name
    folder.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    (folder / "SKILL.md").write_bytes(data)


def _by_id(ws):
    return {s["id"]: s for s in skill_library(workspace=ws)["skills"]}


@pytest.mark.parametrize("name,expected", [("a" * 80, True), ("a" * 81, False), ("-bad", False), ("ok.name_1", True)])
def test_skill_id_rule_is_bach_and_gui_rule(tmp_path, name, expected):
    ws = _workspace(tmp_path)
    _skill(ws, name, "---\nname: x\n---\n")
    assert (name in _by_id(ws)) is expected


def test_oversized_nul_and_invalid_utf8_sources_are_not_skills(tmp_path):
    ws = _workspace(tmp_path)
    _skill(ws, "too-big", "---\nname: x\n---\n" + "a" * 200_001)
    _skill(ws, "has-nul", "---\nname: x\n---\nbody\x00")
    _skill(ws, "bad-utf8", b"---\nname: x\n---\n\xff\xfe")
    _skill(ws, "fine", "---\nname: x\n---\n" + "a" * 100)
    assert set(_by_id(ws)) == {"demo-skill", "fine"}


def test_metadata_lengths_are_bounded(tmp_path):
    ws = _workspace(tmp_path)
    _skill(ws, "long", "---\nname: " + "n" * 500 + "\ncategory: " + "c" * 500 + "\nversion: " + "v" * 500 +
                       "\ndescription: " + "d" * 900 + "\n---\n")
    item = _by_id(ws)["long"]
    assert (len(item["name"]), len(item["category"]), len(item["version"]), len(item["description"])) == (200, 100, 100, 300)


# yaml.safe_load semantics (what BACH produces), pinned with explicit values
@pytest.mark.parametrize("text,key,expected", [
    ("---\nname: x\ndescription: |\n  alpha\n  beta\n---\n", "description", "alpha\nbeta\n"),
    ("---\nname: x\ndescription: |-\n  alpha\n  beta\n---\n", "description", "alpha\nbeta"),
    ("---\nname: x\ndescription: |+\n  alpha\n  beta\n\n---\n", "description", "alpha\nbeta\n\n"),
    ("---\nname: x\ndescription: >\n  alpha\n  beta\n---\n", "description", "alpha beta\n"),
    ("---\nname: x\ndescription: >-\n  alpha\n  beta\n---\n", "description", "alpha beta"),
    ("---\nname: x\ndescription: |\n  before\n  ---\n  after\n---\n", "description", "before\n---\nafter\n"),
    ("---\nname: a\nname: b\n---\n", "name", "b"),                                    # duplicate: last wins
    ('---\nname: "one\\ntwo"\n---\n', "name", "one\ntwo"),                           # double-quoted escape
    ("---\nname: 'don''t'\n---\n", "name", "don't"),                                   # single-quote escape
    ("---\nname: x\ndescription: first\n  second\n---\n", "description", "first second"),
    ("\ufeff---\nname: bom\n---\n", "name", "bom"),
    ("---\r\nname: crlf\r\n---\r\n", "name", "crlf"),
    ("---\nname: \u00fcnic\u00f6de \U0001f600\n---\n", "name", "\u00fcnic\u00f6de \U0001f600"),
])
def test_metadata_equals_yaml_safe_load(text, key, expected):
    from tools.capability_views import _metadata
    assert _metadata(text)[key] == expected


@pytest.mark.parametrize("text,key", [
    ("---\nname: x\nversion: null\n---\n", "version"),
    ("---\nname: x\nversion: 1.2\n---\n", "version"),                 # number, not str: field dropped
    ("---\nname: x\ndescription: [a, b]\n---\n", "description"),      # list
    ('---\nname: "a\\x01b"\n---\n', "name"),                           # control character
    ("---\nname: x\ndescription: 'open\n---\n", "description"),         # YAML error: whole block unreadable
])
def test_metadata_drops_non_string_and_control_values(text, key):
    from tools.capability_views import _metadata
    assert key not in _metadata(text)


@pytest.mark.parametrize("text", [
    "---\nname: x\nbody without closing marker\n",                      # no closing marker
    "---\nname: x\n  ---\nsymbol: usr\n",                              # indented --- is no marker
    "name: x\n---\n",                                                   # no start marker
    "---\n- a\n- b\n---\n",                                            # not a mapping
])
def test_metadata_needs_a_real_frontmatter_block(text):
    from tools.capability_views import _metadata
    assert _metadata(text) == {}


def test_without_pyyaml_metadata_is_degraded_never_homemade(tmp_path, monkeypatch):
    from tools import capability_views
    ws = _workspace(tmp_path)
    monkeypatch.setattr(capability_views, "_yaml", None)
    result = skill_library(workspace=ws)
    assert result["degraded"] == ["frontmatter:yaml-unavailable"]
    item = result["skills"][0]
    assert item["description"] == "" and item["name"] == item["id"] and item["version"] == "ohne Versionsnummer"


def test_supported_frontmatter_and_symbol_allow_list(tmp_path):
    ws = _workspace(tmp_path)
    _skill(ws, "good", '---\nname: "Good Name"\ncategory: dev # comment\nversion: "1.2"\nsymbol: wissen\n'
                      'description: plain text\n---\nbody\n')
    _skill(ws, "badsym", "---\nname: x\nsymbol: not-a-symbol\n---\n")
    by = _by_id(ws)
    assert (by["good"]["name"], by["good"]["category"], by["good"]["version"]) == ("Good Name", "dev", "1.2")
    assert by["good"]["symbol"] == "wissen" and by["good"]["description"] == "plain text"
    assert by["badsym"]["symbol"] == "" and "degraded" not in skill_library(workspace=ws)


def test_bom_file_keeps_its_metadata(tmp_path):
    ws = _workspace(tmp_path)
    _skill(ws, "bom", b"\xef\xbb\xbf---\nname: With BOM\n---\n")
    assert _by_id(ws)["bom"]["name"] == "With BOM"


# --- budgets -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("make", [
    lambda i: "---\nname: x\n---\n" + "a" * 200_001,          # oversized
    lambda i: "---\nname: x\n---\nbody\x00" + "a" * 100,         # NUL
    lambda i: b"---\nname: x\n---\n\xff\xfe" + b"a" * 500,     # invalid UTF-8
])
def test_every_read_attempt_counts_against_the_shared_budget(tmp_path, monkeypatch, make):
    from tools import capability_views
    ws = _workspace(tmp_path, skills=False)
    for index in range(30):
        _skill(ws, f"skill-{index:02d}", make(index))
    monkeypatch.setattr(capability_views, "MAX_TOTAL_SOURCE_BYTES", 1000)
    with pytest.raises(RuntimeError):
        skill_library(workspace=ws)


def test_entry_limit_is_enforced_while_scanning(tmp_path, monkeypatch):
    from tools import capability_views
    ws = _workspace(tmp_path)
    monkeypatch.setattr(capability_views, "MAX_SKILL_DIRECTORIES", 5)
    yielded = []

    class _Entry:
        def __init__(self, name):
            self.name = name

    class _Listing:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            for index in range(10_000):
                yielded.append(index)
                yield _Entry(f"s{index}")

    monkeypatch.setattr(capability_views.os, "scandir", lambda path: _Listing())
    with pytest.raises(RuntimeError):
        skill_library(workspace=ws)
    assert len(yielded) <= 6  # the generator was not drained before the limit applied


def test_response_size_limit_gives_503_not_a_huge_answer(tmp_path, monkeypatch):
    from tools import capability_views
    ws = _workspace(tmp_path)
    monkeypatch.setattr(capability_views, "MAX_RESPONSE_BYTES", 100)
    with pytest.raises(RuntimeError):
        skill_library(workspace=ws)
    with pytest.raises(RuntimeError):
        ocean_inventory(workspace=ws)
    bridge = GuiBridge(ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    client = _client(bridge)
    assert client.get("/api/capabilities/skills/library", headers=HEADERS).status_code == 503
    assert client.get("/api/capabilities/ocean", headers=HEADERS).json() == {"detail": "Ocean-Quellen nicht lesbar"}


def test_real_workspace_skills_equal_yaml_safe_load():
    root = Path(os.environ.get("OCEAN_TEST_WORKSPACE", r"C:\_Local_DEV\ocean-full-20261011"))
    if not (root / "skills").is_dir():
        pytest.skip("no installed workspace with skills on this host")
    result = skill_library(workspace=root)
    described = categories = 0
    for item in result["skills"]:
        content = (root / "skills" / item["id"] / "SKILL.md").read_bytes().decode("utf-8").removeprefix("\ufeff")
        block = content.split("\n---", 1)[0].split("\n", 1)[1]
        try:
            reference = yaml.safe_load(block)
        except yaml.YAMLError:
            reference = {}  # BACH answers {} for unparsable frontmatter, so do we
        reference = reference if isinstance(reference, dict) else {}
        for key, field, fallback in (("description", "description", ""), ("category", "category", "general")):
            expected = reference.get(key) if isinstance(reference.get(key), str) else fallback
            assert item[field] == expected[:300 if key == "description" else 100], (item["id"], key)  # BACH redacts nothing here
        described += bool(item["description"])
        categories += item["category"] != "general"
    print(f"real skills: {result['count']}, descriptions: {described}, non-default categories: {categories}, "
          f"categories: {len(result['categories'])}")
    assert result["count"] > 0


def test_skills_assignment_tab_endpoints_are_optional_reads_not_status(tmp_path):
    # ellmos-system-gui c19f70d: hierarchy-assignment-ui.mjs reads GET /api/gui/capabilities and GET + PUT
    # /api/skills-board/hierarchy; Ocean serves neither skills-board route. The manifest marks them optional, so they
    # are reported as unserved but never decide the page status; writes never appear.
    ws = _workspace(tmp_path)
    bridge = GuiBridge(gui=_Gui(), ocean=lambda: ocean_inventory(workspace=ws), skills=lambda: skill_library(workspace=ws))
    page = _pages(bridge)["skills"]
    assert "GET /api/skills-board/hierarchy" in page["optional_unserved"]
    assert "GET /api/skills-board/hierarchy" not in page["missing"] and page["status"] == "configured"
    assert not any(item.startswith(("PUT ", "POST ")) for item in page["requires"] + page["optional_unserved"])


def test_skill_library_keeps_description_text_literal_but_inventory_still_redacts_paths(tmp_path):
    ws = _workspace(tmp_path)
    win = "C:" + chr(92) + "x" + chr(92) + "y"
    _skill(ws, "nulcleaner", "---\nname: Null\ndescription: Writes to /dev/null and " + win + "\ncategory: tools /dev/null\n---\nbody")
    skill = _by_id(ws)["nulcleaner"]
    assert skill["description"] == skill["role"] == "Writes to /dev/null and " + win
    assert skill["category"] == "tools /dev/null"
    # negative control: the redaction itself is intact and still applied to the Ocean source inventory
    from tools.catalog_projection import REDACTED
    assert _redact(win, [0]) == REDACTED
    import inspect
    from tools import capability_views
    assert "_redact(result, [0])" in inspect.getsource(capability_views.ocean_inventory)
