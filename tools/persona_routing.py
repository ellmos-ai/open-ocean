# -*- coding: utf-8 -*-
"""Ocean-Modul persona-routing: Manifest-Validierung v2 (`roles[]` & `maintenance[]`),
Rollen-Routing-Katalog mit Provider-Sockeln und Modul-Delivery-Lebenszyklus (#2447, #2448, #2452).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PERSONA_ROUTING_SCHEMA = "ellmos.persona-routing.v2"
ROLE_SOCKET_CATALOG_SCHEMA = "ellmos.role-socket-catalog.v1"
INTERVAL_REF_RE = re.compile(r"^(config|routine|policy):[A-Za-z0-9._/-]+$")

VALID_MAINTENANCE_CLASSES = frozenset({"job", "agent-recommended", "agent-required"})
VALID_DIFFICULTIES = frozenset({"low", "medium", "high"})
VALID_ACCESS_TYPES = frozenset({"api", "cli", "browser", "local"})
ORIGIN_REMOVED_BADGE = "Herkunft entfernt"

CLASS_UI_META: dict[str, dict[str, Any]] = {
    "job": {
        "badge": "Reiner Skript-Job",
        "execution_options": ["job"],
        "default_execution_mode": "job",
        "description": "Läuft deterministisch ohne Sprachmodell.",
    },
    "agent-recommended": {
        "badge": "Agent empfohlen",
        "execution_options": ["job", "agent"],
        "default_execution_mode": "agent",
        "description": "Kann als einfacher Job oder mit Agenten-Urteilskraft geplant werden.",
    },
    "agent-required": {
        "badge": "Agent erforderlich",
        "execution_options": ["agent"],
        "default_execution_mode": "agent",
        "description": "Setzt zwingend einen zugewiesenen Agenten mit Sprachmodell voraus.",
    },
}

PROVIDER_SOCKET_PROFILES: dict[str, dict[str, Any]] = {
    "reasoning_coordinator": {
        "socket_id": "reasoning_coordinator",
        "description": "High-reasoning coordinator socket for Umbrella/Boss routing and multi-step orchestration.",
        "providers": {
            "claude": "claude-opus-4-6",
            "codex": "gpt-5.4",
            "agy": "gemini-3.1-pro",
            "kimi": "kimi-k2.5",
            "ollama": "qwen3.5:35b-a3b",
            "openrouter": "anthropic/claude-opus-4-6",
        },
    },
    "domain_specialist": {
        "socket_id": "domain_specialist",
        "description": "Balanced specialist socket for domain experts, audits, and structured report generation.",
        "providers": {
            "claude": "claude-sonnet-4-6",
            "codex": "gpt-5.4-mini",
            "agy": "gemini-3-flash",
            "kimi": "kimi-k2.5",
            "ollama": "qwen3.5:35b-a3b",
            "openrouter": "anthropic/claude-sonnet-4-6",
        },
    },
    "fast_worker": {
        "socket_id": "fast_worker",
        "description": "Low-latency execution socket for atomic worker tasks, ticket triage, and hygiene scans.",
        "providers": {
            "claude": "claude-haiku-4-5",
            "codex": "gpt-5.4-mini",
            "agy": "gemini-3-flash-lite",
            "kimi": "kimi-k2.5",
            "ollama": "qwen2.5-coder:14b",
            "openrouter": "google/gemini-2.5-flash",
        },
    },
}

OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "ati",
        "label": "ATI (Software-Entwicklung & Tooling)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "projekt-pipeline-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='dev')",
        "socket_id": "reasoning_coordinator",
        "experts": ("entwickler-agent", "system-architekt", "devops-experte"),
    },
    {
        "id": "bueroassistent",
        "label": "Büroassistent (Steuern, Verwaltung & Dokumente)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "office-administration-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='office')",
        "socket_id": "reasoning_coordinator",
        "experts": ("steuer-agent", "foerderplaner", "bewerbungsexperte", "rechtsberater"),
    },
    {
        "id": "finanz-assistent",
        "label": "Finanz-Assistent (Banking, Budget & Versicherungen)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "finance-insurance-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='finance')",
        "socket_id": "reasoning_coordinator",
        "experts": ("finanz-experte", "versicherungs-experte", "immobilien-experte"),
    },
    {
        "id": "gesundheitsassistent",
        "label": "Gesundheitsassistent (Medizin, Labor & Prävention)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "therapie-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='health_therapy')",
        "socket_id": "reasoning_coordinator",
        "experts": ("gesundheitsverwalter", "psychologischer-berater"),
    },
    {
        "id": "persoenlicher-assistent",
        "label": "Persönlicher Assistent (Alltag, Termine & Kontakte)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "personal-life-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='personal')",
        "socket_id": "reasoning_coordinator",
        "experts": ("reise-experte", "haushalts-experte", "kommunikations-experte"),
    },
    {
        "id": "produktivitaet",
        "label": "Produktivität (Selbstmanagement & Ziele)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "selbstmanagement",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='productivity')",
        "socket_id": "reasoning_coordinator",
        "experts": ("projekt-experte", "qualitaets-experte", "dokumentations-experte", "forschungs-experte"),
    },
    {
        "id": "steuer-agent",
        "label": "Steuer-Experte (Belege & ELSTER)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "office-administration-umbrella -> steuer-agent",
        "deterministic_route": "controlcenter_switch_profile(profile='office-tax')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "foerderplaner",
        "label": "Förderplaner (ICF & Teilhabeplanung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> foerderplaner",
        "deterministic_route": "controlcenter_switch_profile(profile='therapy-icf')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "bewerbungsexperte",
        "label": "Bewerbungsexperte (CV, Matching & Anschreiben)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "office-administration-umbrella -> bewerbungsexperte",
        "deterministic_route": "controlcenter_find_skill(query='bewerbungsexperte')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "gesundheitsverwalter",
        "label": "Gesundheitsverwalter (Befunde & Medikation)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> gesundheitsverwalter",
        "deterministic_route": "controlcenter_switch_profile(profile='health-records')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "psychologischer-berater",
        "label": "Psychologischer Berater (Stabilisierung & Gesprächsführung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> counseling-basics",
        "deterministic_route": "controlcenter_find_skill(query='therapie-umbrella')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "forschungs-experte",
        "label": "Forschungs-Experte (Literatur, ArXiv & Claim-Mode)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "research-umbrella -> claim-mode",
        "deterministic_route": "controlcenter_find_skill(query='claim-mode')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "dokumentations-experte",
        "label": "Dokumentations-Experte (Doc-Keeper & 3-Ursachen-Prüfung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "docs-analysis -> doc-keeper",
        "deterministic_route": "controlcenter_find_skill(query='docs-analysis')",
        "socket_id": "domain_specialist",
    },
)


def validate_persona_routing_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate `roles[]` and `maintenance[]` blocks in an ellmos.module.v2 manifest (#2447, #2448, #2452)."""
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "problems": ["manifest must be a dict"]}

    roles = manifest.get("roles", [])
    if not isinstance(roles, list):
        problems.append("roles must be a list")
        roles = []
    seen_roles: set[str] = set()
    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            problems.append(f"roles[{idx}] must be a dict")
            continue
        role_id = role.get("id")
        if not isinstance(role_id, str) or not role_id.strip():
            problems.append(f"roles[{idx}].id missing")
        elif role_id in seen_roles:
            problems.append(f"duplicate role id: {role_id}")
        else:
            seen_roles.add(role_id)

        if "prompt" in role or "label" in role or "request" in role or "modes" in role:
            if not isinstance(role.get("label"), str) or not role["label"].strip():
                problems.append(f"roles[{idx}].label must be a non-empty string")
            if not isinstance(role.get("prompt"), str) or not role["prompt"].strip():
                problems.append(f"roles[{idx}].prompt must be a non-empty relative path")
            if not isinstance(role.get("request"), str) or not role["request"].strip():
                problems.append(f"roles[{idx}].request must be a non-empty string")
            if not isinstance(role.get("modes"), list):
                problems.append(f"roles[{idx}].modes must be a list")
        else:
            kind = role.get("kind")
            if kind not in {"boss", "expert", "worker", "reviewer"}:
                problems.append(f"roles[{idx}].kind must be boss|expert|worker|reviewer")
            caps = role.get("capabilities")
            if not isinstance(caps, list) or not caps or any(not isinstance(c, str) for c in caps):
                problems.append(f"roles[{idx}].capabilities must be a non-empty string list")

    maintenance = manifest.get("maintenance", [])
    if not isinstance(maintenance, list):
        problems.append("maintenance must be a list")
        maintenance = []
    for idx, item in enumerate(maintenance):
        if not isinstance(item, dict):
            problems.append(f"maintenance[{idx}] must be a dict")
            continue
        routine_id = item.get("id")
        interval_ref = item.get("interval_ref")
        if not isinstance(routine_id, str) or not routine_id.strip():
            problems.append(f"maintenance[{idx}].id missing")
        if not isinstance(interval_ref, str) or INTERVAL_REF_RE.fullmatch(interval_ref) is None:
            problems.append(f"maintenance[{idx}].interval_ref must match config|routine|policy:<name>")
        if not isinstance(item.get("entrypoint"), str) or not item["entrypoint"].strip():
            problems.append(f"maintenance[{idx}].entrypoint missing")

    return {
        "schema": PERSONA_ROUTING_SCHEMA,
        "valid": len(problems) == 0,
        "role_count": len(roles),
        "maintenance_count": len(maintenance),
        "problems": problems,
    }


