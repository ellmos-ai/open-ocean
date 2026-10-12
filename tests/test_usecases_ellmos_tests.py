"""GET /api/usecases served from the ellmos-tests module of the composition (BACH #2095); no service, no scan.

Contract sources (read, not guessed):
  BACH system/gui/server.py:13120-13151  GET /api/usecases -> {"success": True, "usecases": [SELECT * rows ORDER BY title],
      "stats": {"total", "pass", "fail", "pending"}}; pass/fail are counts of test_result, pending = total - pass - fail.
  BACH system/data/schema/schema.sql:1951-1966  the usecases columns; server.py:13297-13298 the test_result rule
      (score >= 75 pass, score > 0 fail, else pending).
  ellmos-system-gui src/pages/governance/usecases.astro:136-294  the page script, vendored below and executed by node
      against the real response: success === true, Array usecases, stats object, rows with a positive integer id.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.gui_bridge import GuiBridge, bridge_from_workspace, mount_gui_bridge, usecases_reader, USECASE_COLUMNS

HEADERS = {"x-test-session": "ok"}
PAGE = Path(__file__).parent / "fixtures" / "gui-usecases-page.85dbe25.js"
PAGE_SHA256 = "17bc96e58a3cb5f6417728137ca1ab461a044da5cc34571ea9d195202c551748"
NODE = shutil.which("node")
PRIVATE = "C:\\Users\\someone\\secret-project"

SOURCE = {
    "_meta": {"generator": "tools/usecases_sync.py", "source_db": "bach.db", "generated_at": "2026-06-22T05:53:57+00:00"},
    "stats": {"total": 4, "covered": 2, "partial": 1, "open": 1},
    "usecases": [
        {"id": 2, "title": "b zweite", "description": None, "module": "docs", "test_score": 80,
         "last_tested": "2026-02-06 08:13:06", "covering_skill": None, "coverage_status": "PARTIAL"},
        {"id": 1, "title": "a erste", "description": "text", "module": "SOFTWARE", "test_score": 100,
         "last_tested": "2026-02-06 08:13:06", "covering_skill": "bewerbungsexperte", "coverage_status": "COVERED"},
        {"id": 3, "title": "c dritte", "description": "x", "module": "docs", "test_score": 40,
         "last_tested": None, "covering_skill": "s", "coverage_status": "OPEN"},
        {"id": 4, "title": "d vierte", "description": "y", "module": "docs", "test_score": 0,
         "last_tested": None, "covering_skill": None, "coverage_status": "OPEN"},
        {"id": 5, "title": "e fünfte", "description": "z", "module": "docs", "test_score": 75,
         "last_tested": None, "covering_skill": None, "coverage_status": "COVERED"},  # boundary: exactly 75 passes
        {"id": 6, "title": "f sechste", "description": "z", "module": "docs", "test_score": 74,
         "last_tested": None, "covering_skill": None, "coverage_status": "COVERED"},  # boundary: 74 fails
        {"id": 7, "title": "g siebte", "description": "z", "module": "docs", "test_score": 1,
         "last_tested": None, "covering_skill": None, "coverage_status": "OPEN"},  # boundary: 1 fails, 0 is pending
    ],
}


def _component(path: Path, catalog_id: str = "ellmos-tests") -> dict:
    return {"ref": f"module:{catalog_id}", "kind": "module", "detail": {"catalog_id": catalog_id, "local_path": str(path)}}


def _client(bridge: GuiBridge) -> TestClient:
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-test-session") != "ok":
            raise HTTPException(401, "login")

    def admin(request):
        auth(request)
    mount_gui_bridge(app, bridge, auth, admin)
    return TestClient(app, follow_redirects=False)


def _bound(tmp_path: Path, document=SOURCE, raw: bytes | None = None) -> TestClient:
    module = tmp_path / "modules" / "ellmos-tests"
    module.mkdir(parents=True, exist_ok=True)
    (module / "usecases.json").write_bytes(raw if raw is not None else json.dumps(document).encode("utf-8"))
    return _client(GuiBridge(usecases=usecases_reader(_component(module))))


# ---- the response itself ---------------------------------------------------------------------------------------

def test_the_response_has_the_bach_shape_and_is_sorted_like_the_bach_query(tmp_path):
    body = _bound(tmp_path).get("/api/usecases", headers=HEADERS).json()
    assert body["success"] is True and list(body)[:3] == ["success", "usecases", "stats"]
    assert [row["title"] for row in body["usecases"]] == ["a erste", "b zweite", "c dritte", "d vierte", "e fünfte", "f sechste", "g siebte"]
    for row in body["usecases"]:
        assert list(row)[:len(USECASE_COLUMNS)] == list(USECASE_COLUMNS)  # every bach.db column, in table order
    first = body["usecases"][0]
    assert first["id"] == 1 and first["test_score"] == 100 and first["last_tested"] == "2026-02-06 08:13:06"
    assert first["workflow_name"] is None and first["test_input"] is None and first["created_by"] is None  # not invented
    assert first["module"] == "SOFTWARE" and first["coverage_status"] == "COVERED"  # additive, ignored by the page


def test_test_result_and_stats_follow_the_bach_rule_and_are_named_as_derived(tmp_path):
    body = _bound(tmp_path).get("/api/usecases", headers=HEADERS).json()
    assert {row["id"]: row["test_result"] for row in body["usecases"]} == {1: "pass", 2: "pass", 3: "fail", 4: "pending", 5: "pass", 6: "fail", 7: "fail"}
    assert body["stats"] == {"total": 7, "pass": 3, "fail": 3, "pending": 1}
    assert body["source"]["derived"] == ["test_result", "stats"]


def test_the_age_of_the_data_is_reported_in_an_additive_field(tmp_path):
    source = _bound(tmp_path).get("/api/usecases", headers=HEADERS).json()["source"]
    assert source["generated_at"] == "2026-06-22T05:53:57+00:00" and source["source_db"] == "bach.db"
    assert source["id"] == "ellmos-tests" and source["read_only"] is True


def test_a_missing_score_leaves_the_result_unset_and_counts_it_pending(tmp_path):
    document = {"usecases": [{"id": 1, "title": "t", "test_score": None}]}
    body = _bound(tmp_path, document).get("/api/usecases", headers=HEADERS).json()
    assert body["usecases"][0]["test_result"] is None and body["stats"] == {"total": 1, "pass": 0, "fail": 0, "pending": 1}
    assert body["source"]["generated_at"] is None


# ---- honest 503 codes --------------------------------------------------------------------------------------------

def test_unbound_is_the_documented_503():
    response = _client(GuiBridge()).get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"available": False, "reason": "source-not-in-composition"}


@pytest.mark.parametrize("name, raw, reason", [
    ("missing", None, "source-missing"),
    ("broken json", b"{not json", "source-invalid"),
    ("not utf-8", b"\xff\xfe\x00", "source-invalid"),
    ("top level list", b"[]", "source-invalid"),
    ("usecases not a list", b'{"usecases": {}}', "source-invalid"),
    ("meta not an object", b'{"_meta": 1, "usecases": []}', "source-invalid"),
    ("id as string", b'{"usecases": [{"id": "1", "title": "t"}]}', "source-invalid"),
    ("id as bool", b'{"usecases": [{"id": true, "title": "t"}]}', "source-invalid"),
    ("id zero", b'{"usecases": [{"id": 0, "title": "t"}]}', "source-invalid"),
    ("duplicate id", b'{"usecases": [{"id": 1, "title": "t"}, {"id": 1, "title": "u"}]}', "source-invalid"),
    ("empty title", b'{"usecases": [{"id": 1, "title": " "}]}', "source-invalid"),
    ("score as string", b'{"usecases": [{"id": 1, "title": "t", "test_score": "100"}]}', "source-invalid"),
    ("score above 100", b'{"usecases": [{"id": 1, "title": "t", "test_score": 101}]}', "source-invalid"),
    ("description as number", b'{"usecases": [{"id": 1, "title": "t", "description": 5}]}', "source-invalid"),
])
def test_a_bad_source_is_a_503_with_a_stable_code_and_no_path(tmp_path, name, raw, reason):
    if raw is None:
        module = tmp_path / "modules" / "ellmos-tests"
        module.mkdir(parents=True)
        client = _client(GuiBridge(usecases=usecases_reader(_component(module))))
    else:
        client = _bound(tmp_path, raw=raw)
    response = client.get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503, name
    assert response.json() == {"available": False, "reason": reason}, name
    assert str(tmp_path) not in response.text and "usecases.json" not in response.text


def test_a_source_over_the_size_limit_is_refused_without_parsing(tmp_path):
    raw = b'{"usecases": [], "pad": "' + b"x" * (4 * 1024 * 1024) + b'"}'
    response = _bound(tmp_path, raw=raw).get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"available": False, "reason": "source-too-large"}


def test_a_link_in_place_of_the_file_is_refused(tmp_path):
    module = tmp_path / "modules" / "ellmos-tests"
    module.mkdir(parents=True)
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(SOURCE), encoding="utf-8")
    try:
        (module / "usecases.json").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks need privileges on this host")
    client = _client(GuiBridge(usecases=usecases_reader(_component(module))))
    response = client.get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503 and response.json()["reason"] == "source-unreadable"


@pytest.mark.parametrize("component", [
    {}, {"detail": {}}, {"detail": {"catalog_id": "policy-registry", "local_path": "x"}},
    {"detail": {"catalog_id": "ellmos-tests"}}, {"detail": {"catalog_id": "ellmos-tests", "local_path": 5}}])
def test_a_component_that_is_not_ellmos_tests_cannot_be_bound(component):
    from tools.gui_bridge import BridgeUnavailable
    with pytest.raises(BridgeUnavailable):
        usecases_reader(component)


def test_auth_comes_first_and_writes_are_405(tmp_path):
    client = _bound(tmp_path)
    assert client.get("/api/usecases").status_code == 401 and client.post("/api/usecases").status_code == 401
    assert client.get("/api/usecases/", headers={}).status_code == 401
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/usecases", headers=HEADERS).status_code == 405


# ---- binding through the composition, not a workspace scan ---------------------------------------------------------

def _workspace(tmp_path: Path, component: dict | None) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    config = {"schema": "ellmos.open-ocean.gui-bridge.v1", "plan_paths": {}}
    if component is not None:
        config["usecases_component"] = component
    (workspace / "ocean.gui-bridge.json").write_text(json.dumps(config), encoding="utf-8")
    return workspace


def test_the_bridge_binds_the_component_from_its_config(tmp_path):
    module = tmp_path / "elsewhere" / "ellmos-tests"
    module.mkdir(parents=True)
    (module / "usecases.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    bridge = bridge_from_workspace(_workspace(tmp_path, _component(module)))
    assert _client(bridge).get("/api/usecases", headers=HEADERS).json()["stats"]["total"] == 7
    endpoint = {item["path"]: item for item in bridge.capabilities()["endpoints"]}["/api/usecases"]
    assert endpoint["available"] is True and endpoint["provider"] == {"id": "ellmos-tests", "version": None}


def test_a_modules_directory_in_the_workspace_is_never_scanned(tmp_path):
    workspace = _workspace(tmp_path, None)
    planted = workspace / "modules" / "ellmos-tests"
    planted.mkdir(parents=True)
    (planted / "usecases.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    bridge = bridge_from_workspace(workspace)
    assert _client(bridge).get("/api/usecases", headers=HEADERS).status_code == 503
    endpoint = {item["path"]: item for item in bridge.capabilities()["endpoints"]}["/api/usecases"]
    assert endpoint["available"] is False and endpoint["reason"] == "source-not-in-composition"


def test_a_foreign_component_in_the_config_is_not_bound(tmp_path):
    bridge = bridge_from_workspace(_workspace(tmp_path, _component(tmp_path, "policy-registry")))
    assert _client(bridge).get("/api/usecases", headers=HEADERS).status_code == 503


def test_the_lifecycle_writes_the_ellmos_tests_component_into_the_bridge_config():
    source = Path(__file__).parent.parent.joinpath("tools", "ocean_lifecycle.py").read_text(encoding="utf-8")
    assert '"usecases_component"' in source and '"ellmos-tests"' in source


# ---- the GUI's own page script, executed -------------------------------------------------------------------------

HARNESS = r"""
const fs = await import('node:fs');
let raw = ''; for await (const c of process.stdin) raw += c;
const {status, body} = JSON.parse(raw);
const nodes = new Map();
const make = () => new Proxy({children: [], textContent: '', hidden: false, dataset: {}, attrs: {}, value: '', style: {}}, {
  get(t, k) {
    if (k in t) return t[k];
    if (k === 'replaceChildren') return (...a) => { t.children = [...a]; };
    if (k === 'append') return (...a) => { t.children.push(...a); };
    if (k === 'setAttribute') return (n, v) => { t.attrs[n] = v; };
    return () => {};
  },
  set(t, k, v) { t[k] = v; return true; }});
