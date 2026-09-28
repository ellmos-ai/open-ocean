"""Tests for tools/project_workflows.py -- S8 Skills- and Workflow-Projection.

Uses synthetic fixtures throughout, matching the style of test_resolve_bundles.py.
Ensures no real OneDrive or network access.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.project_workflows import (
    ProjectWorkflowsError,
    load_modules_from_catalog,
    load_skills_from_registry,
    load_toolchains_from_db,
    main,
    project_bundle_components,
    project_workflows,
    render_modules_markdown,
    render_skills_markdown,
    render_toolchains_markdown,
)
from tools.resolve_bundles import ResolvedComponent


class ProjectWorkflowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output_dir = self.root / "output"
        self.skills_path = self.root / "skills.registry.json"
        self.catalog_path = self.root / "modules.catalog.json"
        self.toolchains_path = self.root / "toolchains.json"

        # Local directory to satisfy present_locally for module:USMC
        (self.root / "USMC").mkdir(parents=True)

        self.skills_data = {
            "components": [
                {
                    "id": "skill:dev:decide",
                    "name": "decide",
                    "category": "utilities",
                    "status": "active",
                    "path": "utilities/decide/SKILL.md",
                    "requirement": "recommended",
                    "bundles": ["core-bundle"],
                },
                {
                    "id": "skill:dev:brainstorm",
                    "name": "brainstorm",
                    "category": "utilities",
                    "status": "active",
                    "path": "utilities/brainstorm/SKILL.md",
                    "requirement": "optional",
                    "bundles": ["optional-bundle"],
                },
            ]
        }
        self.skills_path.write_text(json.dumps(self.skills_data), encoding="utf-8")

        self.catalog_data = {
            "modules": [
                {
                    "id": "USMC",
                    "source_of_truth": {
                        "type": "git-repository",
                        "repository": "https://github.com/ellmos-ai/usmc.git",
                    },
                    "resolved_source": "USMC",
                    "visibility": "public",
                    "kind": "library",
                    "requirement": "required",
                    "bundles": ["core-bundle"],
                },
                {
                    "id": "UnresolvedModule",
                    "source_of_truth": {
                        "type": "git-repository",
                        "repository": "https://github.com/ellmos-ai/unresolved.git",
                    },
                    "resolved_source": "non-existent-source-path",
                    "visibility": "private",
                    "kind": "service",
                    "requirement": "unspecified",
                },
            ]
        }
        self.catalog_path.write_text(json.dumps(self.catalog_data), encoding="utf-8")

        self.toolchains_data = {
            "toolchains": [
                {
                    "id": "chain-sync",
                    "name": "Daily Sync Chain",
                    "description": "Runs daily sync procedures",
                    "trigger_type": "cron: 0 8 * * *",
                    "is_active": True,
                    "steps": [
                        {"name": "fetch", "action": "fetch_data"},
                        {"name": "process", "action": "run_processor"},
                    ],
                },
                {
                    "id": "chain-cleanup",
                    "name": "Weekly Cleanup",
                    "description": "Purges temporary artifacts",
                    "trigger_type": "manual",
                    "is_active": False,
                    "steps": ["step1", "step2"],
                },
            ]
        }
        self.toolchains_path.write_text(json.dumps(self.toolchains_data), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_load_skills_from_registry(self):
        skills, raw = load_skills_from_registry(self.skills_path)
        self.assertEqual(len(skills), 2)
        refs = [s.ref for s in skills]
        self.assertEqual(refs, ["skill:brainstorm", "skill:decide"])
        self.assertEqual(skills[1].status, "resolved")
        self.assertEqual(skills[1].detail["category"], "utilities")
        self.assertEqual(skills[1].detail["registry_id"], "skill:dev:decide")

    def test_load_modules_from_catalog(self):
        modules, raw = load_modules_from_catalog(self.catalog_path)
        self.assertEqual(len(modules), 2)
        refs = [m.ref for m in modules]
        self.assertEqual(refs, ["module:USMC", "module:UnresolvedModule"])
        self.assertEqual(modules[0].status, "resolved")
        self.assertEqual(modules[0].detail["repository"], "https://github.com/ellmos-ai/usmc.git")
        self.assertEqual(modules[1].status, "unresolved")

    def test_load_toolchains_from_db(self):
        toolchains, raw = load_toolchains_from_db(self.toolchains_path)
        self.assertEqual(len(toolchains), 2)
        ids = [t["id"] for t in toolchains]
        self.assertEqual(ids, ["chain-cleanup", "chain-sync"])

    def test_project_workflows_without_toolchains(self):
        result = project_workflows(
            skills_registry=self.skills_path,
            modules_catalog=self.catalog_path,
            db_path=None,
            output_dir=self.output_dir,
            include_toolchains=False,
        )

        skills_file = self.output_dir / "SKILLS.md"
        modules_file = self.output_dir / "MODULES.md"
        toolchains_file = self.output_dir / "TOOLCHAINS.md"

        self.assertTrue(skills_file.is_file())
        self.assertTrue(modules_file.is_file())
        self.assertFalse(toolchains_file.exists())

        skills_content = skills_file.read_text(encoding="utf-8")
        self.assertIn("skill:decide", skills_content)
        self.assertIn("skill:brainstorm", skills_content)
        self.assertIn("resolved", skills_content)
        self.assertIn("utilities", skills_content)
        self.assertIn("core-bundle", skills_content)

        modules_content = modules_file.read_text(encoding="utf-8")
        self.assertIn("module:USMC", modules_content)
        self.assertIn("module:UnresolvedModule", modules_content)
        self.assertIn("resolved", modules_content)
        self.assertIn("unresolved", modules_content)
        self.assertIn("https://github.com/ellmos-ai/usmc.git", modules_content)

        self.assertEqual(len(result["written_files"]), 2)

    def test_project_workflows_with_toolchains(self):
        result = project_workflows(
            skills_registry=self.skills_path,
            modules_catalog=self.catalog_path,
            db_path=self.toolchains_path,
            output_dir=self.output_dir,
            include_toolchains=True,
        )

        toolchains_file = self.output_dir / "TOOLCHAINS.md"
        self.assertTrue(toolchains_file.is_file())

        content = toolchains_file.read_text(encoding="utf-8")
        self.assertIn("chain-sync", content)
        self.assertIn("Daily Sync Chain", content)
        self.assertIn("cron: 0 8 * * *", content)
        self.assertIn("chain-cleanup", content)
        self.assertIn("Weekly Cleanup", content)
        self.assertIn("active", content)
        self.assertIn("inactive", content)

        self.assertEqual(len(result["written_files"]), 3)

    def test_include_toolchains_requires_db_path(self):
        with self.assertRaises(ProjectWorkflowsError):
            project_workflows(
                skills_registry=self.skills_path,
                modules_catalog=self.catalog_path,
                db_path=None,
                output_dir=self.output_dir,
                include_toolchains=True,
            )

    def test_missing_files_fail_closed(self):
        missing = self.root / "missing.json"
        with self.assertRaises(ProjectWorkflowsError):
            project_workflows(
                skills_registry=missing,
                modules_catalog=self.catalog_path,
                output_dir=self.output_dir,
            )
        with self.assertRaises(ProjectWorkflowsError):
            project_workflows(
                skills_registry=self.skills_path,
                modules_catalog=missing,
                output_dir=self.output_dir,
            )

    def test_main_cli_execution_success(self):
        code = main([
            "--skills-registry", str(self.skills_path),
            "--modules-catalog", str(self.catalog_path),
            "--db-path", str(self.toolchains_path),
            "--output-dir", str(self.output_dir),
            "--include-toolchains",
        ])
        self.assertEqual(code, 0)
        self.assertTrue((self.output_dir / "SKILLS.md").is_file())
        self.assertTrue((self.output_dir / "MODULES.md").is_file())
        self.assertTrue((self.output_dir / "TOOLCHAINS.md").is_file())

    def test_main_cli_execution_error(self):
        code = main([
            "--skills-registry", str(self.root / "nonexistent.json"),
            "--modules-catalog", str(self.catalog_path),
            "--output-dir", str(self.output_dir),
        ])
        self.assertEqual(code, 2)

    def test_renderers_direct_output(self):
        skill = ResolvedComponent(
            ref="skill:custom",
            kind="skill",
            requirement="required",
            from_bundles=["bundle-x"],
            status="resolved",
            detail={"registry_id": "skill:custom-id", "category": "dev", "path": "skills/custom/SKILL.md"},
        )
        rendered_skills = render_skills_markdown([skill], self.skills_path, "fake-hash")
        self.assertIn("## Overview Table", rendered_skills)
        self.assertIn("`skill:custom`", rendered_skills)
        self.assertIn("fake-hash", rendered_skills)

        module = ResolvedComponent(
            ref="module:custom-mod",
            kind="module",
            requirement="optional",
            from_bundles=["bundle-y"],
            status="unresolved",
            detail={"reason": "catalog entry not found"},
        )
        rendered_modules = render_modules_markdown([module], self.catalog_path, "cat-hash")
        self.assertIn("`module:custom-mod`", rendered_modules)
        self.assertIn("catalog entry not found", rendered_modules)

        tc = {
            "id": "chain-custom",
            "name": "Custom Chain",
            "description": "Custom desc",
            "trigger": "webhook",
            "status": "pending",
            "steps": ["step_a", "step_b"],
        }
        rendered_tc = render_toolchains_markdown([tc], self.toolchains_path, "tc-hash")
        self.assertIn("`chain-custom`", rendered_tc)
        self.assertIn("Custom desc", rendered_tc)
        self.assertIn("webhook", rendered_tc)

    def test_project_bundle_components_helper(self):
        manifest1 = {
            "id": "bundle-1",
            "components": [
                {
                    "type": "skill",
                    "ref": {"ref": "skill:decide", "version": "1.0.0"},
                    "requirement": "recommended",
                }
            ],
        }
        manifest2 = {
            "id": "bundle-2",
            "components": [
                {
                    "type": "skill",
                    "ref": {"ref": "skill:decide", "version": "1.0.0"},
                    "requirement": "required",
                },
                {
                    "type": "module",
                    "ref": {"ref": "module:USMC", "version": "1.0.0"},
                    "requirement": "optional",
                },
            ],
        }
        merged = project_bundle_components([manifest1, manifest2])
        self.assertEqual(len(merged), 2)
        decide = [c for c in merged if c.ref == "skill:decide"][0]
        self.assertEqual(decide.requirement, "required")
        self.assertEqual(sorted(decide.from_bundles), ["bundle-1", "bundle-2"])


if __name__ == "__main__":
    unittest.main()
