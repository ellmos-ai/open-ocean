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
    return _client(GuiBridge(usecases=usecases_reader(_component(module), module.parent)))


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
        client = _client(GuiBridge(usecases=usecases_reader(_component(module), module.parent)))
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
    client = _client(GuiBridge(usecases=usecases_reader(_component(module), module.parent)))
    response = client.get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503 and response.json()["reason"] == "source-unreadable"


@pytest.mark.parametrize("make", [
    lambda m: {},
    lambda m: {"detail": {}},
    lambda m: {**_component(m), "kind": "skill"},                      # wrong kind
    lambda m: {**_component(m), "ref": "module:policy-registry"},       # wrong ref
    lambda m: _component(m, "policy-registry"),                         # wrong catalog id
    lambda m: {"ref": "module:ellmos-tests", "kind": "module", "detail": {"catalog_id": "ellmos-tests"}},
    lambda m: {"ref": "module:ellmos-tests", "kind": "module", "detail": {"catalog_id": "ellmos-tests", "local_path": 5}},
    lambda m: _component(m.parent.parent / "foreign" / "ellmos-tests"),  # a path outside the modules folder
    lambda m: _component(m.parent / "other" / "ellmos-tests"),           # not directly below it
    lambda m: _component(m.parent / "ellmos-tests-copy"),                # another folder name
    lambda m: _component(m / ".." / ".." / "x" / "ellmos-tests"),        # traversal
])
def test_a_component_that_is_not_the_composed_ellmos_tests_cannot_be_bound(tmp_path, make):
    from tools.gui_bridge import BridgeUnavailable
    module = tmp_path / "ws" / "modules" / "ellmos-tests"
    module.mkdir(parents=True)
    with pytest.raises(BridgeUnavailable):
        usecases_reader(make(module), module.parent)


