# -*- coding: utf-8 -*-
"""Ocean-Modul agent-library & Lifecycle-Contracts:
- 3-Tab Agenten-Bibliothek (`templates`, `prompt_agents`, `chains`) (#2478)
- Gemeinsamer Routinen-, Ready- und Kalender-Lifecycle für Jobs ohne Modell,
  Miniagenten und Automations-Agenten (#2329)
- Gemeinsame Abschluss- und Auswahlbedienung für BACH und Ocean (#2259)
- Desktop-Harness Remote-Attach & Geräteabnahme-Beleg (#2337)
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
EXPECTED_ROLES_PATH = Path(__file__).with_name("agent_library_expected_roles.json")


_INSTALLED_CACHE: dict[tuple, list[tuple[Path, str]]] = {}


def _site_signature(dist_path: list[str] | None) -> tuple:
    """Cache-Schlüssel: Suchpfade samt mtime. Eine (De-)Installation ändert die mtime des Site-Ordners."""
    dirs = [str(d) for d in (dist_path if dist_path is not None else sys.path)]
    sig = []
    for d in dirs:
        try:
            sig.append((d, os.stat(d).st_mtime_ns))
        except OSError:
            sig.append((d, None))
    return tuple(sig)


def _installed_manifests(dist_path: list[str] | None = None) -> list[tuple[Path, str]]:
    """(absoluter Pfad, RECORD-relativer Pfad) der von installierten Paketen mitgelieferten Manifeste.

    Liest nur den RECORD-Text je Distribution; `Distribution.files` wird bewusst nicht benutzt, weil es ab
    Python 3.12 jede installierte Datei per stat prüft (gemessen: 71 s auf dem Laptop, 1,1 s auf dem Mac).
    Ergebnis wird je Prozess gecacht, solange sich die Suchpfade nicht ändern.
    """
    key = _site_signature(dist_path)
    cached = _INSTALLED_CACHE.get(key)
    if cached is not None:
        return cached
    found: list[tuple[Path, str]] = []
    dists = metadata.distributions(path=list(dist_path)) if dist_path is not None else metadata.distributions()
    for dist in dists:
        record = dist.read_text("RECORD")
        if not record or MODULE_MANIFEST not in record:
            continue
        for row in csv.reader(line for line in record.splitlines() if MODULE_MANIFEST in line):
            name = row[0] if row else ""
            if name.replace("\\", "/").rsplit("/", 1)[-1] != MODULE_MANIFEST:
                continue
            located = Path(str(dist.locate_file(name)))
            if located.is_file():
                found.append((located, name.replace("\\", "/")))
    _INSTALLED_CACHE.clear()  # nur der aktuelle Stand zählt
    _INSTALLED_CACHE[key] = found
    return found


def _installed_manifest_paths(dist_path: list[str] | None = None) -> list[Path]:
    return [path for path, _rel in _installed_manifests(dist_path)]


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
    # (Pfad, Herkunft, Pfad relativ zur Wurzel bzw. zum Site-Ordner; nur der relative Pfad verlässt den Prozess)
    candidates: list[tuple[Path, str, str]] = []
    for root in roots:
        if root.is_dir():
            candidates += [
                (child / MODULE_MANIFEST, "root", f"{child.name}/{MODULE_MANIFEST}")
                for child in sorted(root.iterdir(), key=lambda p: p.name.casefold())
            ]
    if include_installed if include_installed is not None else repos_root is None:
        candidates += [(path, "installed", rel) for path, rel in _installed_manifests(dist_path)]
    manifests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, via, rel in candidates:
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
        manifests.append({"module_id": module_id, "path": path, "rel_path": rel, "found_via": via, "manifest": manifest})
    return manifests


def discover_module_role_templates(
    repos_root: str | Path | None = None,
    *,
    extra_roots: list[str | Path] | None = None,
    include_installed: bool | None = None,
    dist_path: list[str] | None = None,
    manifests: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Scan module `ellmos-module.v2.json` manifests (siehe `discover_module_manifests`) and return Agent-Library templates.

    `manifests` erlaubt, einen bereits gemachten Scan wiederzuverwenden (ein Scan je Anfrage)."""
    discovered: list[dict[str, Any]] = []
    if manifests is None:
        manifests = discover_module_manifests(
            repos_root, extra_roots=extra_roots, include_installed=include_installed, dist_path=dist_path
        )
    for entry in manifests:
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
                    "manifest_path": entry["rel_path"],
                    "prompt": role.get("prompt"),
                    "request": role.get("request"),
                    "providers": list(role.get("providers") or ("claude", "codex", "agy", "kimi")),
                    "socket_id": "domain_specialist",
                }
            )
    return discovered


