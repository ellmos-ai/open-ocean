"""Read-only inventories for the shared GUI boards, served from OCEAN's own workspace.

Contracts (reference: BACH ``hub/_services/capability_inventory_service.py`` ``ocean_inventory`` and
``hub/_services/skill_source_service.py`` ``skill_library``; GUI readers: ellmos-system-gui
``src/lib/capability-board-client.mjs`` INVENTORIES, ``software-catalog.mjs`` ``catalogMatches``):

* ``GET /api/capabilities/ocean``         ``bach.capability-inventory.v1``, kind ``ocean``, catalog ``ocean-host-sources``
* ``GET /api/capabilities/skills/library`` ``bach.skill-library.v1``

Nothing is written or mocked. A field OCEAN cannot prove is ``null`` (``installed`` is only ``true``/``false`` from the
directory check, ``runtime_active`` is always ``null``). Paths are symbolic labels, never absolute.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

try:
    from .catalog_projection import (MAX_ITEMS, SAFE_SEGMENT, _child, _load_install, _modules, _read_bytes,
                                     _redact)
except ImportError:  # ocean_runtime.py direct entry point
    from catalog_projection import (MAX_ITEMS, SAFE_SEGMENT, _child, _load_install, _modules, _read_bytes,
                                    _redact)

OCEAN_SCHEMA = "bach.capability-inventory.v1"
SKILL_LIBRARY_SCHEMA = "bach.skill-library.v1"
MAX_SKILL_DIRECTORIES = 4096
# Same limits and id rule as BACH hub/_services/skill_source_service.py (SKILL_ID, MAX_SOURCE_BYTES) and the GUI client.
SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_SOURCE_BYTES = 200_000
MAX_TOTAL_SOURCE_BYTES = 20_000_000
# Same allow-list as BACH hub/_services/display_assets.py TICKET_SYMBOL_IDS.
SYMBOL_IDS = frozenset({"githubbot", "office", "scripts", "server", "sync", "topics", "topics_ai", "topics_gesim",
                        "topics_hardware", "topics_research", "topics_roblox", "topics_software", "topics_umbruch",
                        "topics_uni", "usr", "wissen"})


def _source_entry(record: dict, label: str | None = None) -> dict:
    return {"path": label or record["path_label"], "available": record["availability"] == "available",
            "source_version": record["source_version"]}


def ocean_inventory(*, workspace: Path) -> dict:
    """Modules of the installed OCEAN composition (BACH ``ocean_inventory`` item shape)."""
    workspace = Path(workspace)
    sources: list[dict] = []
    errors: list[dict] = []
    transaction, _plan = _load_install(workspace, sources)
    items = []
    for module in _modules(transaction, workspace, next((s["generated_at"] for s in sources), None)):
        proven = module["measured"]["installed"]  # True: identity proof read; False: directory absent; None: no proof
        items.append({
            "id": module["id"], "name": module["name"], "description": module["description"],
            "version": module["version"], "source_version": module["pin"]["commit"] or module["pin"]["content_hash"],
            "code_present": proven is not False,
            # true only when the install state resolved the module AND an identity proof was read; never from a run
            "installed": True if proven is True and module["status"] == "resolved" else (False if proven is False else None),
            "runtime_active": None, "evidence": module["measured"]["evidence"],
            "path": "<workspace>/modules/" + module["id"]})
    for source in sources:
        if source["availability"] == "error":
            errors.append({"source": source["path_label"], "reason": source["error"]})
    truncated = len(items) > MAX_ITEMS
    items = sorted(items[:MAX_ITEMS], key=lambda item: item["id"].casefold())
    result = {"schema": OCEAN_SCHEMA, "kind": "ocean", "items": items,
              "sources": [_source_entry(s) for s in sources], "errors": errors, "truncated": truncated,
              "catalog": "ocean-host-sources", "count": len(items)}
    return _redact(result, [0])


_FRONT_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _frontmatter(text: str) -> dict[str, str]:
    """Strict, bounded reader for flat ``key: scalar`` frontmatter. No YAML dependency: anything beyond a flat map of
    single-line scalars (block scalars ``|``/``>``, lists, nesting, flow collections, anchors, tags), a missing closing
    ``---`` or an unterminated quote yields ``{}``, i.e. the caller's fallbacks, never a half-parsed result."""
    if not text.startswith(("---\n", "---\r\n")):
        return {}
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None or end > 200:
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t-":
            return {}
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not _FRONT_KEY.fullmatch(key) or value[:1] in tuple("|>[{&*!%@`"):
            return {}
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                return {}
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        meta.setdefault(key, value)
    return meta


def skill_library(*, workspace: Path) -> dict:
    """Current ``skills/<name>/SKILL.md`` files of the workspace (BACH ``skill_library`` shape)."""
    workspace = Path(workspace)
    root = _child(workspace, "skills")
    if root is None or not root.is_dir():
        raise FileNotFoundError("skills")
    skills = []
    visited = 0
    total = 0
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        visited += 1
        if visited > MAX_SKILL_DIRECTORIES:
            raise RuntimeError("Skill-Katalog überschreitet die begrenzte Scanweite")
        if not SKILL_ID.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
            continue
        path = _child(workspace, "skills", entry.name, "SKILL.md")
        if path is None or not path.is_file():
            continue
        try:
            raw, _ = _read_bytes(path, workspace, MAX_SOURCE_BYTES)
            if b"\x00" in raw:
                continue
            text = raw.decode("utf-8")  # strict: invalid UTF-8 is not a skill source
        except (OSError, ValueError):
            continue
        total += len(raw)
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise RuntimeError("Skill-Katalog überschreitet die begrenzte Lesemenge")
        meta = _frontmatter(text)
        symbol = meta.get("symbol", "")
        skills.append({
            "id": entry.name, "name": (meta.get("name") or entry.name)[:200],
            "category": (meta.get("category") or "general")[:100],
            "version": (meta.get("version") or "ohne Versionsnummer")[:100],
            "symbol": symbol if symbol in SYMBOL_IDS else "",
            "source_version": hashlib.sha256(raw).hexdigest(), "evidence_type": "filesystem_present",
            "source_kind": "ocean_workspace", "role": (meta.get("description") or "")[:300],
            "description": (meta.get("description") or "")[:300]})
    skills.sort(key=lambda item: item["name"].casefold())
    result = {"schema": SKILL_LIBRARY_SCHEMA, "skills": skills, "count": len(skills),
              "categories": sorted({s["category"] for s in skills}), "source": "current_SKILL.md",
              "declared_only_included": False}
    return _redact(result, [0])
