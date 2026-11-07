# -*- coding: utf-8 -*-
"""Ocean-Modul agent-library & Lifecycle-Contracts:
- 3-Tab Agenten-Bibliothek (`templates`, `prompt_agents`, `chains`) (#2478)
- Gemeinsamer Routinen-, Ready- und Kalender-Lifecycle für Jobs ohne Modell,
  Miniagenten und Automations-Agenten (#2329)
- Gemeinsame Abschluss- und Auswahlbedienung für BACH und Ocean (#2259)
- Desktop-Harness Remote-Attach & Geräteabnahme-Beleg (#2337)
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from tools.persona_routing import (
    CANONICAL_INTERFACE_SYSTEM_SLOTS,
    OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG,
    PRIMARY_INTERFACE_INTEGRATED_ROLES,
    PROVIDER_SOCKET_PROFILES,
)

AGENT_LIBRARY_SCHEMA = "ellmos.agent-library.v1"
FAMILIES = frozenset({"job", "automation_agent", "mini_agent"})
TRIGGERS = frozenset({"manual", "event", "routine", "calendar_once"})
ALLOWED_SCHEMES = frozenset({"http", "https"})


MODULE_MANIFEST = "ellmos-module.v2.json"
MODULE_ROOTS_ENV = "OCEAN_MODULE_ROOTS"  # os.pathsep-getrennte Ordner, deren Unterordner Module sind
EXPECTED_ROLES_PATH = Path(__file__).resolve().parents[1] / "config" / "agent_library_expected_roles.json"


def _installed_manifest_paths(dist_path: list[str] | None = None) -> list[Path]:
    """Manifeste, die installierte Pakete mitliefern (RECORD enthält `ellmos-module.v2.json`)."""
    found: list[Path] = []
    dists = metadata.distributions(path=list(dist_path)) if dist_path is not None else metadata.distributions()
    for dist in dists:
        for f in dist.files or ():
            if f.name == MODULE_MANIFEST:
                located = Path(str(dist.locate_file(f)))
                if located.is_file():
                    found.append(located)
    return found


def discover_module_manifests(
    repos_root: str | Path | None = None,
    *,
    extra_roots: list[str | Path] | None = None,
    include_installed: bool | None = None,
    dist_path: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Alle lesbaren Modulmanifeste: Geschwisterordner, `extra_roots`, `$OCEAN_MODULE_ROOTS`, installierte Pakete.

    Reihenfolge = Vorrang; ein Modul (`id`) zählt einmal, der erste Fund gewinnt. Installierte Pakete werden nur beim
    Standardaufruf (ohne `repos_root`) einbezogen, damit explizite Wurzeln hermetisch bleiben.
    """
    default_root = Path(repos_root) if repos_root is not None else Path(__file__).resolve().parents[2]
    roots = [default_root, *(Path(r) for r in (extra_roots or ()))]
    roots += [Path(r) for r in os.environ.get(MODULE_ROOTS_ENV, "").split(os.pathsep) if r.strip()]
    candidates: list[tuple[Path, str]] = []
    for root in roots:
        if root.is_dir():
            candidates += [(child / MODULE_MANIFEST, "root") for child in sorted(root.iterdir(), key=lambda p: p.name.casefold())]
    if include_installed if include_installed is not None else repos_root is None:
        candidates += [(path, "installed") for path in _installed_manifest_paths(dist_path)]
    manifests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, via in candidates:
        if not path.is_file():
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        module_id = str(manifest.get("id") or path.parent.name)
        if module_id in seen:
            continue
        seen.add(module_id)
        manifests.append({"module_id": module_id, "path": path, "found_via": via, "manifest": manifest})
    return manifests


