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
import json
import os
import re
from pathlib import Path

try:
    from .catalog_projection import (MAX_ITEMS, _child, _load_install, _modules, _read_bytes,
                                     _redact)
except ImportError:  # ocean_runtime.py direct entry point
    from catalog_projection import (MAX_ITEMS, _child, _load_install, _modules, _read_bytes,
                                    _redact)

OCEAN_SCHEMA = "bach.capability-inventory.v1"
SKILL_LIBRARY_SCHEMA = "bach.skill-library.v1"
MAX_SKILL_DIRECTORIES = 4096
# Same limits and id rule as BACH hub/_services/skill_source_service.py (SKILL_ID, MAX_SOURCE_BYTES) and the GUI client.
SKILL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_SOURCE_BYTES = 200_000
MAX_TOTAL_SOURCE_BYTES = 20_000_000
MAX_RESPONSE_BYTES = 5_000_000
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
    return _bounded(_redact(result, [0]))


try:  # PyYAML is the optional "gui" dependency; BACH reads the same frontmatter with yaml.safe_load
    import yaml as _yaml
    _YAML_LOADER = getattr(_yaml, "CSafeLoader", _yaml.SafeLoader)
except ImportError:  # no home-made parser as a substitute: metadata is then reported as degraded
    _yaml = None
    _YAML_LOADER = None

_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _metadata(text: str) -> dict[str, str]:
    """``yaml.safe_load`` of the frontmatter block (BACH ``skill_source_service._metadata``), then reduced to the five
    keys the library uses. The block starts with ``---`` at the first line and ends at the first line that is exactly
    ``---`` in column 0 (an indented ``---`` belongs to a block scalar). Only ``str`` values without control
    characters are kept; any other type (null, number, list ...) leaves that field to its fallback."""
    if _yaml is None:
        return {}
    text = text.removeprefix("\ufeff")
    if not text.startswith(("---\n", "---\r\n")):
        return {}
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines[1:], 1) if line == "---"), None)
    if end is None:
        return {}
    try:
        data = _yaml.load("\n".join(lines[1:end]) + "\n", Loader=_YAML_LOADER)
    except Exception:  # YAMLError, RecursionError, ... : unreadable metadata is no metadata
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in ("name", "category", "version", "description", "symbol")
            if isinstance(data.get(key), str) and not _CONTROL.search(data[key])}


def _bounded(result: dict) -> dict:
    """Refuse an answer whose serialized size exceeds the limit (the caller maps this to 503), instead of sending it."""
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Antwort überschreitet das Größenlimit")
    return result


def skill_library(*, workspace: Path) -> dict:
    """Current ``skills/<name>/SKILL.md`` files of the workspace (BACH ``skill_library`` shape)."""
    workspace = Path(workspace)
    root = _child(workspace, "skills")
    if root is None or not root.is_dir():
        raise FileNotFoundError("skills")
    names = []
    with os.scandir(root) as listing:
        for entry in listing:  # the entry limit is enforced while scanning, before anything is sorted or read
            if len(names) >= MAX_SKILL_DIRECTORIES:
                raise RuntimeError("Skill-Katalog überschreitet die begrenzte Scanweite")
            names.append(entry.name)
    skills = []
    budget = 0
    for name in sorted(names):
        if not SKILL_ID.fullmatch(name):
            continue
        folder = _child(workspace, "skills", name)
        path = _child(workspace, "skills", name, "SKILL.md")
        if folder is None or path is None or not folder.is_dir() or not path.is_file():
            continue
        raw = None
        try:
            raw, _ = _read_bytes(path, workspace, MAX_SOURCE_BYTES)
            budget += len(raw)
        except ValueError:
            budget += MAX_SOURCE_BYTES + 1  # an oversized file was still read up to the limit: it counts
        except OSError:
            pass
        if budget > MAX_TOTAL_SOURCE_BYTES:  # EVERY read attempt counts, valid or not
            raise RuntimeError("Skill-Katalog überschreitet die begrenzte Lesemenge")
        if raw is None or b"\x00" in raw:
            continue
        try:
            text = raw.decode("utf-8")  # strict: invalid UTF-8 is not a skill source
        except UnicodeDecodeError:
            continue
        meta = _metadata(text)
        symbol = meta.get("symbol", "")
        description = meta.get("description", "")[:300]
        skills.append({
            "id": name, "name": (meta.get("name") or name)[:200],
            "category": (meta.get("category") or "general")[:100],
            "version": (meta.get("version") or "ohne Versionsnummer")[:100],
            "symbol": symbol if symbol in SYMBOL_IDS else "",
            "source_version": hashlib.sha256(raw).hexdigest(), "evidence_type": "filesystem_present",
            "source_kind": "ocean_workspace", "role": description, "description": description})
    skills.sort(key=lambda item: item["name"].casefold())
    result = {"schema": SKILL_LIBRARY_SCHEMA, "skills": skills, "count": len(skills),
              "categories": sorted({s["category"] for s in skills}), "source": "current_SKILL.md",
              "declared_only_included": False}
    if _yaml is None:
        result["degraded"] = ["frontmatter:yaml-unavailable"]  # additive: names/versions/descriptions could not be read
    # No path redaction: the BACH library has no path field, and name/category/version/description are the skill author's own
    # text (a literal /dev/null must stay as written). Redaction stays on the Ocean source inventory above.
    return _bounded(result)

