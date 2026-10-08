"""Native, read-only GUI consumer routes. No apply/grant authority lives here."""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

try:
    from .fetch_place import verify_bound_provider
    from .gui_release import GuiReleaseError, VerifiedGuiRelease, verify_installed_gui
except ImportError:  # ocean_runtime.py direct entry point
    from fetch_place import verify_bound_provider
    from gui_release import GuiReleaseError, VerifiedGuiRelease, verify_installed_gui

SCHEMA = "ellmos.gui.capabilities.v1"
BRIDGE_CONFIG = "ocean.gui-bridge.json"
PAGE_ROUTES = {
    "overview": "/", "tasks": "/tasks", "life": "/life", "memory": "/memory",
    "domains": "/domains", "artefakte": "/artefakte", "skills": "/skills",
    "software": "/skills/software", "plugins": "/skills/plugins", "mcp": "/skills/mcp",
    "blueprints": "/agenten/blueprints", "fabrika": "/agenten/fabrika",
    "marblerun": "/agenten/marblerun", "running": "/agenten/running",
    "sessions": "/agenten/sessions", "governance": "/governance",
    "funk": "/governance/funk", "logs": "/governance/logs",
    "usecases": "/governance/usecases", "settings": "/settings",
}


class BridgeUnavailable(RuntimeError):
    pass


def _policy_spec(spec, name: str, expected: Path, package_root: Path) -> None:
    """Inspect import metadata only; never execute a loader to discover origin."""
    if type(spec) is not importlib.machinery.ModuleSpec or spec.name != name or not isinstance(spec.origin, str):
        raise BridgeUnavailable("policy-registry hat keine nachprüfbare Importherkunft.")
    if type(spec.loader) is not importlib.machinery.SourceFileLoader:
        raise BridgeUnavailable("policy-registry verwendet keinen gebundenen Python-Quellenloader.")
    origin = Path(spec.origin).resolve()
    loader_path = vars(spec.loader).get("path")
    if origin != expected.resolve() or not origin.is_relative_to(package_root) or not isinstance(loader_path, str) or Path(loader_path).resolve() != origin:
        raise BridgeUnavailable("policy-registry würde aus einer anderen Quelle importiert.")
    locations = spec.submodule_search_locations
    if expected.name == "__init__.py":
        if not isinstance(locations, (list, tuple)) or len(locations) != 1 or not isinstance(locations[0], str) or Path(locations[0]).resolve() != origin.parent:
            raise BridgeUnavailable("policy-registry hat einen fremden Paket-Suchpfad.")
    elif locations is not None:
        raise BridgeUnavailable("policy-registry hat einen unerwarteten Untermodul-Suchpfad.")


def _policy_cache(package_root: Path) -> None:
    for name, loaded in sys.modules.copy().items():
        if name != "policy_registry" and not name.startswith("policy_registry."):
            continue
        if type(loaded) is not ModuleType:
            raise BridgeUnavailable("policy-registry enthält einen nicht prüfbaren Modulcache.")
        # Direct base access avoids running a foreign module's __getattr__ hook.
        state = ModuleType.__getattribute__(loaded, "__dict__")
        filename = state.get("__file__")
        relative = name.split(".")[1:]
        target = package_root.joinpath(*relative) if relative else package_root
        candidates = [target.with_suffix(".py"), target / "__init__.py"] if relative else [package_root / "__init__.py"]
        if not isinstance(filename, str) or Path(filename).resolve() not in [candidate.resolve() for candidate in candidates]:
            raise BridgeUnavailable("policy-registry enthält einen fremden Modulcache.")
        expected = Path(filename)
        _policy_spec(state.get("__spec__"), name, expected, package_root)
        if expected.name == "__init__.py":
            paths = state.get("__path__")
            if not isinstance(paths, (list, tuple)) or len(paths) != 1 or not isinstance(paths[0], str) or Path(paths[0]).resolve() != expected.resolve().parent:
                raise BridgeUnavailable("policy-registry enthält einen fremden Paketcache-Suchpfad.")