globalThis.document = {getElementById: id => { if (!nodes.has(id)) nodes.set(id, make()); return nodes.get(id); },
                       createElement: () => make()};
globalThis.fetch = async () => ({ok: status < 400, status, json: async () => body});
globalThis.confirm = () => false;
(0, eval)(fs.readFileSync(process.argv[1], 'utf8'));
for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 0));
const text = id => document.getElementById(id).textContent;
const list = document.getElementById('uc-list').children;
console.log(JSON.stringify({total: text('uc-total'), pass: text('uc-pass'), fail: text('uc-fail'), pending: text('uc-pending'),
  count: text('uc-count'), error: document.getElementById('uc-list-error').hidden ? '' : text('uc-list-error'),
  titles: list.map(b => b.children && b.children[0] ? b.children[0].textContent : null),
  secondary: list.map(b => b.children && b.children[1] ? b.children[1].textContent : null)}));
"""


def _page_view(status: int, body) -> dict:
    done = subprocess.run([NODE, "--input-type=module", "-e", HARNESS, str(PAGE)], input=json.dumps({"status": status, "body": body}),
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture
def node():
    if NODE is None:
        if os.environ.get("CI"):
            pytest.fail("node is required to execute the GUI's own page script (CI must not skip the contract test)")
        pytest.skip("node is required to execute the GUI's own page script")


def test_the_vendored_page_script_is_the_pinned_file():
    assert hashlib.sha256(PAGE.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == PAGE_SHA256


def test_the_real_page_script_renders_the_response(tmp_path, node):
    response = _bound(tmp_path).get("/api/usecases", headers=HEADERS)
    view = _page_view(response.status_code, response.json())
    assert view["error"] == "" and view["count"] == "7 von 7 Definitionen"
    assert (view["total"], view["pass"], view["fail"], view["pending"]) == ("7", "3", "3", "1")
    assert view["titles"] == ["a erste", "b zweite", "c dritte", "d vierte", "e fünfte", "f sechste", "g siebte"]
    assert view["secondary"][0].endswith("Definition geprüft") and view["secondary"][2].endswith("Definition unvollständig")


def test_negative_control_the_page_rejects_what_would_break_the_contract(tmp_path, node):
    good = _bound(tmp_path).get("/api/usecases", headers=HEADERS).json()
    no_stats = {key: value for key, value in good.items() if key != "stats"}
    assert "Ungültige Usecase-Antwort" in _page_view(200, no_stats)["error"]
    assert _page_view(200, {**good, "success": False})["error"]  # success must be literally true
    string_ids = {**good, "usecases": [{**row, "id": str(row["id"]) + "x"} for row in good["usecases"]]}
    assert _page_view(200, string_ids)["count"] == "0 von 0 Definitionen"  # rows without a numeric id are dropped


def test_the_503_is_shown_as_an_error_not_as_data(tmp_path, node):
    response = _client(GuiBridge()).get("/api/usecases", headers=HEADERS)
    view = _page_view(response.status_code, response.json())
    assert view["error"] and view["count"] == "Keine Daten geladen" and view["titles"] == []