def discover_module_role_templates(
    repos_root: str | Path | None = None,
    *,
    extra_roots: list[str | Path] | None = None,
    include_installed: bool | None = None,
    dist_path: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan module `ellmos-module.v2.json` manifests (siehe `discover_module_manifests`) and return Agent-Library templates."""
    discovered: list[dict[str, Any]] = []
    for entry in discover_module_manifests(
        repos_root, extra_roots=extra_roots, include_installed=include_installed, dist_path=dist_path
    ):
        module_id = entry["module_id"]
        roles = entry["manifest"].get("roles")
        if not isinstance(roles, list):
            continue
        for role in roles:
            if not isinstance(role, dict) or not role.get("id"):
                continue
            discovered.append(
                {
                    "id": f"{module_id}:{role['id']}",
                    "role_id": str(role["id"]),
                    "module_id": module_id,
                    "label": str(role.get("label") or role["id"]),
                    "source": "module_manifest_role",  # GUI-Vertrag (bibliothek.astro), nicht ändern
                    "origin": "manifest",
                    "found_via": entry["found_via"],
                    "manifest_path": str(entry["path"]),
                    "prompt": role.get("prompt"),
                    "request": role.get("request"),
                    "providers": list(role.get("providers") or ("claude", "codex", "agy", "kimi")),
                    "socket_id": "domain_specialist",
                }
            )
    return discovered


def load_expected_roles(path: str | Path | None = None) -> dict[str, Any]:
    """Soll-Rollenliste (`config/agent_library_expected_roles.json`): `expected[]` und `exceptions[]`."""
    return json.loads(Path(path or EXPECTED_ROLES_PATH).read_text(encoding="utf-8"))


def check_expected_roles(
    templates: list[dict[str, Any]], expected_doc: dict[str, Any], *, found_modules: set[str]
) -> dict[str, Any]:
    """Jede Soll-Rolle ist im Katalog (`covered`), mit Grund ausgenommen (`excepted`), wartet auf ein nicht gefundenes
    Modul (`module_pending`) oder fehlt (`uncovered`). Dazu: Ausnahmen ohne Soll-Rolle (`orphan_exceptions`) und
    Ausnahmen, die der Katalog längst erfüllt (`stale_exceptions`)."""
    ids = {t["id"] for t in templates}
    exceptions = {x["id"] for x in expected_doc.get("exceptions", [])}
    expected_ids = {e["id"] for e in expected_doc.get("expected", [])}
    report: dict[str, list[str]] = {k: [] for k in ("covered", "excepted", "module_pending", "uncovered", "stale_exceptions")}
    for e in expected_doc.get("expected", []):
        if e.get("maps_to") in ids:
            report["covered"].append(e["id"])
            if e["id"] in exceptions:
                report["stale_exceptions"].append(e["id"])
        elif e["id"] in exceptions:
            report["excepted"].append(e["id"])
        elif e.get("module") and e["module"] not in found_modules:
            report["module_pending"].append(e["id"])
        else:
            report["uncovered"].append(e["id"])
    report["orphan_exceptions"] = sorted(exceptions - expected_ids)
    return report


def discover_module_interface_slots(repos_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Scan installed module `ellmos-module.v2.json` manifests for optional `interface_slots[]` (Systemplätze)."""
    root = Path(repos_root) if repos_root is not None else Path(__file__).resolve().parents[2]
    discovered: list[dict[str, Any]] = [dict(slot, source="canonical_core") for slot in CANONICAL_INTERFACE_SYSTEM_SLOTS]
    seen_ids = {slot["id"] for slot in discovered}
    if not root.is_dir():
        return discovered
    for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        manifest_path = child / "ellmos-module.v2.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        module_id = str(manifest.get("id") or child.name)
        interface_slots = manifest.get("interface_slots")
        if not isinstance(interface_slots, list):
            continue
        for slot in interface_slots:
            if not isinstance(slot, dict) or not slot.get("id"):
                continue
            sid = str(slot["id"]).strip()
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
            discovered.append(
                {
                    "id": sid,
                    "module_id": module_id,
                    "label": str(slot.get("label") or sid),
                    "surface": str(slot.get("surface") or "hardware"),
                    "default_integrated_roles": list(
                        slot.get("default_integrated_roles") or PRIMARY_INTERFACE_INTEGRATED_ROLES
                    ),
                    "allow_unassigned": bool(slot.get("allow_unassigned", True)),
                    "supports_fallbacks": bool(slot.get("supports_fallbacks", True)),
                    "preoccupied_on_install": bool(slot.get("preoccupied_on_install", False)),
                    "source": "module_manifest_interface_slot",
                }
            )
    return discovered


def project_agent_library_catalog(
    *,
    templates: list[dict[str, Any]],
    prompt_agents: list[dict[str, Any]],
    chains: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project the 3-tab Agent-Library view (`templates`, `prompt_agents`, `chains`) (#2478)."""
    normalized_chains = []
    for chain in chains:
        kind = chain.get("kind") or ("marblerun" if chain.get("type") == "agent_chain" else "toolchain")
        if kind not in {"marblerun", "toolchain"}:
            kind = "toolchain"
        badge = "Agentenkette (MarbleRun)" if kind == "marblerun" else "Befehlskette (Toolchain)"
        normalized_chains.append({**chain, "kind": kind, "badge": badge})
    return {
        "schema": AGENT_LIBRARY_SCHEMA,
        "tabs": ["templates", "prompt_agents", "chains"],
        "system_restore_in_library": False,
        "system_restore_location": "/settings#system-agents-restore",
        "templates": list(templates),
        "prompt_agents": list(prompt_agents),
        "chains": normalized_chains,
    }


def build_full_agent_library_catalog(
    repos_root: str | Path | None = None,
    *,
    extra_prompt_agents: list[dict[str, Any]] | None = None,
    extra_chains: list[dict[str, Any]] | None = None,
    extra_roots: list[str | Path] | None = None,
    include_installed: bool | None = None,
    dist_path: list[str] | None = None,
) -> dict[str, Any]:
    """Build the populated 3-tab Agent-Library catalog combining BACH Coordinator/Expert roles and module `roles[]`."""
    role_templates: list[dict[str, Any]] = [
        {
            "id": f"ocean-role:{r['id']}",
            "role_id": r["id"],
            "module_id": "open-ocean",
            "label": r["label"],
            "tier": r["tier"],
            "source": "ocean_role_socket_catalog",
            "origin": "builtin",
            "semantic_route": r["semantic_route"],
            "deterministic_route": r["deterministic_route"],
            "socket_id": r["socket_id"],
            "providers": list(PROVIDER_SOCKET_PROFILES[r["socket_id"]]["providers"].keys()),
        }
        for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG
    ]
    manifests = discover_module_manifests(
        repos_root, extra_roots=extra_roots, include_installed=include_installed, dist_path=dist_path
    )
    module_templates = discover_module_role_templates(
        repos_root, extra_roots=extra_roots, include_installed=include_installed, dist_path=dist_path
    )
    default_chains = [
        {"id": "marblerun:doc-keeper-machine", "kind": "marblerun", "label": "Doc-Keeper Machine (3-Cause Audit)"},
        {"id": "marblerun:wishes-come-true-local", "kind": "marblerun", "label": "Wishes-Come-True Local Genie"},
        {"id": "toolchain:daily-hygiene", "kind": "toolchain", "label": "Daily Hygiene & Lock Check"},
    ]
    catalog = project_agent_library_catalog(
        templates=role_templates + module_templates,
        prompt_agents=list(extra_prompt_agents or []),
        chains=list(extra_chains if extra_chains is not None else default_chains),
    )
    try:
        expected_doc = load_expected_roles()
    except OSError:  # repo-only Datei (config/ ist nicht im Paket): Katalog trotzdem liefern
        expected_doc = {"expected": [], "exceptions": []}
    report = check_expected_roles(
        catalog["templates"], expected_doc, found_modules={m["module_id"] for m in manifests}
    )
    exceptions = [dict(x, origin="legacy") for x in expected_doc.get("exceptions", [])]
    catalog["role_exceptions"] = exceptions
    catalog["expected_roles"] = report
    catalog["module_manifests"] = [
        {"module_id": m["module_id"], "path": str(m["path"]), "found_via": m["found_via"],
         "roles": len(m["manifest"].get("roles") or [])}
        for m in manifests
    ]
    # Die GUI liest `counts` statt einer Festzahl (z. B. "19 Modul-Rollen").
    catalog["counts"] = {
        "ocean_roles": len(role_templates),
        "module_roles": len(module_templates),
        "modules": len({t["module_id"] for t in module_templates}),
        "templates": len(catalog["templates"]),
        "exceptions": len(exceptions),
        "expected": len(expected_doc.get("expected", [])),
        "covered": len(report["covered"]),
        "module_pending": len(report["module_pending"]),
        "uncovered": len(report["uncovered"]),
    }
    return catalog


@dataclass
class AutomationLifecycleRegistry:
    """Verwaltet Jobs ohne Modell, Miniagenten und Automations-Agenten mit Fence-Schutz (#2329)."""

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_triggers: dict[str, str] = field(default_factory=dict)

    def register_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        eid = str(payload.get("id") or "").strip()
        family = str(payload.get("family") or "").strip()
        trigger = str(payload.get("trigger") or "routine").strip()
        if not eid:
            raise ValueError("id fehlt")
        if family not in FAMILIES:
            raise ValueError(f"Ungültige Familie: {family}")
        if trigger not in TRIGGERS:
            raise ValueError(f"Ungültige Startart: {trigger}")

        if family == "job" and payload.get("requires_model"):
            raise ValueError("Jobs ohne Modell dürfen kein Sprachmodell anfordern")
        if family == "mini_agent":
            if not payload.get("input_schema") or not payload.get("output_schema"):
                raise ValueError("Miniagenten benötigen festen Ein-/Ausgabevertrag (input_schema/output_schema)")
            if payload.get("allows_open_work") or payload.get("allows_reviews"):
                raise ValueError("Miniagenten erlauben keine offene Agentenarbeit oder Reviews")

        record = {
            "id": eid,
            "title": str(payload.get("title") or eid),
            "family": family,
            "trigger": trigger,
            "timezone": str(payload.get("timezone") or "Europe/Berlin"),
            "state": "available" if payload.get("from_module") and not payload.get("scheduled") else "ready",
            "fence": int(payload.get("fence") or 1),
            "last_start_trigger": None,
            "input_schema": payload.get("input_schema"),
            "output_schema": payload.get("output_schema"),
        }
        self.entries[eid] = record
        return record

    def trigger_start(
        self,
        eid: str,
        *,
        start_trigger: str,
        dedup_key: str,
        tz_now: datetime | None = None,
    ) -> dict[str, Any]:
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        if start_trigger not in TRIGGERS:
            raise ValueError(f"Ungültiger Startanlass: {start_trigger}")
        if self.active_triggers.get(eid) == dedup_key:
            return {**self.entries[eid], "deduplicated": True}

        rec = self.entries[eid]
        if rec["state"] == "available":
            raise RuntimeError("Mitgelieferte Pflegeaufgaben laufen erst nach bestätigter Planung")

        tz = ZoneInfo(rec["timezone"])
        now_local = (tz_now or datetime.now(tz)).astimezone(tz)
        rec["fence"] += 1
        rec["state"] = "running"
        rec["last_start_trigger"] = start_trigger
        rec["started_at_local"] = now_local.isoformat()
        self.active_triggers[eid] = dedup_key
        return {**rec, "deduplicated": False}

    def stop_entry(self, eid: str, *, expected_fence: int) -> dict[str, Any]:
        rec = self.entries[eid]
        if rec["fence"] != expected_fence:
            raise RuntimeError(f"Fence-Konflikt beim Stopp: erwartet {expected_fence}, aktuell {rec['fence']}")
        rec["fence"] += 1
        rec["state"] = "ready"
        self.active_triggers.pop(eid, None)
        return rec


def build_shared_completion_selection_contract(
    *,
    consumer: str,
    gui_version: str,
    host: str,
    device: str,
    provider: str,
    foreign_lease_active: bool = False,
    requires_user_approval: bool = False,
) -> dict[str, Any]:
    """Gemeinsame Integration der Abschluss- und Auswahlbedienung für BACH und Ocean (#2259)."""
    if consumer not in ("bach", "ocean"):
        raise ValueError(f"Unbekannter Consumer: {consumer}")
    return {
        "carrier_product": "ellmos-system-gui",
        "legacy_web_copy_revived": False,
        "consumer": consumer,
        "gui_version": gui_version,
        "identity": {
            "host": host,
            "device": device,
            "provider": provider,
        },
        "guards": {
            "grants_new_tool_permissions": False,
            "bypasses_foreign_leases": False,
            "bypasses_user_approval": False,
            "action_allowed": (not foreign_lease_active) and (not requires_user_approval),
        },
    }


def validate_remote_attach_origin(origin_url: str, allowed_origins: list[str] | set[str]) -> dict[str, Any]:
    """Prüft die exakte Origin-Grenze für das Tauri-Remote-Webview (#2337)."""
    parsed = urlparse(origin_url.strip())
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError(f"Ungültige Origin-URL: {origin_url}")
    normalized = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed_norm = {u.rstrip("/").lower() for u in allowed_origins}
    if normalized not in allowed_norm:
        raise PermissionError(f"Origin nicht freigegeben: {normalized}")
    return {
        "origin": normalized,
        "remote_ipc_enabled": False,
        "spawns_local_processes": False,
        "preserves_device_cookie": True,
    }


def build_desktop_attach_receipt(
    *,
    host: str,
    platform_name: str,
    origin_url: str,
    allowed_origins: list[str],
    capabilities_status: int,
    fence: int,
    bundle_embeds_legacy_astro: bool = False,
) -> dict[str, Any]:
    """Erzeugt den verifizierten Geräteabnahme-Beleg für den Tauri-Desktop-Harness (#2337)."""
    if bundle_embeds_legacy_astro:
        raise ValueError("Desktop-Shell darf keine veraltete Astro-Kopie bündeln")
    if capabilities_status != 200:
        raise RuntimeError(f"Capabilities-Probe fehlgeschlagen: HTTP {capabilities_status}")
    if fence <= 0:
        raise ValueError("Fence muss positiv sein")

    attach = validate_remote_attach_origin(origin_url, allowed_origins)
    payload = {
        "carrier_repo": "ellmos-system-gui",
        "process_supervisor": "open-ocean",
        "host": host,
        "platform": platform_name,
        "origin": attach["origin"],
        "remote_ipc_enabled": False,
        "spawns_local_processes": False,
        "windows_subsystem": "GUI",
        "capabilities_probe_http": capabilities_status,
        "fence": fence,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {**payload, "receipt_sha256": digest}
