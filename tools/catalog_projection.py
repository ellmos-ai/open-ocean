"""Read-only catalog projection ``bach.catalog.v1`` over OCEAN's own composition.

Same contract as BACH ``GET /api/capabilities/catalog`` (item, source and envelope fields are
unchanged; no second contract). The data comes only from the OCEAN workspace: ``ocean.install.json``
(components, fetch, activate, bundle verification), ``modules/<id>`` and ``skills/<name>/SKILL.md``.
Nothing is written, nothing is mocked: a missing or broken source is ``availability: missing|error``
with empty items, one broken source never stops the others, counts are derived from the items and
every output string is path-redacted (``<pfad>``). ``satellite`` has no OCEAN source and stays missing.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "bach.catalog.v1"
KINDS = ("module", "bundle", "stack", "skill", "satellite")
MAX_ITEMS = 5000
MAX_BYTES = 32 * 1024 * 1024
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
REDACTED = "<pfad>"
INSTALL_STATE = "ocean.install.json"
RUNTIME_STATE = "ocean.runtime.json"

_TAIL = r"[^\s\"'<>|,;)]*"
_PATH_PATTERNS = [
    re.compile(r"file://[^\s\"'<>|,;)]+"),
    re.compile(r"(?<!\w)[A-Za-z]:[\\/]" + _TAIL),
    re.compile(r"\\\\[^\s\"'<>|,;)]+"),
    re.compile(r"(?<!\w)~[\\/]" + _TAIL),
    re.compile(r"%[A-Za-z_]+%[\\/]" + _TAIL),
    re.compile(r"(?<![^\s\"'(=\[:,;])/(?!api/)[^\s/\"'<>|,;)]+/[^\s\"'<>|,;)]+"),
]
_REPARSE_FLAG = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _text(value: Any, limit: int = 500) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [x for x in _list(value) if isinstance(x, str)]


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _time(raw: Any) -> tuple[str | None, str, str | None]:
    """(utc_iso | None, basis, raw_when_not_normalised); a zone-less time is never shown as UTC."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "absent", None
    if not isinstance(raw, str):
        return None, "unparsable", None
    candidate = raw.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None, "unparsable", candidate[:80]
    if parsed.tzinfo is None:
        return None, "no_timezone", candidate[:80]
    return parsed.astimezone(timezone.utc).isoformat(), "declared", None


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & _REPARSE_FLAG)


def _child(root: Path, *segments: str) -> Path | None:
    """A path below ``root`` made of safe segments, none of them a link (pre-filter, then re-checked on read)."""
    path = root
    for segment in segments:
        if not SAFE_SEGMENT.fullmatch(segment) or segment in {".", ".."}:
            return None
        path = path / segment
        if _is_link(path):
            return None
    return path


