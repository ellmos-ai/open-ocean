"""Native, read-only GUI consumer routes. No apply/grant authority lives here."""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

try:
    from .capability_views import ocean_inventory, skill_library
    from .catalog_projection import KINDS as CATALOG_KINDS, observe as observe_catalog, _read_bytes
    from . import governance_bridge as gov
    from .fetch_place import verify_bound_provider
    from .module_binding import bound_module_dir
    from .gui_page_reads import SCHEMA as PAGE_READS_SCHEMA, load as load_page_reads, normalize as page_reads_normalize, pages_status
    from .gui_release import GuiReleaseError, VerifiedGuiRelease, verify_installed_gui
    from .gui_metadata import DEFAULT_BRAND, unverified_backend_origin
except ImportError:  # ocean_runtime.py direct entry point
    from gui_page_reads import SCHEMA as PAGE_READS_SCHEMA, load as load_page_reads, normalize as page_reads_normalize, pages_status
    from capability_views import ocean_inventory, skill_library
    from catalog_projection import KINDS as CATALOG_KINDS, observe as observe_catalog, _read_bytes
    import governance_bridge as gov
    from fetch_place import verify_bound_provider
    from module_binding import bound_module_dir
    from gui_release import GuiReleaseError, VerifiedGuiRelease, verify_installed_gui
    from gui_metadata import DEFAULT_BRAND, unverified_backend_origin

