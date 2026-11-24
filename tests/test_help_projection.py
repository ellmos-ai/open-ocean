"""Tests for Ocean core documentation and module manifest help projection (#2459, #2557)."""
from __future__ import annotations

import json
from pathlib import Path
from tools.help_projection import DOC_PRECEDENCE, SUPPORTED_HELP_LOCALES, project_installed_module_help

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def test_repo_root_has_skill_md_and_core_doc():
    root = Path(__file__).resolve().parents[1]
    assert (root / "SKILL.md").is_file()
    assert (root / "docs/CORE.md").is_file()
    proj = project_installed_module_help(root)
    assert proj["schema"] == "ellmos.open-ocean.help-projection.v1"
    assert proj["precedence"] == list(DOC_PRECEDENCE)
    assert proj["core_doc"] == "docs/CORE.md"
    assert proj["skill_doc"] == "SKILL.md"
    root_mods = [m for m in proj["modules"] if m["id"] == "open-ocean"]
    assert len(root_mods) == 1
    assert root_mods[0]["entry"] == "README.md"
    assert root_mods[0]["languages"] == ["de", "en", "es", "fr", "pt", "ru", "zh", "ja", "ar", "hi", "bn"]

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    data_files = pyproject["tool"]["setuptools"]["data-files"]
    assert "SKILL.md" in data_files["share/open-ocean"]
    packaged_docs = set(data_files["share/open-ocean/docs"])
    for lang in SUPPORTED_HELP_LOCALES:
        if lang != "de":
            assert f"docs/SKILL.{lang}.md" in packaged_docs


def test_project_installed_module_help_reads_manifest_docs(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/CORE.md").write_text("# Core", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("# Skill", encoding="utf-8")
    mod_dir = tmp_path / "modules" / "demo-mod"
    mod_dir.mkdir(parents=True)
    manifest = {
        "schema": "ellmos.module.v2",
        "id": "demo-mod",
        "version": "1.2.0",
        "surfaces": ["library", "cli", "ui"],
        "docs": {"entry": "docs/INDEX.md", "languages": ["de", "en", "es"]},
    }
    (mod_dir / "ellmos-module.v2.json").write_text(json.dumps(manifest), encoding="utf-8")
    proj = project_installed_module_help(tmp_path)
    assert len(proj["modules"]) == 1
    m = proj["modules"][0]
    assert m["id"] == "demo-mod"
    assert m["entry"] == "docs/INDEX.md"
    assert m["languages"] == ["de", "en", "es"]