def _read_bytes(path: Path, root: Path, limit: int = MAX_BYTES) -> tuple[bytes, str]:
    """Read a regular file whose resolved location lies inside ``root``; returns (bytes, mtime_iso)."""
    if _is_link(path):
        raise PermissionError("link")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root.resolve(strict=True))
    with open(resolved, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise FileNotFoundError("missing")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("too_large")
    return raw, _iso(info.st_mtime)


class _Source:
    """One source record; a failure becomes availability, never an exception."""

    def __init__(self, source_id: str, kind: str, label: str):
        self.record = {"id": source_id, "kind": kind, "path_label": label, "host": None, "schema": None,
                       "source_version": None, "generated_at": None, "generated_at_basis": "absent",
                       "generated_at_raw": None, "modified_at": None, "availability": "missing", "error": None}

    def fail(self, reason: str) -> None:
        self.record.update(availability="error", error=reason)

    def mark_available(self, version: str | None, mtime: str | None, schema: str | None = None,
                       generated: Any = None) -> None:
        stamp, basis, raw = _time(generated)
        self.record.update(availability="available", source_version=version, error=None, modified_at=mtime,
                           schema=schema, generated_at=stamp, generated_at_basis=basis, generated_at_raw=raw)
        if basis == "absent":
            self.record.update(generated_at=mtime, generated_at_basis="file_mtime")


def _measured() -> dict:
    return {"installed": None, "runtime_active": None, "connection_state": "unverified",
            "observed_at": None, "host": None, "evidence": None}


def _unknown_git() -> dict:
    return {"state": "unknown", "branch": None, "last_commit": None, "last_commit_raw": None, "observed_at": None,
            "observed_at_basis": "absent", "observed_at_raw": None, "host": None, "source": None}


def _item(item_id: str, item_type: str, name: str, source_id: str, **extra: Any) -> dict:
    base = {"id": item_id, "type": item_type, "aliases": [], "name": name, "description": None, "version": None,
            "category": None, "status": None, "visibility": None, "repository": None,
            "pin": {"commit": None, "content_hash": None, "source_version": None, "verified": None},
            "provides": [], "requires": [], "optional": [], "relations": [], "measured": _measured(),
            "git": _unknown_git(), "git_hosts": [], "source_ids": [source_id]}
    base.update(extra)
    return base


def _requirement(value: Any) -> str | None:
    return value if value in ("required", "recommended", "optional") else None


def _redact(node: Any, counter: list[int]) -> Any:
    if isinstance(node, str):
        for pattern in _PATH_PATTERNS:
            node, n = pattern.subn(REDACTED, node)
            counter[0] += n
        return node
    if isinstance(node, list):
        return [_redact(x, counter) for x in node]
    if isinstance(node, dict):
        return {k: _redact(v, counter) for k, v in node.items()}
    return node


def _load_install(workspace: Path, sources: list[dict]) -> tuple[dict, dict]:
    """Return (transaction, plan); empty dicts when the install state is unusable."""
    src = _Source("ocean_install_state", "composition", "<workspace>/" + INSTALL_STATE)
    sources.append(src.record)
    path = _child(workspace, INSTALL_STATE)
    if path is None:
        src.fail("unsafe_path")
        return {}, {}
    try:
        raw, mtime = _read_bytes(path, workspace)
        data = json.loads(raw.decode("utf-8-sig"))
    except FileNotFoundError:
        src.record["error"] = "file_missing"
        return {}, {}
    except (OSError, ValueError, UnicodeError) as exc:
        src.fail(type(exc).__name__)
        return {}, {}
    plan = _dict(_dict(data).get("plan"))
    transaction = _dict(plan.get("transaction"))
    if _dict(data).get("schema") != "ellmos.open-ocean-install-state.v1" or not isinstance(transaction.get("components"), list):
        src.fail("install_state_unsupported")
        return {}, {}
    src.mark_available(hashlib.sha256(raw).hexdigest(), mtime, _text(data.get("schema"), 120), data.get("recorded_at"))
    return transaction, plan


def _present(workspace: Path, *segments: str) -> bool:
    path = _child(workspace, *segments)
    return bool(path and path.is_dir())


def _modules(transaction: dict, workspace: Path, stamp: str | None) -> list[dict]:
    fetch = {x.get("ref"): _dict(x) for x in _list(transaction.get("fetch")) if isinstance(x, dict)}
    items = []
    for comp in _list(transaction.get("components")):
        comp = _dict(comp)
        ref = _text(comp.get("ref"), 300)
        if comp.get("kind") != "module" or not ref or not ref.startswith("module:"):
            continue
        detail = _dict(comp.get("detail"))
        binding = _dict(detail.get("binding"))
        module_id = _text(binding.get("placement_id") or detail.get("catalog_id") or ref.split(":", 1)[1], 200)
        if not module_id:
            continue
        fetched = _dict(fetch.get(ref))
        item = _item(module_id, "module", _text(detail.get("catalog_id"), 200) or module_id, "ocean_install_state",
                     category=_text(detail.get("kind"), 100), status=_text(comp.get("status"), 80),
                     visibility=_text(detail.get("visibility"), 80), repository=_text(detail.get("repository"), 300),
                     provides=_strings(detail.get("provides")), requires=_strings(detail.get("requires")))
        item["version"] = _text(detail.get("version"), 100)
        item["pin"]["commit"] = _text(_dict(fetched.get("detail")).get("sha") or binding.get("commit")
                                      or detail.get("source_commit"), 80)
        item["pin"]["content_hash"] = _text(detail.get("archive_sha256"), 100)
        item["relations"] = [{"kind": "requires", "target": t, "target_type": "capability",
                              "requirement": "required", "basis": "declared"} for t in item["requires"]]
        item["measured"].update(installed=_present(workspace, "modules", module_id), observed_at=stamp,
                                connection_state="unverified", evidence="install_state+directory")
        items.append(item)
    return items


def _bundles(transaction: dict) -> list[dict]:
    components = [_dict(c) for c in _list(transaction.get("components"))]
    results = [_dict(r) for r in _list(_dict(transaction.get("verify")).get("results"))]
    items = []
    for result in results:
        bundle_id = _text(result.get("bundle_ref"), 200)
        if not bundle_id:
            continue
        ok = result.get("ok")
        item = _item(bundle_id, "bundle", bundle_id, "ocean_install_state",
                     status="verified" if ok is True else "unverified")
        item["pin"]["content_hash"] = _text(result.get("pinned_hash"), 100)
        item["pin"]["verified"] = ok if isinstance(ok, bool) else None
        for comp in components:
            if bundle_id in _strings(comp.get("from_bundles")) and _text(comp.get("ref"), 300):
                item["relations"].append({"kind": "contains", "target": comp["ref"],
                                          "target_type": _text(comp.get("kind"), 40) or "unknown",
                                          "requirement": _requirement(comp.get("requirement")), "basis": "declared"})
        items.append(item)
    return items


def _stacks(transaction: dict, plan: dict) -> list[dict]:
    composition = _dict(plan.get("composition")) or _dict(transaction.get("composition"))
    comp_id = _text(composition.get("id"), 200)
    if not comp_id or not SAFE_SEGMENT.fullmatch(comp_id):
        return []
    item = _item("systems/" + comp_id, "stack", comp_id, "ocean_install_state", category="composition",
                 status="installed", aliases=[comp_id])
    item["relations"] = [{"kind": "contains", "target": r["bundle_ref"], "target_type": "bundle",
                          "requirement": "required", "basis": "declared"}
                         for r in (_dict(x) for x in _list(_dict(transaction.get("verify")).get("results")))
                         if _text(r.get("bundle_ref"), 200)]
    return [item]


def _frontmatter_description(raw: bytes) -> str | None:
    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:60]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        if key.strip() == "description":
            return _text(value.strip().strip("'\""), 2000)
    return None