def _import_bound_policy(source: Path):
    package_root = (source / "src" / "policy_registry").resolve()
    if not package_root.is_relative_to(source.resolve()) or not (package_root / "__init__.py").is_file() or not (package_root / "registry.py").is_file():
        raise BridgeUnavailable("policy-registry fehlt innerhalb des geprüften Checkouts.")
    _policy_cache(package_root)
    # find_spec on a nested name imports its parent. Only inspect the top-level
    # name, then inspect the submodule against the checked package path directly.
    parent_spec = importlib.util.find_spec("policy_registry")
    _policy_spec(parent_spec, "policy_registry", package_root / "__init__.py", package_root)
    child_spec = importlib.machinery.PathFinder.find_spec("policy_registry.registry", [str(package_root)])
    _policy_spec(child_spec, "policy_registry.registry", package_root / "registry.py", package_root)
    module = importlib.import_module("policy_registry.registry")
    _policy_cache(package_root)
    state = ModuleType.__getattribute__(module, "__dict__")
    _policy_spec(state.get("__spec__"), "policy_registry.registry", package_root / "registry.py", package_root)
    return module


def _registry_snapshot(path: Path) -> bytes:
    try:
        if not path.is_file():
            raise BridgeUnavailable("Keine lesbare lokale Registry verfügbar.")
        return path.read_bytes()
    except OSError as exc:
        raise BridgeUnavailable("Keine lesbare lokale Registry verfügbar.") from exc


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    """Whitelist public structural evidence; never echo paths, commands or tokens."""
    runtime = report.get("runtime") or {}
    readiness = report.get("readiness") or {}
    composition = report.get("composition") or {}
    transaction = report.get("transaction") or {}
    return {
        "schema": report.get("schema"),
        "runtime": {key: runtime[key] for key in ("id", "control", "health") if key in runtime},
        "composition": {key: composition[key] for key in ("id", "mode", "schema") if key in composition},
        "readiness": {key: readiness[key] for key in ("runtime_host", "full_composition", "required_components_missing") if key in readiness},
        "verification": {"all_ok": (transaction.get("verify") or {}).get("all_ok", False),
                         "scope": "adapter", "runtime_verified": False},
    }


def policy_metadata_reader(component: dict[str, Any], registry_path: Path) -> Callable[[], dict]:
    """Reuse the installed policy-registry API after checking its exact binding.

    Only summary counts and public metadata leave this adapter. Canonical source
    files, rule texts, decision chains and source URIs are never opened here.
    """
    detail = component.get("detail") or {}
    binding = detail.get("binding")
    if not isinstance(binding, dict) or binding.get("catalog_id") != "policy-registry" or not detail.get("local_path"):
        raise BridgeUnavailable("policy-registry benötigt eine exakte Anbieterbindung.")
    source = Path(detail["local_path"])
    verify_bound_provider(source, binding)
    module = _import_bound_policy(source)
    _registry_snapshot(registry_path)

    def read(*, query: str = "", scope: str | None = None, consumer: str | None = None, kind: str | None = None) -> dict:
        # Reverify the code identity at readback, not merely at bootstrap.
        verify_bound_provider(source, binding)
        before = _registry_snapshot(registry_path)
        registry = module.PolicyRegistry(registry_path)
        entries = registry.search(query, scope=scope, consumer=consumer, kind=kind) if any((query, scope, consumer, kind)) else registry.load()["entries"]
        if _registry_snapshot(registry_path) != before:
            raise BridgeUnavailable("Die lokale Registry änderte sich während des Lesezugriffs.")
        return {
            "schema": "ellmos.open-ocean.policy-metadata.v1", "read_only": True,
            "counts": {"total": len(entries), "kind": dict(Counter(item["kind"] for item in entries)),
                       "status": dict(Counter(item["status"] for item in entries))},
            "entries": [{**{key: item[key] for key in ("id", "kind", "title", "status", "version")},
                         "hash": item.get("hash"),
                         "verification": {"state": "metadata-validated", "source_hash_verified": False}}
                        for item in entries if item["privacy"] == "public"],
        }
    return read