def test_a_link_inside_the_modules_folder_cannot_redirect_the_binding(tmp_path):
    from tools.gui_bridge import BridgeUnavailable
    modules = tmp_path / "ws" / "modules"
    modules.mkdir(parents=True)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "usecases.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    try:
        (modules / "ellmos-tests").symlink_to(foreign, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlinks unavailable")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(modules / "ellmos-tests"), str(foreign)],
                              capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip("neither symlink nor junction could be created")
    with pytest.raises(BridgeUnavailable):
        usecases_reader(_component(modules / "ellmos-tests"), modules)


def test_auth_comes_first_and_writes_are_405(tmp_path):
    client = _bound(tmp_path)
    assert client.get("/api/usecases").status_code == 401 and client.post("/api/usecases").status_code == 401
    assert client.get("/api/usecases/", headers={}).status_code == 401
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/usecases", headers=HEADERS).status_code == 405


# ---- binding through the composition, not a workspace scan ---------------------------------------------------------

def _workspace(tmp_path: Path, component: dict | None) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    config = {"schema": "ellmos.open-ocean.gui-bridge.v1", "plan_paths": {}}
    if component is not None:
        config["usecases_component"] = component
    (workspace / "ocean.gui-bridge.json").write_text(json.dumps(config), encoding="utf-8")
    return workspace


def test_the_bridge_binds_the_component_from_its_config(tmp_path):
    module = tmp_path / "ws" / "modules" / "ellmos-tests"
    module.mkdir(parents=True)
    (module / "usecases.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    bridge = bridge_from_workspace(_workspace(tmp_path, _component(module)))
    assert _client(bridge).get("/api/usecases", headers=HEADERS).json()["stats"]["total"] == 7
    endpoint = {item["path"]: item for item in bridge.capabilities()["endpoints"]}["/api/usecases"]
    assert endpoint["available"] is True and endpoint["provider"] == {"id": "ellmos-tests", "version": None}


def test_a_config_pointing_outside_the_modules_folder_is_not_bound(tmp_path):
    foreign = tmp_path / "foreign" / "ellmos-tests"
    foreign.mkdir(parents=True)
    (foreign / "usecases.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    bridge = bridge_from_workspace(_workspace(tmp_path, _component(foreign)))
    assert _client(bridge).get("/api/usecases", headers=HEADERS).json()["reason"] == "source-not-in-composition"


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


def _composed(workspace: Path, **overrides) -> dict:
    module = workspace / "modules" / "ellmos-tests"
    return {**_component(module), **overrides}


def test_the_real_lifecycle_selection_picks_exactly_one_valid_component(tmp_path):
    from tools.ocean_lifecycle import select_usecases_component
    workspace = tmp_path / "ws"
    other = {"ref": "module:policy-registry", "kind": "module", "detail": {"catalog_id": "policy-registry", "local_path": "x"}}
    good = _composed(workspace)
    assert select_usecases_component([other, good], workspace) == good
    assert select_usecases_component([other], workspace) is None                        # nothing composed
    assert select_usecases_component([good, _composed(workspace)], workspace) is None   # two candidates
    assert select_usecases_component([good, _composed(workspace, kind="skill")], workspace) is None  # a malformed twin
    assert select_usecases_component([_composed(workspace, kind="skill")], workspace) is None
    assert select_usecases_component([_composed(workspace, ref="module:other")], workspace) is None
    foreign = _component(tmp_path / "foreign" / "ellmos-tests")
    assert select_usecases_component([foreign], workspace) is None                      # outside <workspace>/modules


def test_the_real_lifecycle_function_writes_the_selection_into_the_bridge_config():
    """up_from_paths is exercised end to end by test_ocean_cli; here the written key is read from the real code path."""
    import ast
    import inspect
    from tools import ocean_lifecycle
    tree = ast.parse(inspect.getsource(ocean_lifecycle.up_from_paths).replace("\r\n", "\n"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "select_usecases_component"]
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
              and n.slice.value == "usecases_component" and isinstance(n.ctx, ast.Store)]
    assert calls and stores, "up_from_paths no longer writes usecases_component from select_usecases_component"


# ---- the GUI's own page script, executed -------------------------------------------------------------------------

HARNESS = r"""
const fs = await import('node:fs');
let raw = ''; for await (const c of process.stdin) raw += c;
const {routes, click} = JSON.parse(raw);
const nodes = new Map();
const make = () => new Proxy({children: [], textContent: '', hidden: false, dataset: {}, attrs: {}, value: '', style: {}}, {
  get(t, k) {
    if (k in t) return t[k];
    if (k === 'replaceChildren') return (...a) => { t.children = [...a]; };
    if (k === 'append') return (...a) => { t.children.push(...a); };
    if (k === 'setAttribute') return (n, v) => { t.attrs[n] = v; };
    if (k === 'addEventListener') return (n, f) => { (t.listeners ??= {})[n] = f; };
    return () => {};
  },
  set(t, k, v) { t[k] = v; return true; }});
globalThis.document = {getElementById: id => { if (!nodes.has(id)) nodes.set(id, make()); return nodes.get(id); },
                       createElement: () => make()};
globalThis.fetch = async url => { const r = routes[url] || {status: 404, body: {}};
  return {ok: r.status < 400, status: r.status, json: async () => r.body}; };
globalThis.confirm = () => false;
(0, eval)(fs.readFileSync(process.argv[1], 'utf8'));
for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 0));
const text = id => document.getElementById(id).textContent;
const list = document.getElementById('uc-list').children;
if (click !== null) { await list[click].listeners.click(); for (let i = 0; i < 20; i++) await new Promise(r => setTimeout(r, 0)); }
const detail = Object.fromEntries(['id','title','workflow','result','score','tested','author','updated','description','input','expected']
  .map(n => [n, text('uc-' + n)]));
const action = document.getElementById('uc-action-status');
console.log(JSON.stringify({total: text('uc-total'), pass: text('uc-pass'), fail: text('uc-fail'), pending: text('uc-pending'),
  count: text('uc-count'), detail, action: action.hidden ? '' : action.textContent, error: document.getElementById('uc-list-error').hidden ? '' : text('uc-list-error'),
  titles: list.map(b => b.children && b.children[0] ? b.children[0].textContent : null),
  secondary: list.map(b => b.children && b.children[1] ? b.children[1].textContent : null)}));
"""


def _page_view(status: int, body, *, details: dict | None = None, click: int | None = None) -> dict:
    routes = {"/api/usecases": {"status": status, "body": body}}
    routes.update({f"/api/usecases/{key}": {"status": 200, "body": value} for key, value in (details or {}).items()})
    done = subprocess.run([NODE, "--input-type=module", "-e", HARNESS, str(PAGE)], input=json.dumps({"routes": routes, "click": click}),
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


# ---- detail route: GET /api/usecases/{id} ---------------------------------------------------------------------------
# BACH server.py:13153-13167: {"success": True, "usecase": row}; unknown id -> HTTP 200 {"success": False,
# "error": "Nicht gefunden"} (the page's delete check at usecases.astro:287 relies on exactly that); a non-integer id is
# FastAPI's 422. The page parses it in open() (usecases.astro:200-222): body.usecase.id must equal the clicked id.

def test_the_detail_route_returns_the_row_the_list_shows(tmp_path):
    client = _bound(tmp_path)
    listed = {row["id"]: row for row in client.get("/api/usecases", headers=HEADERS).json()["usecases"]}
    for usecase_id, row in listed.items():
        response = client.get(f"/api/usecases/{usecase_id}", headers=HEADERS)
        assert response.status_code == 200 and response.json() == {"success": True, "usecase": row}


@pytest.mark.parametrize("path", ["/api/usecases/99", "/api/usecases/0", "/api/usecases/-1"])
def test_an_unknown_id_is_bachs_200_not_found(tmp_path, path):
    response = _bound(tmp_path).get(path, headers=HEADERS)
    assert response.status_code == 200 and response.json() == {"success": False, "error": "Nicht gefunden"}


@pytest.mark.parametrize("path", ["/api/usecases/abc", "/api/usecases/1.5", "/api/usecases/test-all"])
def test_a_non_integer_id_is_a_422_detail_list(tmp_path, path):
    response = _bound(tmp_path).get(path, headers=HEADERS)
    detail = response.json()["detail"]
    assert response.status_code == 422 and detail[0]["loc"] == ["path", "usecase_id"] and detail[0]["type"] == "int_parsing"


def test_the_detail_route_shares_the_503_codes_and_the_guards(tmp_path):
    assert _client(GuiBridge()).get("/api/usecases/1", headers=HEADERS).json() == {
        "available": False, "reason": "source-not-in-composition"}
    broken = _bound(tmp_path, raw=b"{broken")
    response = broken.get("/api/usecases/1", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"available": False, "reason": "source-invalid"}
    assert broken.get("/api/usecases/1").status_code == 401 and broken.get("/api/usecases/1/").status_code == 401
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert broken.request(method, "/api/usecases/1", headers=HEADERS).status_code == 405


def test_the_real_page_script_opens_the_detail_of_a_listed_usecase(tmp_path, node):
    client = _bound(tmp_path)
    listing = client.get("/api/usecases", headers=HEADERS).json()
    details = {row["id"]: client.get(f"/api/usecases/{row['id']}", headers=HEADERS).json() for row in listing["usecases"]}
    view = _page_view(200, listing, details=details, click=4)  # "e fünfte": score 75
    assert view["action"] == ""
    assert view["detail"]["id"] == "Usecase #5" and view["detail"]["title"] == "e fünfte"
    assert view["detail"]["result"] == "Definition geprüft" and view["detail"]["score"] == "75 %"
    assert view["detail"]["workflow"] == "–" and view["detail"]["author"] == "–"  # null columns are shown as unknown


def test_negative_control_the_page_shows_not_found_for_a_missing_row(tmp_path, node):
    client = _bound(tmp_path)
    listing = client.get("/api/usecases", headers=HEADERS).json()
    gone = client.get("/api/usecases/99", headers=HEADERS).json()  # what BACH answers for an id that is not there
    view = _page_view(200, listing, details={1: gone}, click=0)
    assert view["detail"]["id"] == "" and view["error"] == "Nicht gefunden"  # open() reports it in uc-list-error (usecases.astro:83)


# ---- limits, ids, capabilities, methods (review R27) ----------------------------------------------------------------

def _one(**fields) -> bytes:
    return json.dumps({"usecases": [{"id": 1, "title": "t", **fields}]}).encode("utf-8")


@pytest.mark.parametrize("name, raw", [
    ("title too long", _one(title="x" * 1001)),
    ("description too long", _one(description="x" * 100_001)),
    ("module too long", _one(module="x" * 201)),
    ("id above int64", _one(id=2**63)),
    ("too many rows", json.dumps({"usecases": [{"id": i, "title": "t"} for i in range(1, 10_002)]}).encode("utf-8")),
    ("meta text too long", json.dumps({"_meta": {"generated_at": "x" * 257}, "usecases": []}).encode("utf-8")),
    ("deep nesting", b"[" * 200_000 + b"]" * 200_000),
    ("deep nesting in a field", b'{"usecases": [{"id": 1, "title": "t", "description": ' + b"[" * 100_000 + b"]" * 100_000 + b"}]}"),
    ("int with 5000 digits", b'{"usecases": [{"id": 1' + b"0" * 5000 + b', "title": "t"}]}'),
], ids=lambda value: value if isinstance(value, str) else "raw")
def test_field_depth_and_size_limits_are_source_invalid_not_unreadable(tmp_path, name, raw):
    response = _bound(tmp_path, raw=raw).get("/api/usecases", headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"available": False, "reason": "source-invalid"}, name


def test_values_at_the_limits_are_accepted(tmp_path):
    body = _bound(tmp_path, raw=_one(title="x" * 1000, description="y" * 100_000, id=2**63 - 1)).get(
        "/api/usecases", headers=HEADERS).json()
    assert body["success"] is True and body["stats"]["total"] == 1


@pytest.mark.parametrize("path", ["/api/usecases/" + "9" * 5000, "/api/usecases/" + "9" * 20, "/api/usecases/+" + "1" * 20])
def test_an_overlong_numeric_id_is_a_422_never_a_500(tmp_path, path):
    response = _bound(tmp_path).get(path, headers=HEADERS)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["path", "usecase_id"]


def test_the_longest_accepted_id_is_a_clean_not_found(tmp_path):
    response = _bound(tmp_path).get("/api/usecases/" + "9" * 19, headers=HEADERS)
    assert response.status_code == 200 and response.json() == {"success": False, "error": "Nicht gefunden"}


@pytest.mark.parametrize("raw, available, reason", [
    (None, True, None), (b"{broken", False, "source-invalid"), (b"[" * 100_000, False, "source-invalid"),
    (_one(title="x" * 2000), False, "source-invalid")],
    ids=["valid", "broken", "deep", "long-title"])
def test_the_capability_follows_the_readable_valid_source(tmp_path, raw, available, reason):
    module = tmp_path / "ws" / "modules" / "ellmos-tests"
    module.mkdir(parents=True)
    (module / "usecases.json").write_bytes(json.dumps(SOURCE).encode("utf-8") if raw is None else raw)
    bridge = GuiBridge(usecases=usecases_reader(_component(module), module.parent))
    endpoint = {item["path"]: item for item in bridge.capabilities()["endpoints"]}["/api/usecases"]
    assert (endpoint["available"], endpoint["reason"]) == (available, reason)
    assert (endpoint["provider"] is not None) == available


def test_the_capability_of_a_missing_file_carries_the_same_code_as_the_get(tmp_path):
    module = tmp_path / "ws" / "modules" / "ellmos-tests"
    module.mkdir(parents=True)
    bridge = GuiBridge(usecases=usecases_reader(_component(module), module.parent))
    endpoint = {item["path"]: item for item in bridge.capabilities()["endpoints"]}["/api/usecases"]
    get = _client(bridge).get("/api/usecases", headers=HEADERS).json()
    assert endpoint["available"] is False and endpoint["reason"] == get["reason"] == "source-missing"


@pytest.mark.parametrize("path", ["/api/usecases", "/api/usecases/", "/api/usecases/1", "/api/usecases/1/"])
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_writes_are_401_without_a_session_and_405_with_one_on_list_and_detail(tmp_path, path, method):
    client = _bound(tmp_path)
    anonymous = client.request(method, path)
    assert anonymous.status_code == 401 and "usecases" not in anonymous.text.lower()
    assert client.request(method, path, headers=HEADERS).status_code == 405