def _skills(transaction: dict, workspace: Path, sources: list[dict], stamp: str | None) -> list[dict]:
    src = _Source("ocean_skills_dir", "skill", "<workspace>/skills")
    sources.append(src.record)
    root = _child(workspace, "skills")
    if root is None or not root.is_dir():
        return []
    src.mark_available(None, _iso(root.stat().st_mtime))
    items = []
    for entry in _list(transaction.get("activate")):
        entry = _dict(entry)
        name = _text(entry.get("skill_name"), 200)
        if not name or not SAFE_SEGMENT.fullmatch(name):
            continue
        item = _item(name, "skill", name, "ocean_install_state", status=_text(entry.get("action"), 80))
        item["source_ids"].append(src.record["id"])
        item["path_label"] = "skills/" + name
        skill_file = _child(workspace, "skills", name, "SKILL.md")
        installed = bool(skill_file and skill_file.is_file())
        if installed:
            try:
                raw, _ = _read_bytes(skill_file, workspace, 64 * 1024)
                item["description"] = _frontmatter_description(raw)
            except (OSError, ValueError):
                installed = False
        item["measured"].update(installed=installed, observed_at=stamp, evidence="install_state+directory")
        items.append(item)
    return items


@functools.cache  # the running code does not change commit under a live process
def _code_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else None


def _origin(workspace: Path) -> dict:
    """Where this answer comes from: code commit and runtime instance (never the control channel)."""
    instance = None
    path = _child(workspace, RUNTIME_STATE)
    if path and path.is_file():
        try:
            raw, _ = _read_bytes(path, workspace, 1024 * 1024)
            instance = _text(_dict(json.loads(raw.decode("utf-8-sig"))).get("instance_id"), 80)
        except (OSError, ValueError, UnicodeError):
            instance = None
    return {"provider": "open-ocean", "code_commit": _code_commit(), "instance_id": instance,
            "workspace_label": "<workspace>"}


def _guard(sources: list[dict], source_id: str, kind: str, fn, default):
    try:
        return fn()
    except Exception as exc:  # one broken source must not stop the others
        if not any(s["id"] == source_id for s in sources):
            record = _Source(source_id, kind, "<workspace>/" + source_id).record
            sources.append(record)
        for s in sources:
            if s["id"] == source_id:
                s.update(availability="error", error=type(exc).__name__)
        return default


def observe(*, workspace: Path, kind: str | None = None, host: str | None = None,
            now: datetime | None = None) -> dict:
    if kind is not None and kind not in KINDS:
        raise ValueError("unsupported_kind")
    workspace = Path(workspace)
    local_host = _text(host, 80) or platform.node() or None
    sources: list[dict] = []
    errors: list[dict] = []
    transaction, plan = _guard(sources, "ocean_install_state", "composition",
                               lambda: _load_install(workspace, sources), ({}, {}))
    stamp = next((s["generated_at"] for s in sources if s["id"] == "ocean_install_state"), None)
    items: list[dict] = []
    if kind in (None, "module"):
        items += _guard(sources, "ocean_install_state", "composition", lambda: _modules(transaction, workspace, stamp), [])
    if kind in (None, "bundle"):
        items += _guard(sources, "ocean_install_state", "composition", lambda: _bundles(transaction), [])
    if kind in (None, "stack"):
        items += _guard(sources, "ocean_install_state", "composition", lambda: _stacks(transaction, plan), [])
    if kind in (None, "skill"):
        items += _guard(sources, "ocean_skills_dir", "skill", lambda: _skills(transaction, workspace, sources, stamp), [])
    if kind in (None, "satellite"):
        sources.append(_Source("satellite_catalog", "satellite", "none (no OCEAN source)").record)
    for source in sources:
        if source["availability"] == "error":
            errors.append({"source": source["id"], "reason": source["error"], "item": None})
    truncated = len(items) > MAX_ITEMS
    items = items[:MAX_ITEMS]
    counts = {name: sum(1 for i in items if i["type"] == name) for name in KINDS if kind in (None, name)}
    result = {"schema": SCHEMA, "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
              "host": {"id": local_host, "source": "declared" if host else "measured"},
              "sources": sources, "items": items, "counts": counts, "count": len(items),
              "errors": errors, "truncated": truncated,
              "architecture": {"basis": "declared", "source_id": "none", "available": False, "areas": [], "edges": [],
                               "layers": [], "icons": {}, "ui": {}, "edges_note": None},
              "origin": _origin(workspace)}
    counter = [0]
    result = _redact(result, counter)
    result["redactions"] = counter[0]
    return result
