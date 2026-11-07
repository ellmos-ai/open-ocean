# -*- coding: utf-8 -*-
"""PB-10 (#3993): Agenten-Bibliothek vollständig.

Rollenquelle robust (Modulwurzeln, installierte Pakete, Herkunft je Rolle), Soll-Rollenliste als Datenquelle
(jede Soll-Rolle im Katalog ODER mit Ausnahmegrund) und Zählungen aus dem Katalog statt Festzahl in der GUI.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.agent_library import (
    MODULE_ROOTS_ENV,
    build_full_agent_library_catalog,
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
    assert Path(one["manifest_path"]) == manifest
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
