"""Tests for Ocean core documentation and module manifest help projection (#2459, #2557)."""
from __future__ import annotations

import json
from pathlib import Path
from tools.help_projection import DOC_PRECEDENCE, extract_manifest_docs, project_installed_module_help


def test_repo_root_has_skill_md_and_core_doc():
    root = Path(__file__).resolve().parents[1]
    assert (root / "SKILL.md").is_file()
    assert (root / "docs/CORE.md").is_file()
    proj = project_installed_module_help(root)
    assert proj["schema"] == "ellmos.open-ocean.help-projection.v1"
    assert proj["precedence"] == list(DOC_PRECEDENCE)
    assert proj["core_doc"] == "docs/CORE.md"
    assert proj["skill_doc"] == "SKILL.md"


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