class GuiBridge:
    def __init__(self, *, gui: VerifiedGuiRelease | None = None,
                 plan: Callable[[], dict] | None = None, status: Callable[[], dict] | None = None,
                 policies: Callable[[], dict] | None = None, modules: list[dict] | None = None):
        self.gui = gui
        self.providers = {"detect": self.detect, "plan": plan, "status": status, "policies": policies}
        self.modules = modules or []

    def detect(self) -> dict:
        return {"schema": "ellmos.open-ocean.installer-detect.v1", "read_only": True,
                "provider": {"id": "open-ocean", "version": "0.1.2"},
                "native": {name: provider is not None for name, provider in self.providers.items() if name != "detect"},
                "apply": {"available": False, "reason": "Nur die externe Installer-Approval-/Grant-Kette darf Änderungen ausführen."},
                "runtime_verified": False, "verification_scope": "adapter"}

    def invoke(self, name: str, **kwargs) -> dict:
        provider = self.providers.get(name)
        if provider is None:
            raise BridgeUnavailable("Kein nativer Anbieter konfiguriert.")
        try:
            report = provider(**kwargs) if kwargs else provider()
            return _summary(report) if name in {"plan", "status"} else report
        except BridgeUnavailable:
            raise
        except Exception as exc:
            # Native diagnostics can contain private paths or credentials.
            raise BridgeUnavailable("Der native Leseanbieter konnte keine geprüfte Antwort liefern.") from exc

    def capabilities(self) -> dict:
        endpoints = []
        for path, provider in [("/api/gui/capabilities", True),
                               *(("/api/installer/" + name, self.providers[name] is not None) for name in ("detect", "plan", "status")),
                               ("/api/policies", self.providers["policies"] is not None)]:
            endpoints.append({"method": "GET", "path": path, "kind": "read", "available": bool(provider),
                              "provider": {"id": "open-ocean", "version": "0.1.2"},
                              "auth": "provider-session", "runtime_verified": False, "verification_scope": "adapter",
                              "reason": None if provider else "Kein nativer Anbieter konfiguriert."})
        for path in ("/api/governance/policy-registry", "/api/decisions", "/api/governance/effective-policy"):
            available = self.providers["policies"] is not None and path != "/api/governance/effective-policy"
            endpoints.append({"method": "GET", "path": path, "kind": "read", "available": available,
                              "provider": {"id": "policy-registry", "version": next((item.get("version") for item in self.modules if item.get("id") == "policy-registry"), None)} if available else None,
                              "auth": "provider-session", "runtime_verified": False, "verification_scope": "adapter",
                              "reason": None if available else "Kein freigegebener nativer Leseadapter konfiguriert."})
        # A rendered page and a native executable service are different evidence.
        for method, path, kind in [("GET", "/api/tasks", "read"), ("POST", "/api/tasks", "write"),
                                   ("GET", "/api/agents/native/slots", "read"),
                                   ("GET", "/api/agents/native/tasks", "read"),
                                   ("POST", "/api/agents/native/tasks", "action"),
                                   ("POST", "/api/installer/apply", "action")]:
            endpoints.append({"method": method, "path": path, "kind": kind, "available": False,
                              "provider": None, "auth": "provider-session", "runtime_verified": False,
                              "verification_scope": "adapter", "reason": "Kein freigegebener nativer GUI-Adapter vorhanden."})
        pages = []
        for page_id, path in PAGE_ROUTES.items():
            required = ["GET /api/gui/capabilities"] if page_id == "overview" else []
            missing = [] if required else ["native-page-adapter"]
            if not self.gui:
                missing.append("verified-gui-release")
            pages.append({"id": page_id, "path": path, "status": "configured" if not missing else "unavailable",
                          "requires": required, "missing": missing,
                          "todo": [] if not missing else ["Native Seiten- und Widgetadapter mit Laufzeitbeleg ergänzen."]})
        module_sources = self.modules
        module_states = {"policy-registry": {"adapter_registered": True,
                         "available": self.providers["policies"] is not None, "runtime_verified": False,
                         "reason_code": None if self.providers["policies"] else "provider-not-configured"},
                         "native-agents": {"adapter_registered": False, "available": False,
                                           "runtime_verified": False, "reason_code": "adapter-missing"},
                         "tasks": {"adapter_registered": False, "available": False,
                                   "runtime_verified": False, "reason_code": "adapter-missing"}}
        return {"schema": SCHEMA, "system": {"id": "open-ocean", "adapter_version": "1"},
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "gui": {"status": "installed" if self.gui else "unavailable",
                        "source_commit": self.gui.source_commit if self.gui else None,
                        "archive_sha256": self.gui.archive_sha256 if self.gui else None},
                "modules": module_states, "module_sources": module_sources, "pages": pages, "endpoints": endpoints}


