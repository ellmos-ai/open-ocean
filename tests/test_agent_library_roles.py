# -*- coding: utf-8 -*-
"""PB-10 (#3993): Agenten-Bibliothek vollständig.

Rollenquelle robust (Modulwurzeln, installierte Pakete, Herkunft je Rolle), Soll-Rollenliste als Datenquelle
(jede Soll-Rolle im Katalog ODER mit Ausnahmegrund) und Zählungen aus dem Katalog statt Festzahl in der GUI.
"""
from __future__ import annotations

import json
import os
from importlib import metadata
from pathlib import Path

from tools.agent_library import (
    MODULE_ROOTS_ENV,
    build_full_agent_library_catalog,
    _installed_manifest_paths,
    check_expected_roles,
    discover_module_role_templates,
    load_expected_roles,
)


def _write_manifest(folder: Path, module_id: str, role_ids: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ellmos-module.v2.json"
    path.write_text(
        json.dumps({"id": module_id, "roles": [{"id": r, "label": r.upper(), "prompt": f"p/{r}.md"} for r in role_ids]}),
        encoding="utf-8",
    )
    return path


def test_discovery_finds_modules_outside_sibling_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    siblings = tmp_path / "siblings"
    siblings.mkdir()
    other_root = tmp_path / "elsewhere"
    manifest = _write_manifest(other_root / "ticket-master", "ticket-master", ["ticket-master", "ticket-writer"])

    assert discover_module_role_templates(siblings) == []
    found = discover_module_role_templates(siblings, extra_roots=[other_root])

    assert {t["id"] for t in found} == {"ticket-master:ticket-master", "ticket-master:ticket-writer"}
    one = found[0]
    assert one["origin"] == "manifest"
    assert one["module_id"] == "ticket-master"
    assert one["manifest_path"] == "ticket-master/ellmos-module.v2.json"  # relativ zur Wurzel, kein Benutzerpfad
    assert manifest.is_file()
    assert one["source"] == "module_manifest_role"  # GUI-Vertrag (bibliothek.astro) bleibt unberührt


def test_discovery_reads_module_roots_from_environment(tmp_path: Path, monkeypatch) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _write_manifest(root_a / "m1", "m1", ["r1"])
    _write_manifest(root_b / "m2", "m2", ["r2"])
    monkeypatch.setenv(MODULE_ROOTS_ENV, f"{root_a}{__import__('os').pathsep}{root_b}")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert {t["id"] for t in discover_module_role_templates(empty)} == {"m1:r1", "m2:r2"}


def test_discovery_finds_manifest_shipped_in_installed_package(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    site = tmp_path / "site"
    _write_manifest(site / "modx", "modx", ["rx"])
    dist = site / "modx-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: modx\nVersion: 1.0\n", encoding="utf-8")
    (dist / "RECORD").write_text("modx/ellmos-module.v2.json,,\n", encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()

    assert discover_module_role_templates(empty, include_installed=False) == []
    found = discover_module_role_templates(empty, include_installed=True, dist_path=[str(site)])
    assert [t["id"] for t in found] == ["modx:rx"]
    assert found[0]["found_via"] == "installed"


def test_same_module_in_two_roots_is_listed_once_first_root_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    first, second = tmp_path / "first", tmp_path / "second"
    _write_manifest(first / "dup", "dup", ["r1"])
    _write_manifest(second / "dup", "dup", ["r1", "r2"])
    found = discover_module_role_templates(first, extra_roots=[second])
    assert [t["id"] for t in found] == ["dup:r1"]


def test_builtin_templates_carry_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    lib = build_full_agent_library_catalog(tmp_path)
    builtin = [t for t in lib["templates"] if t["id"].startswith("ocean-role:")]
    assert builtin and all(t["origin"] == "builtin" and t["module_id"] == "open-ocean" for t in builtin)


def test_every_expected_role_is_in_catalog_or_has_exception_reason(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    lib = build_full_agent_library_catalog(tmp_path)  # keine Module: nur Bordmittel
    report = check_expected_roles(lib["templates"], load_expected_roles(), found_modules=set())
    assert report["uncovered"] == [], f"Soll-Rollen ohne Katalogeintrag und ohne Ausnahmegrund: {report['uncovered']}"
    assert report["orphan_exceptions"] == []
    assert report["stale_exceptions"] == []
    doc = load_expected_roles()
    for exc in doc["exceptions"]:
        assert exc["reason"].strip(), exc["id"]
        assert exc["status"] == "Vorschlag, Nutzerbestätigung offen", exc["id"]


def test_expected_check_negative_control_flags_missing_role() -> None:
    doc = {
        "expected": [
            {"id": "ghost", "maps_to": "ocean-role:ghost"},
            {"id": "excused", "maps_to": "ocean-role:excused"},
            {"id": "later", "maps_to": "mod:later", "module": "mod"},
            {"id": "present", "maps_to": "ocean-role:present"},
        ],
        "exceptions": [{"id": "excused", "reason": "kein Modul", "status": "Vorschlag, Nutzerbestätigung offen"}],
    }
    report = check_expected_roles([{"id": "ocean-role:present"}], doc, found_modules=set())
    assert report["uncovered"] == ["ghost"]
    assert report["excepted"] == ["excused"]
    assert report["module_pending"] == ["later"]
    assert report["covered"] == ["present"]
    # Modul installiert, Rolle fehlt im Manifest -> kein "pending", sondern echte Lücke
    assert check_expected_roles([{"id": "ocean-role:present"}], doc, found_modules={"mod"})["uncovered"] == ["ghost", "later"]


def test_module_owned_expected_role_is_covered_once_module_is_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    _write_manifest(tmp_path / "ticket-master", "ticket-master", ["ticket-master", "ticket-writer"])
    lib = build_full_agent_library_catalog(tmp_path)
    report = lib["expected_roles"]
    assert "ticket-master" in report["covered"]
    assert "ticket-master" not in report["module_pending"]


def test_counts_are_derived_from_catalog_not_fixed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    _write_manifest(tmp_path / "m1", "m1", ["a", "b"])
    _write_manifest(tmp_path / "m2", "m2", ["c"])
    lib = build_full_agent_library_catalog(tmp_path)
    counts = lib["counts"]
    ocean = [t for t in lib["templates"] if t["origin"] == "builtin"]
    mods = [t for t in lib["templates"] if t["origin"] == "manifest"]
    assert counts["ocean_roles"] == len(ocean) == 13
    assert counts["module_roles"] == len(mods) == 3
    assert counts["modules"] == 2
    assert counts["templates"] == len(lib["templates"])
    assert counts["exceptions"] == len(lib["role_exceptions"]) > 0
    assert all(e["origin"] == "legacy" for e in lib["role_exceptions"])


def _fake_site(site: Path, module: str, n_files: int = 3000) -> Path:
    """Fake-Distribution mit vielen RECORD-Einträgen (nicht vorhanden) und einem Manifest."""
    _write_manifest(site / module, module, ["r"])
    dist = site / f"{module}-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {module}\nVersion: 1.0\n", encoding="utf-8")
    lines = [f"{module}/gen/f{i}.py,," for i in range(n_files)] + [f"{module}/ellmos-module.v2.json,,"]
    (dist / "RECORD").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dist


def test_installed_scan_reads_record_without_per_file_stat(tmp_path: Path, monkeypatch) -> None:
    site = tmp_path / "site"
    _fake_site(site, "bigmod")

    def boom(self):
        raise AssertionError("Distribution.files stattet jede installierte Datei (Python >= 3.12)")

    monkeypatch.setattr(metadata.Distribution, "files", property(boom))
    found = _installed_manifest_paths([str(site)])
    assert [p.name for p in found] == ["ellmos-module.v2.json"]


def test_installed_scan_is_cached_per_process_and_invalidated_by_site_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    site = tmp_path / "site"
    site.mkdir()
    _fake_site(site, "moda")
    empty = tmp_path / "empty"
    empty.mkdir()
    reads: list[str] = []
    orig = metadata.PathDistribution.read_text

    def counting(self, filename):
        reads.append(filename)
        return orig(self, filename)

    monkeypatch.setattr(metadata.PathDistribution, "read_text", counting)

    first = build_full_agent_library_catalog(empty, include_installed=True, dist_path=[str(site)])
    assert reads.count("RECORD") == 1, "höchstens ein Scan je Anfrage"
    second = build_full_agent_library_catalog(empty, include_installed=True, dist_path=[str(site)])
    assert reads.count("RECORD") == 1, "zweite Anfrage nutzt den Prozess-Cache"
    assert first["counts"]["module_roles"] == second["counts"]["module_roles"] == 1

    _fake_site(site, "modb")  # neue Distribution -> mtime der Site-Wurzel ändert sich
    st = os.stat(site)
    os.utime(site, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    third = build_full_agent_library_catalog(empty, include_installed=True, dist_path=[str(site)])
    assert third["counts"]["module_roles"] == 2


def test_api_payload_has_no_absolute_local_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODULE_ROOTS_ENV, raising=False)
    root = tmp_path / "home" / "someone" / "services"
    _write_manifest(root / "m1", "m1", ["a"])
    site = tmp_path / "site"
    site.mkdir()
    _fake_site(site, "modx")
    lib = build_full_agent_library_catalog(root, include_installed=True, dist_path=[str(site)])
    blob = json.dumps(lib, ensure_ascii=False)
    assert str(tmp_path) not in blob and tmp_path.as_posix() not in blob and "someone" not in blob
    paths = {m["module_id"]: m["path"] for m in lib["module_manifests"]}
    assert paths["m1"] == "m1/ellmos-module.v2.json"
    assert paths["modx"] == "modx/ellmos-module.v2.json"