def get_ocean_role_routing_catalog() -> dict[str, Any]:
    """Return the canonical BACH-to-Ocean Coordinator & Expert role catalog with flexible provider sockets."""
    coordinators = [r for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG if r["tier"] == "coordinator"]
    experts = [r for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG if r["tier"] == "expert"]
    return {
        "schema": ROLE_SOCKET_CATALOG_SCHEMA,
        "routing_modes": ("semantic_umbrella_and_persona", "deterministic_controlcenter_mcp"),
        "provider_sockets": PROVIDER_SOCKET_PROFILES,
        "coordinators": coordinators,
        "experts": experts,
        "total_roles": len(OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG),
    }


def validate_module_delivery_manifest(manifest: dict[str, Any]) -> list[str]:
    """Prüft roles[] und maintenance[] in einem ellmos.module.v2-Manifest (#2447, #2448)."""
    errors: list[str] = []
    module_id = str(manifest.get("id") or "").strip()
    if not module_id:
        errors.append("module.id fehlt")

    roles = manifest.get("roles", [])
    if not isinstance(roles, list):
        errors.append("roles muss eine Liste sein")
        roles = []

    role_ids: set[str] = set()
    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            errors.append(f"roles[{idx}] muss ein Objekt sein")
            continue
        rid = str(role.get("id") or "").strip()
        label = str(role.get("label") or "").strip()
        if not rid:
            errors.append(f"roles[{idx}].id fehlt")
        elif rid in role_ids:
            errors.append(f"roles[{idx}].id doppelt: {rid}")
        else:
            role_ids.add(rid)
        if not label:
            errors.append(f"roles[{idx}].label fehlt")
        access = str(role.get("default_access") or "api").strip()
        if access not in VALID_ACCESS_TYPES:
            errors.append(f"roles[{idx}].default_access ungültig: {access}")

    maintenance = manifest.get("maintenance", [])
    if not isinstance(maintenance, list):
        errors.append("maintenance muss eine Liste sein")
        maintenance = []

    maint_ids: set[str] = set()
    for idx, item in enumerate(maintenance):
        if not isinstance(item, dict):
            errors.append(f"maintenance[{idx}] muss ein Objekt sein")
            continue
        mid = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        mclass = str(item.get("class") or "").strip()
        trigger = str(item.get("trigger") or "").strip()
        requires_model = item.get("requires_model")
        difficulty = str(item.get("difficulty") or "low").strip()
        requirements = item.get("requirements", [])

        if not mid:
            errors.append(f"maintenance[{idx}].id fehlt")
        elif mid in maint_ids:
            errors.append(f"maintenance[{idx}].id doppelt: {mid}")
        else:
            maint_ids.add(mid)
        if not label:
            errors.append(f"maintenance[{idx}].label fehlt")
        if mclass not in VALID_MAINTENANCE_CLASSES:
            errors.append(f"maintenance[{idx}].class ungültig: {mclass}")
        if not trigger:
            errors.append(f"maintenance[{idx}].trigger fehlt")
        if not isinstance(requires_model, bool):
            errors.append(f"maintenance[{idx}].requires_model muss bool sein")
        elif mclass == "job" and requires_model is True:
            errors.append(f"maintenance[{idx}] (class=job) darf kein Modell voraussetzen")
        elif mclass == "agent-required" and requires_model is False:
            errors.append(f"maintenance[{idx}] (class=agent-required) benötigt requires_model=True")
        if difficulty not in VALID_DIFFICULTIES:
            errors.append(f"maintenance[{idx}].difficulty ungültig: {difficulty}")
        if not isinstance(requirements, list):
            errors.append(f"maintenance[{idx}].requirements muss eine Liste sein")

    return errors