SCHEMA = "ellmos.gui.capabilities.v1"
BRIDGE_CONFIG = "ocean.gui-bridge.json"
PAGE_ROUTES = {
    "overview": "/", "tasks": "/tasks", "life": "/life", "memory": "/memory",
    "domains": "/domains", "artefakte": "/artefakte", "skills": "/skills",
    "software": "/skills/software", "ocean": "/skills/ocean", "plugins": "/skills/plugins", "mcp": "/skills/mcp",
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
        # Handle-bound, link-free, size-limited (the same rule as the catalog adapter).
        return _read_bytes(path, path.parent, 16 * 1024 * 1024)[0]
    except (OSError, ValueError) as exc:
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


def _bound_policy(component: dict[str, Any], registry_path: Path):
    detail = component.get("detail") or {}
    binding = detail.get("binding")
    if not isinstance(binding, dict) or binding.get("catalog_id") != "policy-registry" or not detail.get("local_path"):
        raise BridgeUnavailable("policy-registry benötigt eine exakte Anbieterbindung.")
    source = Path(detail["local_path"])
    verify_bound_provider(source, binding)
    module = _import_bound_policy(source)
    _registry_snapshot(registry_path)
    return source, binding, module


def policy_metadata_reader(component: dict[str, Any], registry_path: Path) -> Callable[[], dict]:
    """Reuse the installed policy-registry API after checking its exact binding.

    Only summary counts and public metadata leave this adapter. Canonical source
    files, rule texts, decision chains and source URIs are never opened here.
    """
    source, binding, module = _bound_policy(component, registry_path)

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


def policy_registry_reader(component: dict[str, Any], registry_path: Path, provider: dict[str, Any]) -> Callable[..., dict]:
    """bach.policy-registry.v1 over the same exactly-bound checkout; identity is re-proven on every read."""
    source, binding, module = _bound_policy(component, registry_path)

    def read(*, scope: str | None = None, consumer: str | None = None, query: str = "",
             kind: str | None = None, effective: bool = False) -> dict:
        try:
            verify_bound_provider(source, binding)
        except Exception as exc:
            raise gov.GovernanceUnavailable("policy_provider_provenance_mismatch") from exc
        return gov.observe(registry_factory=lambda: module.PolicyRegistry(registry_path), registry_path=registry_path,
                           provider=provider, scope=scope, consumer=consumer, query=query, kind=kind,
                           effective=effective)
    return read


USECASES_FILE = "usecases.json"
USECASES_LIMIT = 4 * 1024 * 1024
USECASE_MAX_ROWS = 10_000
USECASE_TEXT_LIMITS = {"title": 1_000, "description": 100_000, "last_tested": 64, "module": 200, "covering_skill": 200,
                       "coverage_status": 64}
USECASE_META_TEXT_LIMIT = 256
USECASE_MAX_ID = 2**63 - 1  # SQLite INTEGER PRIMARY KEY
USECASE_MAX_ID_DIGITS = 19
# bach.db `usecases` columns, in table order: BACH's GET /api/usecases returns whole rows (SELECT *).
USECASE_COLUMNS = ("id", "title", "description", "workflow_path", "workflow_name", "test_input", "expected_output",
                   "last_tested", "test_result", "test_score", "tuev_valid_until", "created_by", "created_at", "updated_at")


class UsecasesUnavailable(Exception):
    """Stable machine-readable reason (never a path or an exception text) for the 503 body."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _optional_text(value: Any) -> bool:
    return value is None or isinstance(value, str)


def usecases_reader(component: dict[str, Any], modules_root: Path) -> Callable[..., dict]:
    """Serve BACH's ``GET /api/usecases`` contract from the ellmos-tests module bound in the composition.

    The file is ``usecases.json`` of that module (generator tools/usecases_sync.py, exported from bach.db). It carries
    id/title/description/test_score/last_tested natively; ``test_result`` is derived from ``test_score`` with BACH's own
    rule (>=75 pass, >0 fail, else pending) and named under ``source.derived``; the other bach.db columns stay null
    (not invented); module/covering_skill/coverage_status ride along as additive fields the GUI ignores.
    """
    try:
        root = bound_module_dir(component, "ellmos-tests", modules_root)
    except ValueError:
        raise BridgeUnavailable("Die ellmos-tests-Bindung der Komposition ist ungültig.") from None

    def read(usecase_id: int | None = None) -> dict:
        try:
            raw, _ = _read_bytes(root / USECASES_FILE, root, USECASES_LIMIT)
        except FileNotFoundError:
            raise UsecasesUnavailable("source-missing") from None
        except ValueError:
            raise UsecasesUnavailable("source-too-large") from None
        except OSError:
            raise UsecasesUnavailable("source-unreadable") from None
        try:
            document = json.loads(raw.decode("utf-8-sig"))
        except (ValueError, RecursionError):  # JSONDecodeError, UnicodeDecodeError, absurd nesting or int size
            raise UsecasesUnavailable("source-invalid") from None
        meta = document.get("_meta") if isinstance(document, dict) else None
        items = document.get("usecases") if isinstance(document, dict) else None
        if (not isinstance(items, list) or len(items) > USECASE_MAX_ROWS
                or not (meta is None or isinstance(meta, dict))
                or any(isinstance(value, str) and len(value) > USECASE_META_TEXT_LIMIT
                       for value in (meta or {}).values())):
            raise UsecasesUnavailable("source-invalid")
        rows, seen = [], set()
        for item in items:
            if (not isinstance(item, dict) or isinstance(item.get("id"), bool) or not isinstance(item.get("id"), int)
                    or not 0 < item["id"] <= USECASE_MAX_ID or item["id"] in seen
                    or not isinstance(item.get("title"), str) or not item["title"].strip()
                    or not all(_optional_text(item.get(key)) for key in
                               ("description", "last_tested", "module", "covering_skill", "coverage_status"))
                    or any(isinstance(item.get(key), str) and len(item[key]) > limit
                           for key, limit in USECASE_TEXT_LIMITS.items())):
                raise UsecasesUnavailable("source-invalid")
            score = item.get("test_score")
            if score is not None and (isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100):
                raise UsecasesUnavailable("source-invalid")
            seen.add(item["id"])
            row = dict.fromkeys(USECASE_COLUMNS)
            row.update({key: item.get(key) for key in ("id", "title", "description", "last_tested", "test_score")})
            if score is not None:
                row["test_result"] = "pass" if score >= 75 else ("fail" if score > 0 else "pending")
            row.update({key: item.get(key) for key in ("module", "covering_skill", "coverage_status")})
            rows.append(row)
        if usecase_id is not None:  # BACH GET /api/usecases/{id}: the row, or HTTP 200 success:false "Nicht gefunden"
            found = next((row for row in rows if row["id"] == usecase_id), None)
            return {"success": True, "usecase": found} if found else {"success": False, "error": "Nicht gefunden"}
        rows.sort(key=lambda row: (row["title"].encode("utf-8"), row["id"]))  # SQLite ORDER BY title (BINARY)
        passed = sum(1 for row in rows if row["test_result"] == "pass")
        failed = sum(1 for row in rows if row["test_result"] == "fail")
        meta = meta or {}
        generated, source_db = meta.get("generated_at"), meta.get("source_db")
        return {"success": True, "usecases": rows,
                "stats": {"total": len(rows), "pass": passed, "fail": failed, "pending": len(rows) - passed - failed},
                "source": {"id": "ellmos-tests", "file": USECASES_FILE, "read_only": True,
                           "generated_at": generated if isinstance(generated, str) else None,
                           "source_db": source_db if isinstance(source_db, str) else None,
                           "derived": ["test_result", "stats"]}}
    return read


class GuiBridge:
    def __init__(self, *, gui: VerifiedGuiRelease | None = None,
                 plan: Callable[[], dict] | None = None, status: Callable[[], dict] | None = None,
                 policies: Callable[[], dict] | None = None, modules: list[dict] | None = None,
                 catalog: Callable[..., dict] | None = None, ocean: Callable[[], dict] | None = None,
                 skills: Callable[[], dict] | None = None, registry: Callable[..., dict] | None = None,
                 locks: Callable[[], dict] | None = None, usecases: Callable[[], dict] | None = None):
        self.gui = gui
        self.providers = {"detect": self.detect, "plan": plan, "status": status, "policies": policies, "catalog": catalog,
                          "ocean": ocean, "skills": skills, "registry": registry, "locks": locks, "usecases": usecases}
        self.modules = modules or []

    def detect(self) -> dict:
        return {"schema": "ellmos.open-ocean.installer-detect.v1", "read_only": True,
                "provider": {"id": "open-ocean", "version": "0.1.2"},
                "native": {name: provider is not None for name, provider in self.providers.items() if name not in {"detect", "registry", "locks", "usecases"}},
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
                               ("/api/gui/brand", True),
                               ("/api/gui/backend-origin", True),
                               *(("/api/installer/" + name, self.providers[name] is not None) for name in ("detect", "plan", "status")),
                               ("/api/policies", self.providers["policies"] is not None),
                               ("/api/capabilities/catalog", self.providers["catalog"] is not None)]:
            endpoints.append({"method": "GET", "path": path, "kind": "read", "available": bool(provider),
                              "provider": {"id": "open-ocean", "version": "0.1.2"},
                              "auth": "provider-session", "runtime_verified": False, "verification_scope": "adapter",
                              "reason": None if provider else "Kein nativer Anbieter konfiguriert."})
        usecases_reason = "source-not-in-composition"
        if self.providers["usecases"] is not None:
            # ponytail: re-reads and re-validates usecases.json on every capabilities call (at most USECASES_LIMIT = 4 MiB
            # and USECASE_MAX_ROWS = 10k rows); add an mtime/size keyed cache in usecases_reader if the GUI polls this often.
            try:
                self.providers["usecases"]()
                usecases_reason = None
            except UsecasesUnavailable as exc:
                usecases_reason = exc.reason
            except Exception:  # noqa: BLE001 - a stable code, never exception text
                usecases_reason = "source-unreadable"
        lock_state = self.providers["locks"]() if self.providers["locks"] is not None else None
        lock_ok = lock_state is not None and lock_state.get("availability") == "available"
        lock_reason = "lock_cache_missing" if lock_state is None else (lock_state.get("error") or "lock_cache_invalid")
        policy_provider = {"id": "policy-registry", "version": next((item.get("version") for item in self.modules if item.get("id") == "policy-registry"), None)}
        for path, available, reason, provider in [
                ("/api/decisions", self.providers["policies"] is not None, "Kein freigegebener nativer Leseadapter konfiguriert.", policy_provider),
                *((f"/api/governance/{name}", self.providers["registry"] is not None,
                   "Kein freigegebener nativer Leseadapter konfiguriert.", policy_provider)
                  for name in ("policy-registry", "decisions", "policies", "effective-policy")),
                ("/api/governance/status", lock_ok or self.providers["registry"] is not None,
                 "Weder Lock-Cache noch Policy-Registry gebunden.", {"id": "open-ocean", "version": "0.1.2"}),
                ("/api/governance/locks", lock_ok, lock_reason, {"id": "lock-cache", "version": None}),
                ("/api/governance/audit", False, "task_history_unavailable", None),
                ("/api/usecases", usecases_reason is None, usecases_reason, {"id": "ellmos-tests", "version": None})]:
            endpoints.append({"method": "GET", "path": path, "kind": "read", "available": available,
                              "provider": provider if available else None,
                              "auth": "provider-session", "runtime_verified": False, "verification_scope": "adapter",
                              "reason": None if available else reason})
        for path, provider in (("/api/capabilities/ocean", self.providers["ocean"] is not None),
                               ("/api/capabilities/skills/library", self.providers["skills"] is not None)):
            endpoints.append({"method": "GET", "path": path, "kind": "read", "available": provider,
                              "provider": {"id": "open-ocean", "version": "0.1.2"} if provider else None,
                              "auth": "provider-session", "runtime_verified": False, "verification_scope": "adapter",
                              "reason": None if provider else "Kein nativer Anbieter konfiguriert."})
        for method, path, kind, reason in [
                ("GET", "/api/capabilities/software", "read", "source-not-in-composition"),
                ("GET", "/api/capabilities/skills/{id}/source", "read", "no-adapter"),
                ("GET", "/api/capabilities/skills/{id}/history", "read", "no-adapter"),
                ("GET", "/api/capabilities/skills/{id}/history/{revision}", "read", "no-adapter"),
                ("PUT", "/api/capabilities/skills/{id}/source", "write", "no-write-authority"),
                ("GET", "/api/skills-board/hierarchy", "read", "no-adapter"),
                ("PUT", "/api/skills-board/hierarchy", "write", "no-write-authority")]:
            endpoints.append({"method": method, "path": path, "kind": kind, "available": False, "provider": None,
                              "auth": "provider-session", "runtime_verified": False,
                              "verification_scope": "adapter", "reason": reason})
        # A rendered page and a native executable service are different evidence.
        for method, path, kind in [("GET", "/api/tasks", "read"), ("POST", "/api/tasks", "write"),
                                   ("GET", "/api/task-assignees", "read"),
                                   ("GET", "/api/agents/native/slots", "read"),
                                   ("GET", "/api/agents/native/tasks", "read"),
                                   ("POST", "/api/agents/native/tasks", "action"),
                                   ("POST", "/api/installer/apply", "action")]:
            endpoints.append({"method": method, "path": path, "kind": kind, "available": False,
                              "provider": None, "auth": "provider-session", "runtime_verified": False,
                              "verification_scope": "adapter", "reason": "Kein freigegebener nativer GUI-Adapter vorhanden."})
        # The page-to-endpoint table is the GUI's own manifest from the verified release, never a hand table here.
        page_reads = load_page_reads(self.gui)
        served = {f"{e['method']} {page_reads_normalize(e['path'])}": e["available"] for e in endpoints}
        pages = pages_status(page_reads, PAGE_ROUTES, served)
        module_sources = self.modules
        module_states = {"policy-registry": {"adapter_registered": True,
                         "available": self.providers["policies"] is not None, "runtime_verified": False,
                         "reason_code": None if self.providers["policies"] else "provider-not-configured"},
                         "native-agents": {"adapter_registered": False, "available": False,
                                           "runtime_verified": False, "reason_code": "adapter-missing"},
                         "tasks": {"adapter_registered": False, "available": False,
                                   "runtime_verified": False, "reason_code": "adapter-missing"}}
        installed = bool(self.gui and self.gui.installed_verified)
        module_states["ellmos-system-gui"] = {"adapter_registered": True,
            "available": self.gui is not None, "runtime_verified": False,
            "verification_scope": "adapter", "reason_code": None if self.gui else "verified-release-unavailable"}
        return {"schema": SCHEMA, "schema_version": 1,
                "system": {"id": "open-ocean", "adapter_version": "1"},
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "kit": {"revision": self.gui.source_commit if self.gui else None,
                        "version": None, "archive_sha256": self.gui.archive_sha256 if self.gui else None,
                        "verified": self.gui is not None, "installed": installed, "served": False},
                "brand": dict(DEFAULT_BRAND),
                "gui": {"status": "installed" if installed else "unavailable",
                        "source_commit": self.gui.source_commit if self.gui else None,
                        "archive_sha256": self.gui.archive_sha256 if self.gui else None},
                "page_reads": {"state": page_reads["state"], "schema": PAGE_READS_SCHEMA, "sha256": page_reads["sha256"],
                               "reasons": page_reads["reasons"]},
                "modules": module_states, "module_sources": module_sources, "pages": pages, "endpoints": endpoints}


def bridge_from_workspace(workspace: Path, *, gui_pins: tuple[str, str] | None = None) -> GuiBridge:
    """Host-supplied context only; requests cannot select paths or commands."""
    bridge = _bridge_core(workspace, gui_pins=gui_pins)
    # Workspace-only read providers: independent of the optional plan/policy bridge configuration.
    if (workspace / "ocean.install.json").is_file():
        bridge.providers["catalog"] = lambda **kwargs: observe_catalog(workspace=workspace, **kwargs)
        bridge.providers["ocean"] = lambda: ocean_inventory(workspace=workspace)
    if (workspace / "skills").is_dir():
        bridge.providers["skills"] = lambda: skill_library(workspace=workspace)
    return bridge


def _bridge_core(workspace: Path, *, gui_pins: tuple[str, str] | None = None) -> GuiBridge:
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
    policies, modules, registry_reader, locks = None, [], None, None
    lock_cache = config.get("lock_cache")
    if isinstance(lock_cache, str) and lock_cache.strip():
        cache_path = Path(lock_cache)
        locks = lambda: gov.lock_cache_snapshot(cache_path)  # noqa: E731 - bound once, read per request
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
            registry_reader = policy_registry_reader(component, Path(registry), {
                "id": "policy-registry", "version": manifest.get("version"), "source_commit": binding.get("commit"),
                "repository": gov.REPOSITORY, "verified": True})
        except Exception:
            modules.append({"id": "policy-registry", "verified": False})
    usecases = None
    uc_component = config.get("usecases_component")
    if isinstance(uc_component, dict):
        try:
            usecases = usecases_reader(uc_component, workspace / "modules")
        except BridgeUnavailable:
            usecases = None
    return GuiBridge(gui=gui, plan=plan, status=status, policies=policies, modules=modules,
                     registry=registry_reader, locks=locks, usecases=usecases)


def mount_gui_bridge(app: Any, bridge: GuiBridge, require_auth: Callable, require_admin: Callable) -> None:
    """Mount inside the provider's auth/session middleware, never outside it."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    def capability_route(request):
        require_auth(request)
        return JSONResponse(bridge.capabilities(), headers={"Cache-Control": "no-store"})
    capability_route.__annotations__["request"] = Request
    app.add_api_route("/api/gui/capabilities", capability_route, methods=["GET"])

    def add_guarded(path, endpoint, guard=None):
        """Authentication runs first for EVERY method (also unlisted ones such as PROPFIND) and for the trailing-slash
        path, so an unauthenticated caller never sees a 405 or a slash redirect; only authenticated non-GET gets 405.
        A raw ASGI route has no method list, so the router cannot answer 405 before authentication."""
        from starlette.concurrency import run_in_threadpool
        from starlette.routing import Route

        def handle(request):
            require_auth(request)
            if guard is not None and request.method == "GET":
                guard(request)
            if request.method != "GET":
                return JSONResponse({"detail": "method_not_allowed"}, status_code=405,
                                    headers={"Allow": "GET", "Cache-Control": "no-store"})
            return endpoint(request)

        class Guarded:
            async def __call__(self, scope, receive, send):
                response = await run_in_threadpool(handle, Request(scope, receive))
                await response(scope, receive, send)
        for variant in (path, path + "/"):
            app.router.routes.append(Route(variant, endpoint=Guarded(), methods=None))

    def brand_route(request):
        return JSONResponse(dict(DEFAULT_BRAND), headers={"Cache-Control": "no-store"})

    def backend_origin_route(request):
        return JSONResponse(unverified_backend_origin(), headers={"Cache-Control": "no-store"})

    # These are provider-session routes, not the public standalone shell.
    # A successful metadata response does not grant backend/claim authority.
    add_guarded("/api/gui/brand", brand_route)
    add_guarded("/api/gui/backend-origin", backend_origin_route)

    def catalog_route(request):
        # Same validation outcome as BACH's FastAPI Query constraints: 422 with a detail list.
        kind = request.query_params.get("kind")
        host = request.query_params.get("host")
        problems = []
        if kind is not None and kind not in CATALOG_KINDS:
            problems.append({"loc": ["query", "kind"], "msg": "String should match pattern", "type": "string_pattern_mismatch"})
        if host is not None and not 1 <= len(host) <= 80:
            problems.append({"loc": ["query", "host"], "msg": "String should have between 1 and 80 characters",
                             "type": "string_too_short" if not host else "string_too_long"})
        if problems:
            return JSONResponse({"detail": problems}, status_code=422, headers={"Cache-Control": "no-store"})
        if bridge.providers["catalog"] is None:
            return JSONResponse({"available": False, "reason": "Kein nativer Anbieter konfiguriert.",
                                 "runtime_verified": False}, status_code=503, headers={"Cache-Control": "no-store"})
        return JSONResponse(bridge.providers["catalog"](kind=kind, host=host), headers={"Cache-Control": "no-store"})
    add_guarded("/api/capabilities/catalog", catalog_route)

    def inventory_route(name, unreadable):
        def route(request):
            provider = bridge.providers[name]
            if provider is None:
                return JSONResponse({"available": False, "reason": "source-not-configured", "runtime_verified": False},
                                    status_code=503, headers={"Cache-Control": "no-store"})
            try:
                return JSONResponse(provider(), headers={"Cache-Control": "no-store"})
            except (OSError, ValueError, RuntimeError):
                return JSONResponse({"detail": unreadable}, status_code=503, headers={"Cache-Control": "no-store"})
        return route
    add_guarded("/api/capabilities/ocean", inventory_route("ocean", "Ocean-Quellen nicht lesbar"))
    add_guarded("/api/capabilities/skills/library", inventory_route("skills", "Aktuelle Skill-Bibliothek nicht lesbar"))

    def software_route(request):
        # The software register (.SOFTWARE/releases.json) is not part of the OCEAN composition: no substitute data.
        return JSONResponse({"available": False, "reason": "source-not-in-composition"},
                            status_code=503, headers={"Cache-Control": "no-store"})
    add_guarded("/api/capabilities/software", software_route)

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
    app.add_api_route("/api/decisions", make_route("policies", kind="decision"), methods=["GET"])
    _mount_governance(app, bridge, add_guarded, require_admin, JSONResponse)
    # Native launch/task adapters have no configured provider in this package.
    # Auth still runs before 503; no action or write can reach an engine.
    for method, path in (("GET", "/api/agents/native/slots"), ("GET", "/api/agents/native/tasks"),
                         ("POST", "/api/agents/native/tasks"), ("GET", "/api/tasks"), ("POST", "/api/tasks")):
        app.add_api_route(path, make_route("unconfigured-native"), methods=[method])


def _mount_governance(app: Any, bridge: GuiBridge, add_guarded: Callable, require_admin: Callable, json_response: Any) -> None:
    """GET-only governance reads in BACH's shapes. Auth runs first (add_guarded); nothing here can write."""
    headers = {"Cache-Control": "no-store"}
    kinds = {"policy", "rule", "decision", "evidence", "decision-candidate"}

    def unavailable(code: str, status: int = 503):
        return json_response({"detail": code}, status_code=status, headers=headers)

    def registry_call(**kwargs):
        reader = bridge.providers["registry"]
        if reader is None:
            raise gov.GovernanceUnavailable("policy_provider_not_configured")
        return reader(**kwargs)

    def registry_route(view=None, *, effective=False):
        def route(request):
            params = request.query_params
            problems = []
            for key, limit in (("scope", 256), ("consumer", 256), ("query", 512)):
                if len(params.get(key, "")) > limit:
                    problems.append({"loc": ["query", key], "msg": "String should have at most %d characters" % limit,
                                     "type": "string_too_long"})
            if effective and not params.get("scope"):
                problems.append({"loc": ["query", "scope"], "msg": "String should have at least 1 character",
                                 "type": "string_too_short"})
            if not effective and view is None and params.get("kind") is not None and params["kind"] not in kinds:
                problems.append({"loc": ["query", "kind"], "msg": "String should match pattern", "type": "string_pattern_mismatch"})
            if problems:
                return json_response({"detail": problems}, status_code=422, headers=headers)
            kwargs = {"scope": params.get("scope"), "consumer": params.get("consumer"), "query": params.get("query", "")}
            if view is None:
                kwargs["kind"] = params.get("kind")
            elif view is gov.decisions_view:
                kwargs["kind"] = "decision"
            try:
                result = registry_call(**kwargs, **({"effective": True} if effective else {}))
            except gov.GovernanceUnavailable as exc:
                return unavailable(str(exc))
            except gov.GovernanceChanged as exc:
                return unavailable(str(exc), 409)
            return json_response(view(result) if view else result, headers=headers)
        return route
    add_guarded("/api/governance/policy-registry", registry_route(), require_admin)
    add_guarded("/api/governance/decisions", registry_route(gov.decisions_view), require_admin)
    add_guarded("/api/governance/policies", registry_route(gov.policies_view), require_admin)
    add_guarded("/api/governance/effective-policy", registry_route(effective=True), require_admin)

    def lock_snapshot():
        provider = bridge.providers["locks"]
        return provider() if provider else gov.lock_cache_snapshot(None)

    def locks_route(request):
        return json_response(gov.locks_view(lock_snapshot()), headers=headers)
    add_guarded("/api/governance/locks", locks_route)

    def status_route(request):
        return json_response(gov.status_view(lock_snapshot(), bridge.providers["registry"]), headers=headers)
    add_guarded("/api/governance/status", status_route)

    def audit_route(request):
        raw = request.query_params.get("limit", "50")
        if not raw.isdigit() or not 1 <= int(raw) <= 100:
            return json_response({"detail": [{"loc": ["query", "limit"], "msg": "Input should be between 1 and 100",
                                              "type": "int_parsing"}]}, status_code=422, headers=headers)
        # task_history belongs to task-master, not to this composition; dsgvo_audit_log has other semantics.
        return json_response(gov.AUDIT_UNAVAILABLE, headers=headers)
    add_guarded("/api/governance/audit", audit_route)

    def usecases_route(request):
        provider = bridge.providers["usecases"]
        reason = "source-not-in-composition"
        usecase_id = None
        if "usecase_id" in request.path_params:
            # FastAPI's `usecase_id: int` path parameter: anything else is a 422 with a detail list.
            raw = request.path_params["usecase_id"]
            if not re.fullmatch(r"[+-]?\d{1,%d}" % USECASE_MAX_ID_DIGITS, raw):
                return json_response({"detail": [{"type": "int_parsing", "loc": ["path", "usecase_id"],
                                                   "msg": "Input should be a valid integer, unable to parse string as an integer",
                                                   "input": raw}]}, status_code=422, headers=headers)
            usecase_id = int(raw)
        if provider is not None:
            try:
                return json_response(provider() if usecase_id is None else provider(usecase_id), headers=headers)
            except UsecasesUnavailable as exc:
                reason = exc.reason
            except Exception:  # noqa: BLE001 - the body carries a stable code, never exception text
                reason = "source-unreadable"
        return json_response({"available": False, "reason": reason}, status_code=503, headers=headers)
    add_guarded("/api/usecases", usecases_route)
    add_guarded("/api/usecases/{usecase_id}", usecases_route)