def load_expected_roles(path: str | Path | None = None) -> dict[str, Any]:
    """Mitgelieferte Soll-Rollenliste: `expected[]` und `exceptions[]`."""
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
    module_templates = discover_module_role_templates(manifests=manifests)
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
    expected_doc = load_expected_roles()
    report = check_expected_roles(
        catalog["templates"], expected_doc, found_modules={m["module_id"] for m in manifests}
    )
    exceptions = [dict(x, origin="legacy") for x in expected_doc.get("exceptions", [])]
    catalog["role_exceptions"] = exceptions
    catalog["expected_roles"] = report
    catalog["module_manifests"] = [
        {"module_id": m["module_id"], "path": m["rel_path"], "found_via": m["found_via"],
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


CALENDAR_SYNC_DIRECTIONS = frozenset({"bidirectional", "to_calendar", "from_calendar"})
CALENDAR_STATUSES = frozenset({"scheduled", "executed", "cancelled"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_timezone(tz_name: Any) -> str:
    text = str(tz_name or "Europe/Berlin").strip() or "Europe/Berlin"
    try:
        ZoneInfo(text)
    except Exception as exc:
        raise ValueError(f"Ungültige Zeitzone: {text}") from exc
    return text


def _parse_iso_datetime(value: Any, tz_name: str) -> tuple[datetime, str, str, str]:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Zeitstempel fehlt")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    tz = ZoneInfo(tz_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    local_dt = parsed.astimezone(tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    return local_dt, local_dt.isoformat(), utc_dt.isoformat(), local_dt.strftime("%z")


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    return json.loads(raw)


@dataclass
class AutomationLifecycleRegistry:
    """Verwaltet Jobs ohne Modell, Miniagenten und Automations-Agenten mit Persistenz, Kalender & Fence-Schutz (#2329)."""

    db_path: str | Path | None = None
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_triggers: dict[str, str] = field(default_factory=dict)
    calendar_bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    runs: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.db_path is not None:
            self.db_path = Path(self.db_path)
            self._init_schema()
            self._reload_from_db()

    def _connect(self) -> sqlite3.Connection:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_lifecycle_entries (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    family TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
                    state TEXT NOT NULL,
                    fence INTEGER NOT NULL DEFAULT 1,
                    scheduled INTEGER NOT NULL DEFAULT 1,
                    from_module INTEGER NOT NULL DEFAULT 0,
                    schedule_spec TEXT,
                    last_start_trigger TEXT,
                    started_at_local TEXT,
                    started_at_utc TEXT,
                    tz_offset TEXT,
                    input_schema_json TEXT,
                    output_schema_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_lifecycle_active_triggers (
                    entry_id TEXT PRIMARY KEY REFERENCES automation_lifecycle_entries(id) ON DELETE CASCADE,
                    dedup_key TEXT NOT NULL,
                    start_trigger TEXT NOT NULL,
                    run_id TEXT,
                    activated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS automation_lifecycle_calendar (
                    binding_id TEXT PRIMARY KEY,
                    entry_id TEXT NOT NULL REFERENCES automation_lifecycle_entries(id) ON DELETE CASCADE,
                    calendar_event_id TEXT NOT NULL,
                    sync_direction TEXT NOT NULL DEFAULT 'bidirectional',
                    scheduled_at_utc TEXT NOT NULL,
                    scheduled_at_local TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    tz_offset TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    external_etag TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(entry_id, calendar_event_id)
                );
                CREATE TABLE IF NOT EXISTS automation_lifecycle_runs (
                    run_id TEXT PRIMARY KEY,
                    entry_id TEXT NOT NULL REFERENCES automation_lifecycle_entries(id) ON DELETE CASCADE,
                    family TEXT NOT NULL,
                    configured_trigger TEXT NOT NULL,
                    start_trigger TEXT NOT NULL,
                    dedup_key TEXT NOT NULL,
                    fence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    started_at_local TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    tz_offset TEXT NOT NULL,
                    stopped_at_utc TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_alc_runs_trigger ON automation_lifecycle_runs(start_trigger, started_at_utc);
                CREATE INDEX IF NOT EXISTS idx_alc_runs_entry ON automation_lifecycle_runs(entry_id, started_at_utc);
                CREATE INDEX IF NOT EXISTS idx_alc_cal_entry ON automation_lifecycle_calendar(entry_id, status);
                """
            )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "family": row["family"],
            "trigger": row["trigger"],
            "timezone": row["timezone"],
            "state": row["state"],
            "fence": int(row["fence"]),
            "scheduled": bool(row["scheduled"]),
            "from_module": bool(row["from_module"]),
            "schedule_spec": row["schedule_spec"],
            "last_start_trigger": row["last_start_trigger"],
            "started_at_local": row["started_at_local"],
            "started_at_utc": row["started_at_utc"],
            "tz_offset": row["tz_offset"],
            "input_schema": _json_loads(row["input_schema_json"]),
            "output_schema": _json_loads(row["output_schema_json"]),
            "metadata": _json_loads(row["metadata_json"]) or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_binding(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "binding_id": row["binding_id"],
            "entry_id": row["entry_id"],
            "calendar_event_id": row["calendar_event_id"],
            "sync_direction": row["sync_direction"],
            "scheduled_at_utc": row["scheduled_at_utc"],
            "scheduled_at_local": row["scheduled_at_local"],
            "timezone": row["timezone"],
            "tz_offset": row["tz_offset"],
            "status": row["status"],
            "external_etag": row["external_etag"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "entry_id": row["entry_id"],
            "family": row["family"],
            "configured_trigger": row["configured_trigger"],
            "start_trigger": row["start_trigger"],
            "dedup_key": row["dedup_key"],
            "fence": int(row["fence"]),
            "status": row["status"],
            "timezone": row["timezone"],
            "started_at_local": row["started_at_local"],
            "started_at_utc": row["started_at_utc"],
            "tz_offset": row["tz_offset"],
            "stopped_at_utc": row["stopped_at_utc"],
        }

    def _reload_from_db(self) -> None:
        if self.db_path is None:
            return
        with self._connect() as conn:
            self.entries = {
                r["id"]: self._row_to_entry(r)
                for r in conn.execute("SELECT * FROM automation_lifecycle_entries ORDER BY id").fetchall()
            }
            self.active_triggers = {
                r["entry_id"]: r["dedup_key"]
                for r in conn.execute("SELECT entry_id, dedup_key FROM automation_lifecycle_active_triggers").fetchall()
            }
            self.calendar_bindings = {
                r["binding_id"]: self._row_to_binding(r)
                for r in conn.execute("SELECT * FROM automation_lifecycle_calendar ORDER BY updated_at, binding_id").fetchall()
            }
            self.runs = [
                self._row_to_run(r)
                for r in conn.execute("SELECT * FROM automation_lifecycle_runs ORDER BY started_at_utc, run_id").fetchall()
            ]

    @staticmethod
    def _validate_family_contract(family: str, payload: dict[str, Any]) -> None:
        if family not in FAMILIES:
            raise ValueError(f"Ungültige Familie: {family}")
        if family == "job" and payload.get("requires_model"):
            raise ValueError("Jobs ohne Modell dürfen kein Sprachmodell anfordern")
        if family == "mini_agent":
            if not payload.get("input_schema") or not payload.get("output_schema"):
                raise ValueError("Miniagenten benötigen festen Ein-/Ausgabevertrag (input_schema/output_schema)")
            if payload.get("allows_open_work") or payload.get("allows_reviews"):
                raise ValueError("Miniagenten erlauben keine offene Agentenarbeit oder Reviews")

    def register_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        eid = str(payload.get("id") or "").strip()
        family = str(payload.get("family") or "").strip()
        trigger = str(payload.get("trigger") or "routine").strip()
        if not eid:
            raise ValueError("id fehlt")
        self._validate_family_contract(family, payload)
        if trigger not in TRIGGERS:
            raise ValueError(f"Ungültige Startart: {trigger}")
        tz_name = _validate_timezone(payload.get("timezone"))
        from_module = bool(payload.get("from_module", False))
        scheduled = bool(payload.get("scheduled", not from_module))
        if "scheduled" in payload:
            scheduled = bool(payload["scheduled"])
        state = "available" if from_module and not scheduled else "ready"
        now_utc = _utc_now_iso()
        record = {
            "id": eid,
            "title": str(payload.get("title") or eid),
            "family": family,
            "trigger": trigger,
            "timezone": tz_name,
            "state": state,
            "fence": int(payload.get("fence") or 1),
            "scheduled": scheduled,
            "from_module": from_module,
            "schedule_spec": payload.get("schedule_spec"),
            "last_start_trigger": None,
            "started_at_local": None,
            "started_at_utc": None,
            "tz_offset": None,
            "input_schema": payload.get("input_schema"),
            "output_schema": payload.get("output_schema"),
            "metadata": dict(payload.get("metadata") or {}),
            "created_at": now_utc,
            "updated_at": now_utc,
        }
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO automation_lifecycle_entries (
                        id, title, family, trigger, timezone, state, fence,
                        scheduled, from_module, schedule_spec, last_start_trigger,
                        started_at_local, started_at_utc, tz_offset,
                        input_schema_json, output_schema_json, metadata_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        family=excluded.family,
                        trigger=excluded.trigger,
                        timezone=excluded.timezone,
                        state=excluded.state,
                        fence=excluded.fence,
                        scheduled=excluded.scheduled,
                        from_module=excluded.from_module,
                        schedule_spec=excluded.schedule_spec,
                        input_schema_json=excluded.input_schema_json,
                        output_schema_json=excluded.output_schema_json,
                        metadata_json=excluded.metadata_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        record["id"],
                        record["title"],
                        record["family"],
                        record["trigger"],
                        record["timezone"],
                        record["state"],
                        record["fence"],
                        int(record["scheduled"]),
                        int(record["from_module"]),
                        record["schedule_spec"],
                        record["last_start_trigger"],
                        record["started_at_local"],
                        record["started_at_utc"],
                        record["tz_offset"],
                        _json_dumps(record["input_schema"]),
                        _json_dumps(record["output_schema"]),
                        _json_dumps(record["metadata"]),
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
            self._reload_from_db()
            return dict(self.entries[eid])
        self.entries[eid] = record
        return dict(record)

    def get_entry(self, eid: str) -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        return dict(self.entries[eid])

    def list_entries(
        self,
        *,
        family: str | None = None,
        state: str | None = None,
        trigger: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.db_path is not None:
            self._reload_from_db()
        items = list(self.entries.values())
        if family is not None:
            items = [item for item in items if item["family"] == family]
        if state is not None:
            items = [item for item in items if item["state"] == state]
        if trigger is not None:
            items = [item for item in items if item["trigger"] == trigger]
        items.sort(key=lambda item: item["id"])
        return [dict(item) for item in items]

    def update_entry(
        self,
        eid: str,
        patch: dict[str, Any],
        *,
        expected_fence: int | None = None,
    ) -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        current = dict(self.entries[eid])
        cur_fence = int(current["fence"])
        if expected_fence is not None and cur_fence != expected_fence:
            raise RuntimeError(f"Fence-Konflikt beim Update: erwartet {expected_fence}, aktuell {cur_fence}")

        merged = {**current, **patch, "id": eid}
        self._validate_family_contract(str(merged.get("family") or ""), merged)
        trigger = str(merged.get("trigger") or "").strip()
        if trigger not in TRIGGERS:
            raise ValueError(f"Ungültige Startart: {trigger}")
        tz_name = _validate_timezone(merged.get("timezone"))
        now_utc = _utc_now_iso()
        new_fence = cur_fence + 1
        updated = {
            **current,
            "title": str(merged.get("title") or current["title"]),
            "family": str(merged["family"]),
            "trigger": trigger,
            "timezone": tz_name,
            "scheduled": bool(merged.get("scheduled", current.get("scheduled", True))),
            "schedule_spec": merged.get("schedule_spec", current.get("schedule_spec")),
            "input_schema": merged.get("input_schema", current.get("input_schema")),
            "output_schema": merged.get("output_schema", current.get("output_schema")),
            "metadata": dict(merged.get("metadata") if merged.get("metadata") is not None else current.get("metadata") or {}),
            "fence": new_fence,
            "updated_at": now_utc,
        }
        if current["state"] == "available" and updated["scheduled"]:
            updated["state"] = "ready"

        if self.db_path is not None:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE automation_lifecycle_entries
                    SET title=?, family=?, trigger=?, timezone=?, state=?, fence=?,
                        scheduled=?, schedule_spec=?, input_schema_json=?, output_schema_json=?,
                        metadata_json=?, updated_at=?
                    WHERE id=? AND fence=?
                    """,
                    (
                        updated["title"],
                        updated["family"],
                        updated["trigger"],
                        updated["timezone"],
                        updated["state"],
                        new_fence,
                        int(updated["scheduled"]),
                        updated["schedule_spec"],
                        _json_dumps(updated["input_schema"]),
                        _json_dumps(updated["output_schema"]),
                        _json_dumps(updated["metadata"]),
                        now_utc,
                        eid,
                        cur_fence,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Fence-Konflikt beim Update: konkurrierende Änderung für {eid}")
            self._reload_from_db()
            return dict(self.entries[eid])
        self.entries[eid] = updated
        return dict(updated)

    def schedule_entry(
        self,
        eid: str,
        *,
        schedule_spec: str | None = None,
        timezone: str | None = None,
        expected_fence: int | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {"scheduled": True}
        if schedule_spec is not None:
            patch["schedule_spec"] = schedule_spec
        if timezone is not None:
            patch["timezone"] = timezone
        return self.update_entry(eid, patch, expected_fence=expected_fence)

    def delete_entry(self, eid: str, *, expected_fence: int | None = None) -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        current = dict(self.entries[eid])
        cur_fence = int(current["fence"])
        if expected_fence is not None and cur_fence != expected_fence:
            raise RuntimeError(f"Fence-Konflikt beim Löschen: erwartet {expected_fence}, aktuell {cur_fence}")
        if current["state"] == "running":
            raise RuntimeError(f"Laufender Eintrag {eid} muss vor dem Löschen gestoppt werden")

        if self.db_path is not None:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM automation_lifecycle_entries WHERE id=? AND fence=?",
                    (eid, cur_fence),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Fence-Konflikt beim Löschen: konkurrierende Änderung für {eid}")
            self._reload_from_db()
        else:
            self.entries.pop(eid, None)
            self.active_triggers.pop(eid, None)
            for bid in [k for k, v in self.calendar_bindings.items() if v["entry_id"] == eid]:
                self.calendar_bindings.pop(bid, None)
        return {"deleted": True, "id": eid, "fence": cur_fence}

    def bind_calendar_event(
        self,
        eid: str,
        *,
        calendar_event_id: str,
        scheduled_at: str,
        sync_direction: str = "bidirectional",
        external_etag: str | None = None,
        confirm_schedule: bool = True,
    ) -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        cal_id = str(calendar_event_id or "").strip()
        if not cal_id:
            raise ValueError("calendar_event_id fehlt")
        if sync_direction not in CALENDAR_SYNC_DIRECTIONS:
            raise ValueError(f"Ungültige Kalender-Sync-Richtung: {sync_direction}")

        entry = self.entries[eid]
        tz_name = entry["timezone"]
        _, local_iso, utc_iso, tz_offset = _parse_iso_datetime(scheduled_at, tz_name)
        now_utc = _utc_now_iso()

        if confirm_schedule and entry["state"] == "available":
            self.schedule_entry(eid, schedule_spec=utc_iso, expected_fence=int(entry["fence"]))

        existing = next(
            (b for b in self.calendar_bindings.values() if b["entry_id"] == eid and b["calendar_event_id"] == cal_id),
            None,
        )
        binding_id = existing["binding_id"] if existing else f"calbind-{uuid.uuid4().hex[:12]}"
        binding = {
            "binding_id": binding_id,
            "entry_id": eid,
            "calendar_event_id": cal_id,
            "sync_direction": sync_direction,
            "scheduled_at_utc": utc_iso,
            "scheduled_at_local": local_iso,
            "timezone": tz_name,
            "tz_offset": tz_offset,
            "status": "scheduled",
            "external_etag": external_etag,
            "updated_at": now_utc,
        }
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO automation_lifecycle_calendar (
                        binding_id, entry_id, calendar_event_id, sync_direction,
                        scheduled_at_utc, scheduled_at_local, timezone, tz_offset,
                        status, external_etag, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entry_id, calendar_event_id) DO UPDATE SET
                        sync_direction=excluded.sync_direction,
                        scheduled_at_utc=excluded.scheduled_at_utc,
                        scheduled_at_local=excluded.scheduled_at_local,
                        timezone=excluded.timezone,
                        tz_offset=excluded.tz_offset,
                        status='scheduled',
                        external_etag=excluded.external_etag,
                        updated_at=excluded.updated_at
                    """,
                    (
                        binding["binding_id"],
                        binding["entry_id"],
                        binding["calendar_event_id"],
                        binding["sync_direction"],
                        binding["scheduled_at_utc"],
                        binding["scheduled_at_local"],
                        binding["timezone"],
                        binding["tz_offset"],
                        binding["status"],
                        binding["external_etag"],
                        binding["updated_at"],
                    ),
                )
            self._reload_from_db()
            return dict(self.calendar_bindings[binding_id])
        self.calendar_bindings[binding_id] = binding
        return dict(binding)

    def cancel_calendar_event(
        self,
        eid: str,
        *,
        calendar_event_id: str | None = None,
        binding_id: str | None = None,
        source: str = "local",
    ) -> dict[str, Any]:
        if source not in {"local", "calendar"}:
            raise ValueError(f"Ungültige Storno-Quelle: {source}")
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")

        match = None
        for b in self.calendar_bindings.values():
            if b["entry_id"] != eid:
                continue
            if binding_id and b["binding_id"] == binding_id:
                match = b
                break
            if calendar_event_id and b["calendar_event_id"] == calendar_event_id:
                match = b
                break
        if match is None:
            raise KeyError(f"Keine Kalenderbindung gefunden für {eid}")

        if source == "calendar" and match["sync_direction"] == "to_calendar":
            raise PermissionError("Einseitige Kalenderbindung (to_calendar) blockiert externes Storno")

        now_utc = _utc_now_iso()
        updated = {**match, "status": "cancelled", "updated_at": now_utc}
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE automation_lifecycle_calendar SET status='cancelled', updated_at=? WHERE binding_id=?",
                    (now_utc, match["binding_id"]),
                )
            self._reload_from_db()
            return {**self.calendar_bindings[match["binding_id"]], "cancelled_by": source}
        self.calendar_bindings[match["binding_id"]] = updated
        return {**updated, "cancelled_by": source}

    def list_calendar_bindings(
        self,
        eid: str | None = None,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.db_path is not None:
            self._reload_from_db()
        items = list(self.calendar_bindings.values())
        if eid is not None:
            items = [item for item in items if item["entry_id"] == eid]
        if status is not None:
            items = [item for item in items if item["status"] == status]
        items.sort(key=lambda item: (item["scheduled_at_utc"], item["binding_id"]))
        return [dict(item) for item in items]

    def trigger_start(
        self,
        eid: str,
        *,
        start_trigger: str,
        dedup_key: str,
        tz_now: datetime | None = None,
    ) -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        if start_trigger not in TRIGGERS:
            raise ValueError(f"Ungültiger Startanlass: {start_trigger}")
        if not str(dedup_key or "").strip():
            raise ValueError("dedup_key fehlt")
        if self.active_triggers.get(eid) == dedup_key:
            return {**self.entries[eid], "deduplicated": True}

        rec = self.entries[eid]
        if rec["state"] == "available":
            raise RuntimeError("Mitgelieferte Pflegeaufgaben laufen erst nach bestätigter Planung")

        tz = ZoneInfo(rec["timezone"])
        base_now = tz_now or datetime.now(tz)
        if base_now.tzinfo is None:
            base_now = base_now.replace(tzinfo=tz)
        now_local = base_now.astimezone(tz)
        now_utc = now_local.astimezone(timezone.utc)
        started_local_iso = now_local.isoformat()
        started_utc_iso = now_utc.isoformat()
        tz_offset = now_local.strftime("%z")
        cur_fence = int(rec["fence"])
        new_fence = cur_fence + 1
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        now_stamp = _utc_now_iso()

        run_record = {
            "run_id": run_id,
            "entry_id": eid,
            "family": rec["family"],
            "configured_trigger": rec["trigger"],
            "start_trigger": start_trigger,
            "dedup_key": dedup_key,
            "fence": new_fence,
            "status": "running",
            "timezone": rec["timezone"],
            "started_at_local": started_local_iso,
            "started_at_utc": started_utc_iso,
            "tz_offset": tz_offset,
            "stopped_at_utc": None,
        }

        if self.db_path is not None:
            with self._connect() as conn:
                existing_trig = conn.execute(
                    "SELECT dedup_key FROM automation_lifecycle_active_triggers WHERE entry_id=?",
                    (eid,),
                ).fetchone()
                if existing_trig and existing_trig["dedup_key"] == dedup_key:
                    self._reload_from_db()
                    return {**self.entries[eid], "deduplicated": True}
                cur = conn.execute(
                    """
                    UPDATE automation_lifecycle_entries
                    SET fence=?, state='running', last_start_trigger=?,
                        started_at_local=?, started_at_utc=?, tz_offset=?, updated_at=?
                    WHERE id=? AND fence=? AND state != 'available'
                    """,
                    (
                        new_fence,
                        start_trigger,
                        started_local_iso,
                        started_utc_iso,
                        tz_offset,
                        now_stamp,
                        eid,
                        cur_fence,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Fence-Konflikt beim Start: konkurrierende Änderung für {eid}")
                conn.execute(
                    """
                    INSERT INTO automation_lifecycle_active_triggers (
                        entry_id, dedup_key, start_trigger, run_id, activated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(entry_id) DO UPDATE SET
                        dedup_key=excluded.dedup_key,
                        start_trigger=excluded.start_trigger,
                        run_id=excluded.run_id,
                        activated_at=excluded.activated_at
                    """,
                    (eid, dedup_key, start_trigger, run_id, now_stamp),
                )
                conn.execute(
                    """
                    INSERT INTO automation_lifecycle_runs (
                        run_id, entry_id, family, configured_trigger, start_trigger,
                        dedup_key, fence, status, timezone, started_at_local,
                        started_at_utc, tz_offset, stopped_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        run_record["run_id"],
                        run_record["entry_id"],
                        run_record["family"],
                        run_record["configured_trigger"],
                        run_record["start_trigger"],
                        run_record["dedup_key"],
                        run_record["fence"],
                        run_record["status"],
                        run_record["timezone"],
                        run_record["started_at_local"],
                        run_record["started_at_utc"],
                        run_record["tz_offset"],
                    ),
                )
            self._reload_from_db()
            return {**self.entries[eid], "deduplicated": False, "run_id": run_id}

        rec["fence"] = new_fence
        rec["state"] = "running"
        rec["last_start_trigger"] = start_trigger
        rec["started_at_local"] = started_local_iso
        rec["started_at_utc"] = started_utc_iso
        rec["tz_offset"] = tz_offset
        rec["updated_at"] = now_stamp
        self.active_triggers[eid] = dedup_key
        self.runs.append(run_record)
        return {**rec, "deduplicated": False, "run_id": run_id}

    def stop_entry(self, eid: str, *, expected_fence: int, status: str = "stopped") -> dict[str, Any]:
        if self.db_path is not None:
            self._reload_from_db()
        if eid not in self.entries:
            raise KeyError(f"Unbekannter Eintrag: {eid}")
        rec = self.entries[eid]
        cur_fence = int(rec["fence"])
        if cur_fence != expected_fence:
            raise RuntimeError(f"Fence-Konflikt beim Stopp: erwartet {expected_fence}, aktuell {cur_fence}")
        new_fence = cur_fence + 1
        now_utc = _utc_now_iso()

        if self.db_path is not None:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE automation_lifecycle_entries
                    SET fence=?, state='ready', updated_at=?
                    WHERE id=? AND fence=?
                    """,
                    (new_fence, now_utc, eid, expected_fence),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Fence-Konflikt beim Stopp: konkurrierende Änderung für {eid}")
                trig_row = conn.execute(
                    "SELECT run_id FROM automation_lifecycle_active_triggers WHERE entry_id=?",
                    (eid,),
                ).fetchone()
                if trig_row and trig_row["run_id"]:
                    conn.execute(
                        "UPDATE automation_lifecycle_runs SET status=?, stopped_at_utc=? WHERE run_id=?",
                        (status, now_utc, trig_row["run_id"]),
                    )
                conn.execute("DELETE FROM automation_lifecycle_active_triggers WHERE entry_id=?", (eid,))
                if rec.get("trigger") == "calendar_once":
                    conn.execute(
                        "UPDATE automation_lifecycle_calendar SET status='executed', updated_at=? WHERE entry_id=? AND status='scheduled'",
                        (now_utc, eid),
                    )
            self._reload_from_db()
            return dict(self.entries[eid])

        rec["fence"] = new_fence
        rec["state"] = "ready"
        rec["updated_at"] = now_utc
        self.active_triggers.pop(eid, None)
        for run in reversed(self.runs):
            if run["entry_id"] == eid and run["status"] == "running":
                run["status"] = status
                run["stopped_at_utc"] = now_utc
                break
        if rec.get("trigger") == "calendar_once":
            for b in self.calendar_bindings.values():
                if b["entry_id"] == eid and b["status"] == "scheduled":
                    b["status"] = "executed"
                    b["updated_at"] = now_utc
        return dict(rec)

    def list_runs(
        self,
        eid: str | None = None,
        *,
        start_trigger: str | None = None,
        group_by_trigger: bool = False,
    ) -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
        if start_trigger is not None and start_trigger not in TRIGGERS:
            raise ValueError(f"Ungültiger Startanlass: {start_trigger}")
        if self.db_path is not None:
            self._reload_from_db()
        items = list(self.runs)
        if eid is not None:
            items = [r for r in items if r["entry_id"] == eid]
        if start_trigger is not None:
            items = [r for r in items if r["start_trigger"] == start_trigger]
        items = [dict(r) for r in items]
        if not group_by_trigger:
            return items
        grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in sorted(TRIGGERS)}
        for run in items:
            grouped.setdefault(run["start_trigger"], []).append(run)
        return grouped


def open_workspace_lifecycle_registry(workspace: str | Path) -> AutomationLifecycleRegistry:
    """Öffnet die persistente Workspace-Lifecycle-DB unter `<workspace>/state/automation_lifecycle.db` (#2329)."""
    return AutomationLifecycleRegistry(db_path=Path(workspace) / "state" / "automation_lifecycle.db")


def read_workspace_automation_lifecycle(workspace: str | Path) -> dict[str, Any]:
    """Liest den aktuellen Lifecycle-Snapshot eines Workspace fail-soft aus."""
    db_file = Path(workspace) / "state" / "automation_lifecycle.db"
    if not db_file.is_file():
        return {
            "available": False,
            "db_path": str(db_file),
            "entries": [],
            "calendar_bindings": [],
            "runs_by_trigger": {t: [] for t in sorted(TRIGGERS)},
        }
    reg = AutomationLifecycleRegistry(db_path=db_file)
    return {
        "available": True,
        "db_path": str(db_file),
        "entries": reg.list_entries(),
        "calendar_bindings": reg.list_calendar_bindings(),
        "runs_by_trigger": reg.list_runs(group_by_trigger=True),
    }


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