@dataclass
class ModuleDeliveryCatalog:
    """Verwaltet den Lebenszyklus (Install, Update, Uninstall) von Modul-Rollen und Pflegeaufgaben."""

    role_templates: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_instances: dict[str, dict[str, Any]] = field(default_factory=dict)
    maintenance_catalog: dict[str, dict[str, Any]] = field(default_factory=dict)
    scheduled_maintenance: dict[str, dict[str, Any]] = field(default_factory=dict)

    def install_or_update_module(self, manifest: dict[str, Any]) -> None:
        errors = validate_module_delivery_manifest(manifest)
        if errors:
            raise ValueError("; ".join(errors))
        module_id = str(manifest["id"]).strip()
        version = str(manifest.get("version") or "1.0.0")

        for role in manifest.get("roles", []):
            key = f"{module_id}:{role['id']}"
            self.role_templates[key] = {
                **role,
                "key": key,
                "origin_module": module_id,
                "origin_version": version,
                "is_template": True,
                "active": False,
                "origin_removed": False,
                "origin_badge": None,
            }
            for inst in self.agent_instances.values():
                if inst.get("template_key") == key:
                    inst["origin_removed"] = False
                    inst["origin_badge"] = None

        for maint in manifest.get("maintenance", []):
            key = f"{module_id}:{maint['id']}"
            self.maintenance_catalog[key] = {
                **maint,
                "key": key,
                "origin_module": module_id,
                "origin_version": version,
                "active": False,
                "origin_removed": False,
                "origin_badge": None,
            }
            if key in self.scheduled_maintenance:
                self.scheduled_maintenance[key]["origin_removed"] = False
                self.scheduled_maintenance[key]["origin_badge"] = None

    def instantiate_agent(self, template_key: str, instance_id: str, **overrides: Any) -> dict[str, Any]:
        if template_key not in self.role_templates:
            raise KeyError(f"Unbekannte Rollenvorlage: {template_key}")
        tpl = self.role_templates[template_key]
        inst = {
            "instance_id": instance_id,
            "template_key": template_key,
            "origin_module": tpl["origin_module"],
            "label": overrides.get("label", tpl["label"]),
            "default_access": overrides.get("default_access", tpl.get("default_access", "api")),
            "is_template": False,
            "origin_removed": False,
            "origin_badge": None,
        }
        self.agent_instances[instance_id] = inst
        return inst

    def schedule_maintenance(self, maint_key: str, *, execution_mode: str | None = None) -> dict[str, Any]:
        if maint_key not in self.maintenance_catalog:
            raise KeyError(f"Unbekannte Pflegeaufgabe: {maint_key}")
        item = self.maintenance_catalog[maint_key]
        mode = execution_mode or ("job" if item["class"] == "job" else "agent")
        if item["class"] == "job" and mode != "job":
            raise ValueError("Reine Skript-Jobs starten keinen Agenten")
        sched = {
            **item,
            "active": True,
            "execution_mode": mode,
            "origin_removed": False,
            "origin_badge": None,
        }
        self.scheduled_maintenance[maint_key] = sched
        return sched

    def uninstall_module(self, module_id: str) -> dict[str, Any]:
        removed_templates = [k for k, v in self.role_templates.items() if v["origin_module"] == module_id]
        for k in removed_templates:
            del self.role_templates[k]

        removed_maint = [k for k, v in self.maintenance_catalog.items() if v["origin_module"] == module_id]
        for k in removed_maint:
            del self.maintenance_catalog[k]

        marked_instances = []
        for iid, inst in self.agent_instances.items():
            if inst.get("origin_module") == module_id:
                inst["origin_removed"] = True
                inst["origin_badge"] = ORIGIN_REMOVED_BADGE
                marked_instances.append(iid)

        marked_schedules = []
        for skey, sched in self.scheduled_maintenance.items():
            if sched.get("origin_module") == module_id:
                sched["origin_removed"] = True
                sched["origin_badge"] = ORIGIN_REMOVED_BADGE
                marked_schedules.append(skey)

        return {
            "module_id": module_id,
            "removed_templates": removed_templates,
            "removed_maintenance": removed_maint,
            "marked_instances": marked_instances,
            "marked_schedules": marked_schedules,
        }


