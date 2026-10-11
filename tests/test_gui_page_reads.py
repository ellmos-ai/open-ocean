"""Page status from the GUI's page-reads manifest (ellmos-system-gui#35): derivation, strictness, parity; no service."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import tools.gui_bridge as gui_bridge
from tools.gui_bridge import GuiBridge, PAGE_ROUTES
from tools.gui_page_reads import MAX_BYTES, load, normalize, pages_status
from tools.gui_release import INSTALLED_ARCHIVE, RECEIPT, verify_gui_archive, verify_installed_gui

FIXTURE = Path(__file__).parent / "fixtures" / "gui-page-reads.v1.f6696e5.json"  # ellmos-system-gui#35 @f6696e5
REAL = FIXTURE.read_bytes()
MEMBER = "dist/page-reads.v1.json"


class _Gui:  # stand-in for a verified release: the bridge only reads source_commit, archive_sha256, payload
    source_commit, archive_sha256, installed_verified = "a" * 40, "b" * 64, True

    def __init__(self, manifest: bytes | None = REAL):
        self.payload = {} if manifest is None else {MEMBER: manifest}


def _manifest(pages, layout=()):
    return json.dumps({"schema": "ellmos.gui.page-reads.v1", "layout": list(layout), "pages": pages}).encode()


def _entry(method, path, required=False):
    return {"method": method, "path": path, "required": required}


def _pages(bridge):
    return {p["id"]: p for p in bridge.capabilities()["pages"]}


def _full_bridge(gui):
    return GuiBridge(gui=gui, ocean=lambda: {}, skills=lambda: {}, catalog=lambda **kw: {}, policies=lambda **kw: {})


def test_the_hand_table_is_gone_and_the_manifest_decides():
    assert not hasattr(gui_bridge, "PAGE_REQUIRES")
    caps = _full_bridge(_Gui()).capabilities()
    assert caps["page_reads"]["state"] == "available" and caps["page_reads"]["sha256"] == hashlib.sha256(REAL).hexdigest()
    configured = {p["id"] for p in caps["pages"] if p["status"] == "configured"}
    # skills + ocean: their board inventory is the only required read and Ocean serves it; fabrika/funk/user-inbox
    # are pages without a backend call (empty list in the manifest); everything else lacks a required read.
    assert configured == {"skills", "ocean", "fabrika", "funk", "user-inbox"}
    for page in caps["pages"]:
        assert all(item.startswith("GET ") for item in page["requires"]), page["id"]
        assert not set(page["requires"]) & set(page["optional_unserved"])
    assert len(caps["pages"]) == len(json.loads(REAL)["pages"])  # user-inbox is not in PAGE_ROUTES but in the manifest


def test_parity_with_the_former_hand_entries_and_the_documented_differences():
    legacy = {"overview": ["GET /api/gui/capabilities"], "ocean": ["GET /api/capabilities/ocean"],
              "skills": ["GET /api/gui/capabilities", "GET /api/capabilities/skills/library", "GET /api/skills-board/hierarchy",
                         "PUT /api/skills-board/hierarchy", "GET /api/capabilities/skills/{id}/source",
                         "GET /api/capabilities/skills/{id}/history", "GET /api/capabilities/skills/{id}/history/{revision}",
                         "PUT /api/capabilities/skills/{id}/source"],
              "software": ["GET /api/capabilities/software"]}
    bridge = _full_bridge(_Gui())
    caps = bridge.capabilities()
    served = {f"{e['method']} {e['path']}": e["available"] for e in caps["endpoints"]}
    derived = {p["id"]: p for p in caps["pages"]}
    def status(ident):
        return "configured" if all(served.get(r) for r in legacy[ident]) else "unavailable"
    # identical where the page reads exactly one inventory
    for ident in ("ocean", "software"):
        assert derived[ident]["requires"] == legacy[ident] and derived[ident]["status"] == status(ident)
    # skills: the former table also demanded the optional assignment/history/source reads and PUTs -> now only the
    # required inventory decides, the rest is reported as unserved (contract: required + GET only)
    assert status("skills") == "unavailable" and derived["skills"]["status"] == "configured"
    assert derived["skills"]["requires"] == ["GET /api/capabilities/skills/library"]
    assert {"GET /api/skills-board/hierarchy", "GET /api/capabilities/skills/{id}/source"} <= set(derived["skills"]["optional_unserved"])
    # overview: the hand entry was a guess (capabilities); the dashboard really needs blueprints and tasks
    assert status("overview") == "configured" and derived["overview"]["status"] == "unavailable"
    assert derived["overview"]["requires"] == ["GET /api/agent-studio/blueprints", "GET /api/tasks"]


def test_only_required_get_reads_decide_and_duplicates_merge():
    pages = {"/": [_entry("GET", "/api/capabilities/ocean", True), _entry("GET", "/api/capabilities/catalog"),
                   _entry("POST", "/api/tasks"), _entry("GET", "/api/never-served"), _entry("PUT", "/api/x/{id}")]}
    layout = [_entry("GET", "/api/gui/brand")]
    bridge = _full_bridge(_Gui(_manifest(pages, layout)))
    page = _pages(bridge)["overview"]
    assert page["status"] == "configured" and page["requires"] == ["GET /api/capabilities/ocean"] and page["missing"] == []
    assert page["optional_unserved"] == ["GET /api/never-served"]  # unserved optional reads never change the status
    # negative control: make the served GET required and the page flips; a required POST alone would not
    flipped = {"/": [_entry("GET", "/api/never-served", True)]}
    page = _pages(_full_bridge(_Gui(_manifest(flipped))))["overview"]
    assert page["status"] == "unavailable" and page["missing"] == ["GET /api/never-served"]
    # the same read declared twice (optional here, required there; other parameter name): required wins, listed once
    merged = {"/": [_entry("GET", "/api/capabilities/skills/{id}/source"), _entry("GET", "/api/capabilities/skills/{key}/source", True)]}
    page = _pages(_full_bridge(_Gui(_manifest(merged))))["overview"]
    assert page["requires"] == ["GET /api/capabilities/skills/{key}/source"] and page["optional_unserved"] == []
    assert page["status"] == "unavailable"


def test_parameter_names_do_not_matter_when_matching():
    info = {"state": "available", "reasons": [], "sha256": None,
            "pages": {"/a": {"required": ["GET /api/s/{snapshot_id}/x"], "optional": []}}}
    assert normalize("/api/s/{snapshot_id}/x") == normalize("/api/s/{id}/x") == "/api/s/{}/x"
    served = {"GET /api/s/{}/x": True}
    assert pages_status(info, {"a": "/a"}, served)[0]["status"] == "configured"
    assert pages_status(info, {"a": "/a"}, {"GET /api/s/{}/y": True})[0]["status"] == "unavailable"


def test_pages_missing_from_manifest_or_routes():
    manifest = _manifest({"/": [], "/neu/seite": []})
    pages = _pages(GuiBridge(gui=_Gui(manifest)))
    assert pages["overview"]["status"] == "configured" and pages["neu-seite"]["path"] == "/neu/seite"
    assert pages["tasks"]["status"] == "unavailable" and pages["tasks"]["missing"] == ["page-not-in-manifest"]
    assert set(PAGE_ROUTES) <= set(pages)


def test_no_release_or_no_manifest_member_means_every_page_unavailable_with_the_reason():
    for gui, reasons in ((None, ["verified-gui-release", "page-reads-manifest-missing"]), (_Gui(None), ["page-reads-manifest-missing"])):
        caps = GuiBridge(gui=gui, ocean=lambda: {}).capabilities()
        assert caps["page_reads"]["state"] == "missing" and caps["page_reads"]["reasons"] == reasons
        assert caps["pages"] and all(p["status"] == "unavailable" and p["missing"] == reasons for p in caps["pages"])


BAD = {
    "wrong-schema": json.dumps({"schema": "x", "pages": {"/": []}}).encode(),
    "not-json": b"{nope",
    "bom": b"\xef\xbb\xbf" + REAL,
    "latin1": REAL.replace(b'"note"', b'"n\xf6te"', 1),
    "nan": b'{"schema":"ellmos.gui.page-reads.v1","pages":{"/":[]},"x":NaN}',
    "duplicate-key": b'{"schema":"ellmos.gui.page-reads.v1","pages":{"/":[]},"pages":{"/":[]}}',
    "no-pages": _manifest({}),
    "pages-list": json.dumps({"schema": "ellmos.gui.page-reads.v1", "pages": []}).encode(),
    "bad-method": _manifest({"/": [_entry("GRAB", "/api/x", True)]}),
    "query-in-path": _manifest({"/": [_entry("GET", "/api/x?a=1", True)]}),
    "foreign-path": _manifest({"/": [_entry("GET", "/other/x", True)]}),
    "dotdot": _manifest({"/": [_entry("GET", "/api/../x", True)]}),
    "required-not-bool": _manifest({"/": [{"method": "GET", "path": "/api/x", "required": "yes"}]}),
    "entry-not-object": _manifest({"/": ["GET /api/x"]}),
    "layout-invalid": _manifest({"/": []}, layout=[{"method": "GET"}]),
    "page-without-slash": _manifest({"tasks": []}),
    "required-write": _manifest({"/": [_entry("POST", "/api/x", True)]}),
    "required-layout": _manifest({"/": []}, layout=[_entry("GET", "/api/gui/brand", True)]),
    "dynamic-without-found-in": _manifest({"/": [{**_entry("GET", "/api/x/{id}"), "dynamic": True}]}),
    "dynamic-bad-found-in": _manifest({"/": [{**_entry("GET", "/api/x/{id}"), "dynamic": True, "found_in": "no-function"}]}),
    "dynamic-not-bool": _manifest({"/": [{**_entry("GET", "/api/x/{id}"), "dynamic": "yes", "found_in": "a#b"}]}),
    "found-in-without-dynamic": _manifest({"/": [{**_entry("GET", "/api/x"), "found_in": "a#b"}]}),
    "query-not-string": _manifest({"/": [{**_entry("GET", "/api/x"), "query": ["a=1"]}]}),
    "too-large": b" " * (MAX_BYTES + 1),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_an_invalid_manifest_makes_every_page_unavailable(name):
    info = load(_Gui(BAD[name]))
    assert info["state"] == "invalid", name
    caps = GuiBridge(gui=_Gui(BAD[name])).capabilities()
    assert caps["page_reads"]["state"] == "invalid"
    assert all(p["status"] == "unavailable" and p["missing"] == ["page-reads-manifest-invalid"] for p in caps["pages"])


def test_the_real_manifest_is_valid_and_a_clean_negative_control_exists():
    assert load(_Gui())["state"] == "available"
    assert load(_Gui(b"{}"))["state"] == "invalid"


def _archive(manifest: bytes | None):
    files = {"index.html": b"<p>fixture</p>\n"}
    if manifest is not None:
        files["page-reads.v1.json"] = manifest
    commit = "c" * 40
    record = {"schema": "ellmos-system-gui.dist.v1", "source_commit": commit,
              "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("LICENSE", "MIT\n")
        archive.writestr("dist/dist-manifest.json", json.dumps(record))
        for name, data in files.items():
            archive.writestr("dist/" + name, data)
    return commit, buffer.getvalue()


def test_documented_optional_fields_stay_valid():
    manifest = _manifest({"/": [{**_entry("GET", "/api/x/{id}", True), "query": "a=1"},
                                {**_entry("PUT", "/api/x/{id}"), "dynamic": True, "found_in": "src/a.mjs#save"}]},
                         layout=[_entry("GET", "/api/gui/brand")])
    assert load(_Gui(manifest))["state"] == "available"
    merged = Path(__file__).parent / "fixtures" / "gui-page-reads.origin-main-920bcf63.json"  # merged ellmos-system-gui main
    assert load(_Gui(merged.read_bytes()))["state"] == "available"


def _place(root: Path, archive: Path, commit: str, digest: str):
    """What fetch_place does: payload files, receipt and the original archive side by side."""
    release = verify_gui_archive(archive, commit, digest)
    for name, data in release.payload.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / RECEIPT).write_text(json.dumps(release.receipt()), encoding="utf-8")
    (root / INSTALLED_ARCHIVE).write_bytes(release.archive_bytes)
    return verify_installed_gui(root, commit, digest)


def test_manifest_is_read_only_from_an_installed_verified_kit_not_from_an_archive(tmp_path):
    commit, raw = _archive(REAL)
    digest = hashlib.sha256(raw).hexdigest()
    path = tmp_path / "gui.zip"
    path.write_bytes(raw)
    archive_only = verify_gui_archive(path, commit, digest)
    assert archive_only.installed_verified is False
    caps = _full_bridge(archive_only).capabilities()
    assert caps["page_reads"]["state"] == "missing" and "gui-release-not-installed-verified" in caps["page_reads"]["reasons"]
    assert all(p["status"] == "unavailable" for p in caps["pages"])
    installed = _place(tmp_path / "kit", path, commit, digest)
    assert installed.installed_verified is True
    caps = _full_bridge(installed).capabilities()
    assert caps["page_reads"]["state"] == "available"
    assert {p["id"] for p in caps["pages"] if p["status"] == "configured"} >= {"skills", "ocean"}
    # a kit without the member (e.g. 0.2.18) leaves every page unavailable instead of falling back to a table
    commit, raw = _archive(None)
    digest = hashlib.sha256(raw).hexdigest()
    path.write_bytes(raw)
    old = _place(tmp_path / "oldkit", path, commit, digest)
    caps = _full_bridge(old).capabilities()
    assert caps["page_reads"]["reasons"] == ["page-reads-manifest-missing"]
    assert all(p["status"] == "unavailable" for p in caps["pages"])
    # tampering with the manifest byte breaks the release hash, so it can never reach the bridge
    commit, raw = _archive(REAL)
    path.write_bytes(raw.replace(b"/api/tasks", b"/api/tasKs", 1))
    with pytest.raises(Exception):
        verify_gui_archive(path, commit, hashlib.sha256(raw).hexdigest())
    # ... and so does a changed byte inside an installed kit
    target = tmp_path / "kit" / MEMBER
    target.write_bytes(target.read_bytes().replace(b"/api/tasks", b"/api/tasKs", 1))
    with pytest.raises(Exception):
        verify_installed_gui(tmp_path / "kit", commit, hashlib.sha256(_archive(REAL)[1]).hexdigest())