MAX_SOFTWARE_BYTES = 2_000_000


def _text(value, limit=300) -> str:
    return value[:limit] if isinstance(value, str) and "\x00" not in value else ""


def _catalog_link(value) -> str | None:
    from urllib.parse import urlsplit
    if not isinstance(value, str) or len(value) > 1000:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        return value
    except ValueError:
        return None


def software_inventory(*, releases_path: Path) -> dict:
    """Serve BACH's ``GET /api/capabilities/software`` contract from a bound ``releases.json``."""
    releases_path = Path(releases_path)
    root = releases_path.parent
    raw, _ = _read_bytes(releases_path, root, MAX_SOFTWARE_BYTES)
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise ValueError("Software-Register benötigt eine Projektliste")
    revision = hashlib.sha256(raw).hexdigest()
    projects = data["projects"]
    truncated = len(projects) > MAX_ITEMS
    items = []
    seen = set()
    for project in projects[:MAX_ITEMS]:
        if not isinstance(project, dict):
            raise ValueError("Ungültiger Software-Projekteintrag")
        name = _text(project.get("name"), 180)
        relative = project.get("path")
        if (not name or not isinstance(relative, str) or not relative
                or "\\" in relative or ":" in relative or "\x00" in relative
                or relative.startswith("/") or ".." in relative.split("/")):
            raise ValueError("Ungültiger Software-Projektpfad")
        key = hashlib.sha256(("releases.json:" + relative).encode("utf-8")).hexdigest()[:24]
        if key in seen:
            continue
        targets = project.get("targets", [])
        if not isinstance(targets, list):
            raise ValueError("Software-Veröffentlichungen benötigen eine Liste")
        publications = []
        for target in targets[:30]:
            if not isinstance(target, dict):
                continue
            publications.append({
                "type": _text(target.get("type"), 80),
                "platform": _text(target.get("platform"), 80),
                "declared_status": _text(target.get("status"), 80),
                "version": _text(target.get("version"), 100) or None,
                "url": _catalog_link(target.get("release_url")) or _catalog_link(target.get("url")),
                "live_verified": False,
            })
        seen.add(key)
        folder = _child(root, *relative.split("/"))
        items.append({
            "id": key, "name": name,
            "description": _text(project.get("description")),
            "version": _text(project.get("version"), 100) or None,
            "category": relative.split("/", 1)[0],
            "lifecycle": _text(project.get("lifecycle"), 80),
            "source_version": revision, "source": "<software>/releases.json",
            "code_present": bool(folder is not None and folder.is_dir()),
            "installed": None, "runtime_active": None,
            "evidence": "software_release_catalog", "publications": publications,
        })
    items.sort(key=lambda item: item["name"].casefold())
    result = {
        "schema": OCEAN_SCHEMA, "kind": "software", "items": items,
        "sources": [{"path": "<software>/releases.json", "available": True, "source_version": revision}],
        "errors": [], "truncated": truncated, "catalog": "software-applications", "count": len(items),
    }
    return _bounded(_redact(result, [0]))

