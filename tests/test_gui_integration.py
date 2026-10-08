"""Synthetic release/adapter checks; no network, service or production install."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
import zipfile
from types import ModuleType

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools import gui_bridge, ocean_dev
from tools.fetch_place import place_gui_release
from tools.gui_bridge import GuiBridge, mount_gui_bridge, policy_metadata_reader
from tools.gui_release import GuiReleaseError, verify_gui_archive, verify_installed_gui
from tools.host_adapters import known_adapters
from tools.ocean_lifecycle import RuntimeProvider, _ellmos_core_runtime_spec
from tools.ocean_origin import OceanOriginApp
from tools.resolve_bundles import canonical_hash

COMMIT = "a" * 40


def _archive(root, *, commit=COMMIT, extra=None, missing=None, wrong_file=False):
    files = {"index.html": b"<html><body>Gemeinsame Oberfl\xc3\xa4che</body></html>",
             "tasks/index.html": b"<html><body>Aufgaben</body></html>", "_astro/ui.js": b"console.log('gui');"}
    payload = {"dist/" + name: data for name, data in files.items()}
    payload["dist/dist-manifest.json"] = json.dumps({"schema": "ellmos-system-gui.dist.v1",
        "source_commit": commit, "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}).encode()
    payload["LICENSE"] = b"MIT test fixture"
    if missing:
        payload.pop(missing)
    if wrong_file:
        payload["dist/index.html"] = b"changed"
    payload.update(extra or {})
    path = root / "gui.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", [{"commit": "b" * 40}, {"missing": "LICENSE"},
    {"missing": "dist/tasks/index.html"}, {"wrong_file": True},
    {"extra": {"../outside": b"bad"}}, {"extra": {"dist/undeclared.txt": b"bad"}},
    {"extra": {"DIST/index.html": b"collision"}}, {"extra": {"dist/CON.txt": b"bad"}}])
def test_bad_release_refused_before_placement(tmp_path, change):
    archive, digest = _archive(tmp_path, **change)
    with pytest.raises(GuiReleaseError):
        verify_gui_archive(archive, COMMIT, digest)
    assert not (tmp_path / "workspace").exists()


def test_archive_pin_is_required(tmp_path):
    archive, _ = _archive(tmp_path)
    with pytest.raises(GuiReleaseError):
        verify_gui_archive(archive, COMMIT, "0" * 64)


def test_real_place_and_existing_journal_rollback(tmp_path):
    archive, digest = _archive(tmp_path)
    release = verify_gui_archive(archive, COMMIT, digest)
    workspace = tmp_path / "workspace"
    prospective = place_gui_release(release, workspace, apply=False)
    assert prospective.action == "planned" and not workspace.exists()
    log = workspace / "ocean-dev.activation-log.json"
    ocean_dev.preflight_activation_log(log, [prospective], [])
    outcome = place_gui_release(release, workspace, apply=True)
    ocean_dev.write_activation_log(log, [outcome], [])
    installed = workspace / "modules" / "ellmos-system-gui"
    assert verify_installed_gui(installed, COMMIT, digest).payload == release.payload
    assert place_gui_release(release, workspace, apply=True).action == "present-pinned-provider"
    adapter = known_adapters()["claude-code"](skills_dir=workspace / "skills")
    assert ocean_dev.do_rollback(log, adapter, workspace) == 0
    assert not installed.exists()


def test_foreign_destination_and_tampering_never_overwritten(tmp_path):
    archive, digest = _archive(tmp_path)
    release = verify_gui_archive(archive, COMMIT, digest)
    workspace = tmp_path / "workspace"
    dest = workspace / "modules" / "ellmos-system-gui"
    dest.mkdir(parents=True)
    marker = dest / "foreign.txt"
    marker.write_text("preserve")
    with pytest.raises(GuiReleaseError):
        place_gui_release(release, workspace, apply=True)
    assert marker.read_text() == "preserve"
    marker.unlink()
    dest.rmdir()
    place_gui_release(release, workspace, apply=True)
    (dest / "dist" / "index.html").write_text("tampered")
    with pytest.raises(GuiReleaseError):
        verify_installed_gui(dest, COMMIT, digest)
    # Even changing both the receipt and manifest cannot forge the pinned ZIP.
    changed = b"tampered"
    manifest_path = dest / "dist" / "dist-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["index.html"] = hashlib.sha256(changed).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    receipt_path = dest / ".ocean-gui-release.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["dist/index.html"] = hashlib.sha256(changed).hexdigest()
    receipt["files"]["dist/dist-manifest.json"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(GuiReleaseError, match="Originalarchiv"):
        verify_installed_gui(dest, COMMIT, digest)


def test_transaction_cli_wires_gui_plan_apply_and_rollback(tmp_path, capsys):
    archive, digest = _archive(tmp_path)
    bundles = tmp_path / "bundles"
    bundle_dir = bundles / "manifests" / "bundles" / "gui-fixture"
    bundle_dir.mkdir(parents=True)
    bundle = {"schema": "ellmos.bundle.v1", "id": "gui-fixture", "version": "1.0.0", "components": [], "choice_groups": []}
    bundle["content_hash"] = canonical_hash(bundle)
    (bundle_dir / "bundle.v1.json").write_text(json.dumps(bundle))
    system = tmp_path / "system.json"
    system.write_text(json.dumps({"schema": "ellmos.system.v1", "id": "fixture", "authority": {"runtime_authority": False},
                                 "bundle_refs": [{"ref": "gui-fixture", "content_hash": bundle["content_hash"]}]}))
    catalog, registry, bindings = (tmp_path / name for name in ("catalog.json", "registry.json", "bindings.json"))
    catalog.write_text('{"modules": []}')
    registry.write_text('{"components": []}')
    overlay = {"schema": "ellmos.open-ocean-component-bindings.v1", "id": "fixture", "version": "1.0.0",
               "authority": {"kind": "integration-overlay", "runtime_authority": False}, "bindings": {}}
    overlay["content_hash"] = canonical_hash(overlay)
    bindings.write_text(json.dumps(overlay))
    workspace = tmp_path / "workspace"
    args = ["--bundles-root", str(bundles), "--system-manifest", str(system), "--modules-catalog", str(catalog),
            "--skills-registry", str(registry), "--component-bindings", str(bindings), "--workspace", str(workspace),
            "--gui-archive", str(archive), "--gui-source-commit", COMMIT, "--gui-archive-sha256", digest,
            "--expected-components-json", '["module:ellmos-system-gui"]', "--json"]
    assert ocean_dev.main(args) == 0
    assert not workspace.exists()
    assert ocean_dev.main(args + ["--apply"]) == 0
    output = capsys.readouterr().out
    assert "shared-gui.host" in output
    log = workspace / "ocean-dev.activation-log.json"
    assert json.loads(log.read_text())["entries"][0]["ref"] == "module:ellmos-system-gui"
    assert ocean_dev.main(["--rollback", str(log), "--workspace", str(workspace)]) == 0
    assert not (workspace / "modules" / "ellmos-system-gui").exists()


def _scope_recipe(tmp_path, module_ids):
    bundles = tmp_path / "bundles"
    bundle_dir = bundles / "manifests" / "bundles" / "scope-fixture"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    modules = []
    components = []
    for module_id in module_ids:
        source = tmp_path / "sources" / module_id
        source.mkdir(parents=True, exist_ok=True)
        (source / "module.txt").write_text("synthetic dependency")
        modules.append({"id": module_id, "source_of_truth": {"type": "local-directory"},
                        "resolved_source": str(source), "provides": [], "requires": []})
        components.append({"type": "module", "ref": {"ref": "module:" + module_id}, "requirement": "required"})
    bundle = {"schema": "ellmos.bundle.v1", "id": "scope-fixture", "version": "1.0.0", "components": components, "choice_groups": []}
    bundle["content_hash"] = canonical_hash(bundle)
    (bundle_dir / "bundle.v1.json").write_text(json.dumps(bundle))
    system = tmp_path / "system.json"
    system.write_text(json.dumps({"schema": "ellmos.system.v1", "id": "fixture", "authority": {"runtime_authority": False},
                                 "bundle_refs": [{"ref": "scope-fixture", "content_hash": bundle["content_hash"]}]}))
    catalog, registry, bindings = (tmp_path / name for name in ("catalog.json", "registry.json", "bindings.json"))
    catalog.write_text(json.dumps({"modules": modules}))
    registry.write_text('{"components": []}')
    overlay = {"schema": "ellmos.open-ocean-component-bindings.v1", "id": "fixture", "version": "1.0.0",
               "authority": {"kind": "integration-overlay", "runtime_authority": False}, "bindings": {}}
    overlay["content_hash"] = canonical_hash(overlay)
    bindings.write_text(json.dumps(overlay))
    return ["--bundles-root", str(bundles), "--system-manifest", str(system), "--modules-catalog", str(catalog),
            "--skills-registry", str(registry), "--component-bindings", str(bindings), "--workspace", str(tmp_path / "workspace"), "--json"]


def _gui_scope_args(tmp_path):
    archive, digest = _archive(tmp_path)
    return ["--gui-archive", str(archive), "--gui-source-commit", COMMIT, "--gui-archive-sha256", digest]


def test_gui_only_approved_scope_cannot_place_system_manifest_dependency(tmp_path, monkeypatch):
    args = _scope_recipe(tmp_path, ["unapproved-dependency"]) + _gui_scope_args(tmp_path)
    monkeypatch.setattr(ocean_dev, "plan_and_fetch", lambda *args, **kwargs: pytest.fail("Fetch reached before scope rejection"))
    monkeypatch.setattr(ocean_dev, "activate_skills", lambda *args, **kwargs: pytest.fail("Activate reached before scope rejection"))
    assert ocean_dev.main(args + ["--expected-components-json", '["module:ellmos-system-gui"]', "--apply"]) == 3
    assert not (tmp_path / "workspace").exists()


def test_fresh_resolved_change_after_good_preplan_still_stops_before_mutation(tmp_path, monkeypatch, capsys):
    args = _scope_recipe(tmp_path, []) + _gui_scope_args(tmp_path) + ["--expected-components-json", '["module:ellmos-system-gui"]']
    assert ocean_dev.main(args) == 0
    capsys.readouterr()
    # Same approved plan and paths; composition files changed after the preplan.
    _scope_recipe(tmp_path, ["late-dependency"])
    monkeypatch.setattr(ocean_dev, "plan_and_fetch", lambda *args, **kwargs: pytest.fail("Fetch reached before fresh scope rejection"))
    assert ocean_dev.main(args + ["--apply"]) == 3
    assert "fresh resolved component scope" in capsys.readouterr().err
    assert not (tmp_path / "workspace").exists()


def test_full_explicit_dependency_scope_installs_and_rolls_back_without_escalation(tmp_path):
    scope = json.dumps(["module:ellmos-system-gui", "module:dependency"])
    args = _scope_recipe(tmp_path, ["dependency"]) + _gui_scope_args(tmp_path) + ["--expected-components-json", scope]
    assert ocean_dev.main(args + ["--apply"]) == 0
    workspace = tmp_path / "workspace"
    assert (workspace / "modules" / "dependency" / "module.txt").is_file()
    assert (workspace / "modules" / "ellmos-system-gui" / "dist" / "index.html").is_file()
    log = workspace / "ocean-dev.activation-log.json"
    rollback = ["--rollback", str(log), "--workspace", str(workspace), "--expected-components-json"]
    assert ocean_dev.main(rollback + ['["module:ellmos-system-gui"]']) == 4
    assert (workspace / "modules" / "dependency").exists()
    assert (workspace / "modules" / "ellmos-system-gui").exists()
    assert ocean_dev.main(rollback + [scope]) == 0
    assert not (workspace / "modules" / "dependency").exists()
    assert not (workspace / "modules" / "ellmos-system-gui").exists()


@pytest.mark.parametrize("value", ['"module:one"', '["module:*"]', '["module:one", "module:one"]', 'not-json'])
def test_component_scope_requires_full_exact_unique_ref_array(value):
    with pytest.raises(ocean_dev.ResolveError):
        ocean_dev.expected_component_scope(value)


def test_adapter_auth_unavailable_redaction_and_no_apply():
    app = FastAPI()
    def auth(request):
        if request.headers.get("x-test-role") not in {"user", "admin"}:
            raise HTTPException(401)
    def admin(request):
        auth(request)
        if request.headers.get("x-test-role") != "admin":
            raise HTTPException(403)
    bridge = GuiBridge(status=lambda: {"schema": "fixture", "runtime": {"id": "core", "control": "stopped", "url": "secret"},
                                      "workspace": "private", "token": "secret"})
    mount_gui_bridge(app, bridge, auth, admin)
    with TestClient(app) as client:
        assert client.get("/api/gui/capabilities").status_code == 401
        user, administrator = {"x-test-role": "user"}, {"x-test-role": "admin"}
        caps = client.get("/api/gui/capabilities", headers=user).json()
        assert caps["schema"] == "ellmos.gui.capabilities.v1"
        assert all(not item["runtime_verified"] for item in caps["endpoints"])
        assert all(item["status"] == "unavailable" for item in caps["pages"])
        assert not next(item for item in caps["endpoints"] if item["path"] == "/api/installer/plan")["available"]
        assert client.get("/api/installer/status", headers=user).status_code == 403
        assert client.get("/api/installer/plan", headers=administrator).status_code == 503
        assert client.get("/api/governance/policy-registry", headers=administrator).status_code == 503
        assert client.get("/api/governance/effective-policy", headers=administrator).status_code == 503
        assert client.get("/api/agents/native/slots", headers=administrator).status_code == 503
        assert client.post("/api/agents/native/tasks", headers=administrator).status_code == 503
        result = client.get("/api/installer/status", headers=administrator)
        assert result.status_code == 200 and "private" not in result.text and "secret" not in result.text
        assert client.post("/api/installer/apply", headers=administrator).status_code == 404


def test_policy_alias_forwards_only_bounded_search_filters():
    observed = []
    def reader(**kwargs):
        observed.append(kwargs)
        return {"entries": []}
    app = FastAPI()
    mount_gui_bridge(app, GuiBridge(policies=reader), lambda request: None, lambda request: None)
    with TestClient(app) as client:
        assert client.get("/api/governance/policy-registry?scope=global&query=regel&consumer=ocean&path=private").status_code == 200
        assert observed[-1] == {"scope": "global", "query": "regel", "consumer": "ocean"}
        assert client.get("/api/decisions").status_code == 200
        assert observed[-1] == {"kind": "decision"}
        assert client.get("/api/governance/policy-registry?query=" + "x" * 513).status_code == 422
        caps = client.get("/api/gui/capabilities").json()
        assert isinstance(caps["modules"], dict)
        assert isinstance(caps["module_sources"], list)
        assert next(item for item in caps["endpoints"] if item["path"] == "/api/governance/policy-registry")["available"]
        assert not next(item for item in caps["endpoints"] if item["path"] == "/api/governance/effective-policy")["available"]


def test_policy_adapter_reuses_native_load_and_reverifies_without_source_reads(tmp_path, monkeypatch):
    source = tmp_path / "module"
    package = source / "src" / "policy_registry"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "registry.py").write_text("")
    for name in list(sys.modules):
        if name == "policy_registry" or name.startswith("policy_registry."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(source / "src"))
    registry = tmp_path / "registry.json"
    registry.write_text("synthetic")
    checks, loads = [], []
    monkeypatch.setattr(gui_bridge, "verify_bound_provider", lambda path, binding: checks.append(path))
    entries = [{"id": "public", "kind": "policy", "title": "Öffentliche Regel", "status": "active", "version": "1", "privacy": "public", "source": {"uri": "never-open"}},
               {"id": "secret", "kind": "rule", "title": "private", "status": "active", "version": "1", "privacy": "private"}]
    class NativeRegistry:
        def __init__(self, path):
            loads.append(path)
        def load(self):
            return {"entries": entries}
    native = ModuleType("policy_registry.registry")
    native.__file__ = str(package / "registry.py")
    native.__spec__ = gui_bridge.importlib.machinery.PathFinder.find_spec("policy_registry.registry", [str(package)])
    native.PolicyRegistry = NativeRegistry
    monkeypatch.setattr(gui_bridge.importlib, "import_module", lambda name: native)
    reader = policy_metadata_reader({"detail": {"binding": {"commit": COMMIT, "catalog_id": "policy-registry"}, "local_path": str(source)}}, registry)
    result = reader()
    assert len(checks) == 2 and loads == [registry]
    assert result["counts"]["total"] == 2 and len(result["entries"]) == 1
    assert "secret" not in json.dumps(result) and "never-open" not in json.dumps(result)


def _synthetic_policy_source(tmp_path, monkeypatch, *, parent_code=""):
    source = tmp_path / "bound"
    package = source / "src" / "policy_registry"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(parent_code, encoding="utf-8")
    (package / "registry.py").write_text(
        "import json\nfrom pathlib import Path\nclass PolicyRegistry:\n"
        "    def __init__(self, path): self.path = Path(path)\n"
        "    def load(self):\n"
        "        if not self.path.exists(): return {'entries': []}\n"
        "        return json.loads(self.path.read_text())\n", encoding="utf-8")
    for name in list(sys.modules):
        if name == "policy_registry" or name.startswith("policy_registry."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(source / "src"))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(gui_bridge, "verify_bound_provider", lambda path, binding: None)
    registry = tmp_path / "metadata.json"
    registry.write_text('{"entries": []}')
    component = {"detail": {"binding": {"commit": COMMIT, "catalog_id": "policy-registry"}, "local_path": str(source)}}
    return source, registry, component


def test_foreign_parent_is_rejected_before_its_side_effect(tmp_path, monkeypatch):
    _, registry, component = _synthetic_policy_source(tmp_path, monkeypatch)
    foreign = tmp_path / "foreign"
    package = foreign / "policy_registry"
    package.mkdir(parents=True)
    marker = tmp_path / "foreign-executed"
    (package / "__init__.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    (package / "registry.py").write_text("raise AssertionError('foreign registry executed')")
    monkeypatch.syspath_prepend(str(foreign))
    with pytest.raises(gui_bridge.BridgeUnavailable, match="anderen Quelle"):
        policy_metadata_reader(component, registry)
    assert not marker.exists()
    assert "policy_registry" not in sys.modules


@pytest.mark.parametrize("cached_name", ["policy_registry", "policy_registry.registry"])
def test_foreign_module_cache_is_rejected_before_parent_or_hook_executes(tmp_path, monkeypatch, cached_name):
    marker = tmp_path / "bound-parent-executed"
    _, registry, component = _synthetic_policy_source(tmp_path, monkeypatch,
        parent_code=f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    foreign = ModuleType(cached_name)
    foreign.__file__ = str(tmp_path / "foreign" / "registry.py")
    hooks = []
    foreign.__getattr__ = lambda name: hooks.append(name)
    monkeypatch.setitem(sys.modules, cached_name, foreign)
    with pytest.raises(gui_bridge.BridgeUnavailable, match="fremden Modulcache"):
        policy_metadata_reader(component, registry)
    assert hooks == []
    assert not marker.exists()


@pytest.mark.parametrize("failure", ["removed-before", "removed-during", "unreadable"])
def test_registry_loss_or_unreadability_is_503_per_read(tmp_path, monkeypatch, failure):
    _, registry, component = _synthetic_policy_source(tmp_path, monkeypatch)
    reader = policy_metadata_reader(component, registry)
    if failure == "removed-before":
        registry.unlink()
    elif failure == "removed-during":
        native = sys.modules["policy_registry.registry"]
        def empty_after_removal(self):
            registry.unlink()
            return {"entries": []}
        monkeypatch.setattr(native.PolicyRegistry, "load", empty_after_removal)
    else:
        original = Path.read_bytes
        def deny_registry(path):
            if path == registry:
                raise PermissionError("private diagnostic")
            return original(path)
        monkeypatch.setattr(Path, "read_bytes", deny_registry)
    app = FastAPI()
    mount_gui_bridge(app, GuiBridge(policies=reader), lambda request: None, lambda request: None)
    with TestClient(app) as client:
        response = client.get("/api/policies")
    assert response.status_code == 503
    assert response.json()["available"] is False
    assert "private diagnostic" not in response.text


def test_optional_exact_native_policy_provider_with_synthetic_registry(tmp_path, monkeypatch):
    source_value = os.environ.get("OCEAN_POLICY_TEST_SOURCE")
    if not source_value:
        pytest.skip("requires an explicitly supplied, clean pinned policy-registry checkout")
    source = Path(source_value)
    for name in list(sys.modules):
        if name == "policy_registry" or name.startswith("policy_registry."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(source / "src"))
    monkeypatch.setattr(gui_bridge.sys, "dont_write_bytecode", True)
    binding = {"catalog_id": "policy-registry", "commit": "08add2bb598e9d301d225221ebef5721a7a0e833",
               "repository": "https://github.com/ellmos-ai/policy-registry.git",
               "provider_manifest": "ellmos-module.v2.json", "required_provides": ["policy.registry"]}
    entry = {"id": "fixture-public", "kind": "policy", "title": "Öffentliche Testregel", "scope": "global",
             "owner": "fixture", "priority": 1, "precedence": 1, "version": "1", "privacy": "public",
             "source": {"uri": "https://example.invalid/never-open"}, "consumers": ["ocean"],
             "status": "active", "adoption": "adopted"}
    private = {**entry, "id": "fixture-private", "privacy": "private", "title": "Private fixture"}
    registry_path = tmp_path / "synthetic-registry.json"
    registry_path.write_text(json.dumps({"schema": "ellmos.policy-registry.v1", "entries": [entry, private]}), encoding="utf-8")
    reader = policy_metadata_reader({"detail": {"binding": binding, "local_path": str(source)}}, registry_path)
    result = reader(scope="global", consumer="ocean", query="Testregel", kind="policy")
    assert result["counts"]["total"] == 1
    assert result["entries"][0]["id"] == "fixture-public"
    assert result["entries"][0]["verification"]["source_hash_verified"] is False
    assert "example.invalid" not in json.dumps(result)
    # A valid already-loaded package cache remains usable as well.
    assert policy_metadata_reader({"detail": {"binding": binding, "local_path": str(source)}}, registry_path)()["counts"]["total"] == 2


def _asgi_request(app, path, method="GET"):
    events = []
    async def receive():
        return {"type": "http.request", "body": b""}
    async def send(event):
        events.append(event)
    asyncio.run(app({"type": "http", "path": path, "method": method}, receive, send))
    return events[0], b"".join(item.get("body", b"") for item in events)


def test_static_gui_declared_pages_head_and_provider_boundary(tmp_path):
    archive, digest = _archive(tmp_path)
    release = verify_gui_archive(archive, COMMIT, digest)
    seen = []
    async def provider(scope, receive, send):
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b"provider"})
    app = OceanOriginApp(provider, gui=release)
    assert _asgi_request(app, "/control/")[0]["status"] == 200
    assert "Oberfläche" in _asgi_request(app, "/control/")[1].decode()
    assert _asgi_request(app, "/tasks")[0]["status"] == 200
    assert _asgi_request(app, "/_astro/ui.js", "HEAD")[1] == b""
    for path in ("/api/installer/status", "/login", "/../LICENSE", "/dist-manifest.json"):
        assert _asgi_request(app, path)[0]["status"] == 404
    assert seen == ["/api/installer/status", "/login", "/../LICENSE", "/dist-manifest.json"]


def test_lifecycle_selects_verified_astro_consumer_without_jinja(tmp_path):
    archive, digest = _archive(tmp_path)
    workspace = tmp_path / "workspace"
    outcome = place_gui_release(verify_gui_archive(archive, COMMIT, digest), workspace, apply=True)
    core = tmp_path / "core"
    (core / "src" / "ellmos_core").mkdir(parents=True)
    provider = RuntimeProvider("ellmos-core", "module:core", core, {"service": "serve"}, "ellmos-core", {})
    components = [{"kind": "module", "status": "resolved", "detail": {"provides": ["shared-gui.host"],
                   "local_path": outcome.detail["dest"], "source_commit": COMMIT, "archive_sha256": digest}}]
    spec = _ellmos_core_runtime_spec(provider, components, workspace, workspace / "manifest.json", "127.0.0.1", 8810)
    assert spec["env"]["ELLMOS_CORE_CONSOLE_ENABLED"] == "0"
    assert spec["env"]["OCEAN_GUI_SOURCE_COMMIT"] == COMMIT
    assert spec["command"][1].endswith("ocean_runtime.py")
    assert spec["runtime_url"].endswith("/control/")