def bridge_from_workspace(workspace: Path, *, gui_pins: tuple[str, str] | None = None) -> GuiBridge:
    """Host-supplied context only; requests cannot select paths or commands."""
    gui = None
    if gui_pins:
        try:
            gui = verify_installed_gui(workspace / "modules" / "ellmos-system-gui", *gui_pins)
        except GuiReleaseError:
            pass
    try:
        config = json.loads((workspace / BRIDGE_CONFIG).read_text(encoding="utf-8"))
        if config.get("schema") != "ellmos.open-ocean.gui-bridge.v1":
            return GuiBridge(gui=gui)
    except (OSError, ValueError, AttributeError):
        return GuiBridge(gui=gui)
    try:
        from .ocean_lifecycle import plan_from_paths, status_for_workspace
    except ImportError:
        from ocean_lifecycle import plan_from_paths, status_for_workspace
    keys = {"bundles_root", "system_manifest", "modules_catalog", "skills_registry", "component_bindings", "source_pins"}
    paths = config.get("plan_paths") or {}
    plan = None
    if isinstance(paths, dict) and {"bundles_root", "system_manifest", "modules_catalog", "skills_registry", "source_pins"}.issubset(paths) and set(paths).issubset(keys):
        kwargs = {key: Path(value) for key, value in paths.items() if isinstance(value, str)}
        if len(kwargs) == len(paths) and all(path.is_file() if key != "bundles_root" else path.is_dir() for key, path in kwargs.items()):
            def plan():
                return plan_from_paths(workspace=workspace, **kwargs)
    status = (lambda: status_for_workspace(workspace)) if all((workspace / name).is_file() for name in ("ocean.install.json", "ocean.runtime.json")) else None
    policies, modules = None, []
    component = config.get("policy_component")
    registry = config.get("policy_registry")
    if isinstance(component, dict) and isinstance(registry, str):
        try:
            policies = policy_metadata_reader(component, Path(registry))
            binding = component["detail"]["binding"]
            manifest = json.loads((Path(component["detail"]["local_path"]) / binding["provider_manifest"]).read_text(encoding="utf-8"))
            modules.append({"id": "policy-registry", "version": manifest.get("version"),
                            "source_commit": binding.get("commit"), "verified": True,
                            "verification_scope": "source-pin"})
        except Exception:
            modules.append({"id": "policy-registry", "verified": False})
    return GuiBridge(gui=gui, plan=plan, status=status, policies=policies, modules=modules)


def mount_gui_bridge(app: Any, bridge: GuiBridge, require_auth: Callable, require_admin: Callable) -> None:
    """Mount inside the provider's auth/session middleware, never outside it."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    def capability_route(request):
        require_auth(request)
        return JSONResponse(bridge.capabilities(), headers={"Cache-Control": "no-store"})
    capability_route.__annotations__["request"] = Request
    app.add_api_route("/api/gui/capabilities", capability_route, methods=["GET"])

    def make_route(name, *, kind=None):
        def route(request):
            require_admin(request)
            try:
                kwargs = {}
                if name == "policies":
                    kwargs = {key: value for key, value in request.query_params.items() if key in {"scope", "query", "consumer", "kind"}}
                    if any(len(value) > 512 for value in kwargs.values()):
                        return JSONResponse({"reason": "Suchparameter ist zu lang."}, status_code=422)
                    if kind:
                        kwargs["kind"] = kind
                return JSONResponse(bridge.invoke(name, **kwargs), headers={"Cache-Control": "no-store"})
            except BridgeUnavailable as exc:
                return JSONResponse({"available": False, "reason": str(exc), "runtime_verified": False}, status_code=503,
                                    headers={"Cache-Control": "no-store"})
        route.__annotations__["request"] = Request
        return route
    for name in ("detect", "plan", "status", "policies"):
        path = "/api/policies" if name == "policies" else "/api/installer/" + name
        app.add_api_route(path, make_route(name), methods=["GET"])
    app.add_api_route("/api/governance/policy-registry", make_route("policies"), methods=["GET"])
    app.add_api_route("/api/decisions", make_route("policies", kind="decision"), methods=["GET"])
    app.add_api_route("/api/governance/effective-policy", make_route("unconfigured-effective-policy"), methods=["GET"])
    # Native launch/task adapters have no configured provider in this package.
    # Auth still runs before 503; no action or write can reach an engine.
    for method, path in (("GET", "/api/agents/native/slots"), ("GET", "/api/agents/native/tasks"),
                         ("POST", "/api/agents/native/tasks"), ("GET", "/api/tasks"), ("POST", "/api/tasks")):
        app.add_api_route(path, make_route("unconfigured-native"), methods=[method])