def project_module_library_and_routines(catalog: ModuleDeliveryCatalog) -> dict[str, Any]:
    """Erzeugt das GUI-View-Model für Agenten-Bibliothek und Routinen je Modul (#2448)."""
    library_cards: list[dict[str, Any]] = []
    for key, tpl in sorted(catalog.role_templates.items()):
        library_cards.append({
            "key": key,
            "id": tpl["id"],
            "label": tpl["label"],
            "origin_module": tpl["origin_module"],
            "origin_badge": tpl.get("origin_badge") or f"Modul: {tpl['origin_module']}",
            "origin_removed": bool(tpl.get("origin_removed")),
            "default_access": tpl.get("default_access", "api"),
            "actions": ["Agent anlegen", "In Werkstatt öffnen"],
        })

    instance_cards: list[dict[str, Any]] = []
    for iid, inst in sorted(catalog.agent_instances.items()):
        instance_cards.append({
            "instance_id": iid,
            "label": inst["label"],
            "origin_module": inst["origin_module"],
            "origin_removed": bool(inst.get("origin_removed")),
            "origin_badge": inst.get("origin_badge") or f"Modul: {inst['origin_module']}",
            "default_access": inst.get("default_access", "api"),
        })

    routine_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for key, item in sorted(catalog.maintenance_catalog.items()):
        seen_keys.add(key)
        sched = catalog.scheduled_maintenance.get(key)
        meta = CLASS_UI_META[item["class"]]
        routine_items.append({
            "key": key,
            "id": item["id"],
            "label": item["label"],
            "origin_module": item["origin_module"],
            "class": item["class"],
            "class_badge": meta["badge"],
            "execution_options": list(meta["execution_options"]),
            "selected_execution_mode": sched["execution_mode"] if sched else meta["default_execution_mode"],
            "trigger": item["trigger"],
            "requires_model": item["requires_model"],
            "difficulty": item["difficulty"],
            "requirements": list(item.get("requirements", [])),
            "scheduled": bool(sched and sched.get("active")),
            "origin_removed": False,
            "origin_badge": f"Modul: {item['origin_module']}",
        })

    for key, sched in sorted(catalog.scheduled_maintenance.items()):
        if key in seen_keys:
            continue
        meta = CLASS_UI_META[sched["class"]]
        routine_items.append({
            "key": key,
            "id": sched["id"],
            "label": sched["label"],
            "origin_module": sched["origin_module"],
            "class": sched["class"],
            "class_badge": meta["badge"],
            "execution_options": list(meta["execution_options"]),
            "selected_execution_mode": sched["execution_mode"],
            "trigger": sched["trigger"],
            "requires_model": sched["requires_model"],
            "difficulty": sched["difficulty"],
            "requirements": list(sched.get("requirements", [])),
            "scheduled": bool(sched.get("active")),
            "origin_removed": bool(sched.get("origin_removed")),
            "origin_badge": sched.get("origin_badge") or f"Modul: {sched['origin_module']}",
        })

    return {
        "agent_library": library_cards,
        "agent_instances": instance_cards,
        "routines": routine_items,
    }
