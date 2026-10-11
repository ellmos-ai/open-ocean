# SPDX-License-Identifier: MIT
"""Page status derived from the GUI's own page-reads manifest (ellmos.gui.page-reads.v1).

The manifest ships inside the verified GUI release (dist/page-reads.v1.json, hashed in the dist manifest), so the
page-to-endpoint table is never maintained by hand here. A page is `configured` only when the verified release
brings the manifest and every `required` GET read of that page is served by an Ocean route. Optional reads, layout
reads and any write call never change a page status (docs/CONSUMER_CONTRACT.md of ellmos-system-gui).
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping

MEMBER = "dist/page-reads.v1.json"
SCHEMA = "ellmos.gui.page-reads.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 200
MAX_ENTRIES = 500
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
PATH = re.compile(r"/api/[A-Za-z0-9_.~{}/-]*")


class PageReadsError(ValueError):
    pass


def normalize(path: str) -> str:
    """Parameter names do not matter when matching: /a/{id}/b == /a/{key}/b."""
    return re.sub(r"\{[^{}/]*\}", "{}", path)


def _unique(pairs):
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PageReadsError("duplicate key")
        result[key] = value
    return result


FOUND_IN = re.compile(r"[^#\s]+#[^#\s]+")


def _entries(value: Any, where: str, *, layout: bool = False) -> list[dict]:
    if not isinstance(value, list) or len(value) > MAX_ENTRIES:
        raise PageReadsError(f"{where}: entries are not a bounded list")
    for entry in value:
        if not (isinstance(entry, dict) and entry.get("method") in METHODS and isinstance(entry.get("path"), str)
                and PATH.fullmatch(entry["path"]) and ".." not in entry["path"] and isinstance(entry.get("required"), bool)
                and isinstance(entry.get("dynamic", False), bool)):
            raise PageReadsError(f"{where}: invalid entry")
        # documented field rules (ellmos-system-gui docs/CONSUMER_CONTRACT.md, "Seiten-Lesepfade")
        if "query" in entry and not isinstance(entry["query"], str):
            raise PageReadsError(f"{where}: query must be a string")
        if entry.get("dynamic", False) != ("found_in" in entry) or (
                "found_in" in entry and not (isinstance(entry["found_in"], str) and FOUND_IN.fullmatch(entry["found_in"]))):
            raise PageReadsError(f"{where}: dynamic needs a found_in of the form file#function, and only dynamic has one")
        if entry["required"] and (layout or entry["method"] != "GET"):
            raise PageReadsError(f"{where}: layout reads and write calls cannot be required")
    return value


def load(gui: Any) -> dict:
    """-> {state: available|missing|invalid, reasons: [...], sha256, pages: {path: {required: [...], optional: [...]}}}"""
    if gui is None:
        return {"state": "missing", "reasons": ["verified-gui-release", "page-reads-manifest-missing"], "sha256": None, "pages": {}}
    if getattr(gui, "installed_verified", False) is not True:
        # an archive that was only verified is not an installed kit: its manifest says nothing about what is served
        return {"state": "missing", "reasons": ["gui-release-not-installed-verified", "page-reads-manifest-missing"], "sha256": None, "pages": {}}
    payload = getattr(gui, "payload", None)
    raw = payload.get(MEMBER) if isinstance(payload, Mapping) else None
    if raw is None:
        return {"state": "missing", "reasons": ["page-reads-manifest-missing"], "sha256": None, "pages": {}}
    invalid = {"state": "invalid", "reasons": ["page-reads-manifest-invalid"], "sha256": None, "pages": {}}
    try:
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
            raise PageReadsError("size")
        document = json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(PageReadsError("constant")))
        if not (isinstance(document, dict) and document.get("schema") == SCHEMA and isinstance(document.get("pages"), dict)
                and 0 < len(document["pages"]) <= MAX_PAGES):
            raise PageReadsError("schema")
        _entries(document.get("layout", []), "layout", layout=True)
        pages: dict[str, dict] = {}
        for page, entries in document["pages"].items():
            if not (isinstance(page, str) and page.startswith("/") and len(page) <= 200):
                raise PageReadsError("page path")
            required: dict[str, str] = {}
            optional: dict[str, str] = {}
            for entry in _entries(entries, page):
                if entry["method"] != "GET":
                    continue  # writes never decide a page status
                (required if entry["required"] else optional).setdefault(normalize(entry["path"]), "GET " + entry["path"])
            pages[page] = {"required": list(required.values()),
                           "optional": [text for key, text in optional.items() if key not in required]}
    except (PageReadsError, UnicodeError, ValueError, TypeError, RecursionError):
        return {**invalid, "sha256": sha256(raw).hexdigest() if isinstance(raw, (bytes, bytearray)) else None}
    return {"state": "available", "reasons": [], "sha256": sha256(raw).hexdigest(), "pages": pages}


def page_id(path: str, known: Mapping[str, str]) -> str:
    return known.get(path) or (path.strip("/").replace("/", "-") or "overview")


def pages_status(info: dict, routes: Mapping[str, str], served: Mapping[str, bool]) -> list[dict]:
    """routes: id -> path. served: 'METHOD /normalized/path' -> bool."""
    by_path = {path: ident for ident, path in routes.items()}
    order = list(routes.items()) + [(page_id(path, by_path), path) for path in info["pages"] if path not in by_path]
    out = []
    for ident, path in order:
        page = info["pages"].get(path)
        if info["state"] != "available":
            required, missing, optional = [], list(info["reasons"]), []
        elif page is None:
            required, missing, optional = [], ["page-not-in-manifest"], []
        else:
            required = list(page["required"])
            missing = [item for item in required if not served.get(_key(item))]
            optional = [item for item in page["optional"] if not served.get(_key(item))]
        out.append({"id": ident, "path": path, "status": "configured" if not missing else "unavailable",
                    "requires": required, "missing": missing, "optional_unserved": optional,
                    "todo": [] if not missing else ["Native Seiten- und Widgetadapter mit Laufzeitbeleg ergänzen."]})
    return out


def _key(item: str) -> str:
    method, _, path = item.partition(" ")
    return f"{method} {normalize(path)}"
