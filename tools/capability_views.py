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


def _frontmatter(raw: bytes) -> dict[str, str]:
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:80]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line.startswith((" ", "\t")):
            meta.setdefault(key.strip(), value.strip().strip("'\""))
    return meta


def skill_library(*, workspace: Path) -> dict:
    """Current ``skills/<name>/SKILL.md`` files of the workspace (BACH ``skill_library`` shape)."""
    workspace = Path(workspace)
    root = _child(workspace, "skills")
    if root is None or not root.is_dir():
        raise FileNotFoundError("skills")
    skills = []
    visited = 0
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        visited += 1
        if visited > MAX_SKILL_DIRECTORIES:
            raise RuntimeError("Skill-Katalog überschreitet die begrenzte Scanweite")
        if not SAFE_SEGMENT.fullmatch(entry.name) or entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
            continue
        path = _child(workspace, "skills", entry.name, "SKILL.md")
        if path is None or not path.is_file():
            continue
        try:
            raw, _ = _read_bytes(path, workspace, 1024 * 1024)
        except (OSError, ValueError):
            continue
        meta = _frontmatter(raw)
        skills.append({
            "id": entry.name, "name": meta.get("name") or entry.name, "category": meta.get("category") or "general",
            "version": meta.get("version") or "ohne Versionsnummer", "symbol": "",
            "source_version": hashlib.sha256(raw).hexdigest(), "evidence_type": "filesystem_present",
            "source_kind": "ocean_workspace", "role": (meta.get("description") or "")[:300],
            "description": (meta.get("description") or "")[:300]})
    skills.sort(key=lambda item: item["name"].casefold())
    result = {"schema": SKILL_LIBRARY_SCHEMA, "skills": skills, "count": len(skills),
              "categories": sorted({s["category"] for s in skills}), "source": "current_SKILL.md",
              "declared_only_included": False}
    return _redact(result, [0])
