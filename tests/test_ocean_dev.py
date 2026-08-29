"""Tests for tools/ocean_dev.py -- the single-command entry point chaining
Resolve -> Verify -> Fetch/Place -> Activate, plus --rollback.

Synthetic-fixture end-to-end tests against a fully constructed fixture tree
(same technique as test_resolve_bundles.py's MainIntegrationTests), proving
the *wiring* between resolve_bundles/fetch_place/host_adapters -- the pieces
each already have their own focused unit tests (test_resolve_bundles.py,
test_fetch_place.py, test_host_adapters.py) that this file does not repeat.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.ocean_dev import ActivationLogError, main, write_activation_log
from tools.resolve_bundles import canonical_hash


def _bundle(ref: str, components: list[dict]) -> dict:
    manifest = {"schema": "ellmos.bundle.v1", "id": ref, "version": "1.0.0", "components": components, "choice_groups": []}
    manifest["content_hash"] = canonical_hash(manifest)
    return manifest


def _component(kind: str, name: str, requirement: str = "recommended") -> dict:
    return {
        "type": kind, "ref": {"ref": f"{kind}:{name}", "version": "v4-shadow"},
        "role": "declared-component", "requirement": requirement, "provides": [], "consumes": [],
    }


class OceanDevIntegrationTests(unittest.TestCase):
    """A ring with one already-present module (nothing to fetch) and one
    not-yet-active skill (something for Activate to genuinely do) -- proves
    the dry-run/--apply distinction and the never-live-directory default
    without needing a real git remote."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundles_root = self.root / "bundles"
        (self.bundles_root / "manifests" / "bundles").mkdir(parents=True)
        self.catalog_path = self.root / "modules.catalog.json"
        self.registry_path = self.root / "components.json"
        self.workspace = self.root / "workspace"

        (self.root / "present-module").mkdir()
        self.catalog_path.write_text(json.dumps({"modules": [{
            "id": "present-module", "source_of_truth": {"type": "local-directory", "repository": "r"},
            "resolved_source": "present-module", "visibility": "public",
            "kind": "runtime", "package": "present-module",
            "provides": ["runtime.host"], "requires": ["routing.default"],
            "entrypoints": {"service": "present-module serve"},
            "boundaries": {"network": "local", "data": "user-local"},
        }]}), encoding="utf-8")

        # skills_source_root/skills/dev/decide/SKILL.md -- registry "path" is
        # relative to skills_source_root, verified empirically against the
        # real registry+skills layout before ocean_dev.py was written
        # (see _skills_source_root's docstring).
        skill_dir = self.root / "skills-source" / "skills" / "dev" / "decide"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: decide\n---\nbody")
        self.registry_path.write_text(json.dumps({"components": [
            {"id": "skill:dev:decide", "name": "decide", "path": "skills/dev/decide/SKILL.md", "status": "active"},
        ]}), encoding="utf-8")

        manifest = _bundle("b1", [
            _component("module", "present-module", requirement="required"),
            _component("skill", "decide", requirement="recommended"),
        ])
        bundle_dir = self.bundles_root / "manifests" / "bundles" / "b1"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "bundle.v1.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.skeleton = self.root / "skeleton.json"
        self.skeleton.write_text(json.dumps({
            "authority": {"runtime_authority": False},
            "bundle_refs": [{"ref": "b1", "content_hash": manifest["content_hash"]}],
            "rings": {"1": {"name": "core", "members": ["b1"]}},
        }), encoding="utf-8")

        # ocean_dev.py's own --skills-registry defaults assume a
        # registry/components.json under a .../.SKILLS/ tree; here the
        # registry file itself is NOT under skills-source/, so pass
        # --skills-registry explicitly and rely on _skills_source_root's
        # parent.parent rule only implicitly through direct source_dir
        # construction -- to keep that rule exercised as written, place the
        # registry one level under skills-source/registry/.
        registry_under_source = self.root / "skills-source" / "registry" / "components.json"
        registry_under_source.parent.mkdir(parents=True, exist_ok=True)
        registry_under_source.write_text(self.registry_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.registry_path = registry_under_source

    def tearDown(self):
        self.temp.cleanup()

    def _common_args(self, apply: bool = False, skills_dir: Path | None = None) -> list[str]:
        args = [
            "--bundles-root", str(self.bundles_root), "--ring", "1",
            "--skeleton", str(self.skeleton), "--modules-catalog", str(self.catalog_path),
            "--skills-registry", str(self.registry_path), "--workspace", str(self.workspace),
            "--json",
        ]
        if skills_dir is not None:
            args += ["--skills-dir", str(skills_dir)]
        if apply:
            args.append("--apply")
        return args

    def test_system_manifest_drives_the_complete_dry_run(self):
        system_path = self.root / "system.v1.json"
        skeleton = json.loads(self.skeleton.read_text(encoding="utf-8"))
        system_path.write_text(json.dumps({
            "schema": "ellmos.system.v1",
            "id": "ellmos-development-fullsystem",
            "authority": {"runtime_authority": False},
            "bundle_refs": skeleton["bundle_refs"],
        }), encoding="utf-8")
        report_path = self.root / "system-report.json"

        code = main([
            "--bundles-root", str(self.bundles_root),
            "--system-manifest", str(system_path),
            "--modules-catalog", str(self.catalog_path),
            "--skills-registry", str(self.registry_path),
            "--workspace", str(self.workspace),
            "--json", "--report", str(report_path),
        ])

        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["ring"], "all")
        self.assertEqual(report["composition"], {
            "mode": "system-manifest",
            "schema": "ellmos.system.v1",
            "id": "ellmos-development-fullsystem",
        })
        self.assertEqual(report["verify"]["bundles_checked"], 1)
        self.assertFalse(self.workspace.exists())

    def test_dry_run_writes_nothing(self):
        code = main(self._common_args(apply=False))
        self.assertEqual(code, 0)
        self.assertFalse(self.workspace.exists())

    def test_dry_run_reports_planned_activate(self):
        report_path = self.root / "report.json"
        code = main(self._common_args(apply=False) + ["--report", str(report_path)])
        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        activate = {o["ref"]: o for o in report["activate"]}
        self.assertEqual(activate["skill:decide"]["action"], "planned")
        fetch = {o["ref"]: o for o in report["fetch"]}
        self.assertEqual(fetch["module:present-module"]["action"], "present")

    def test_report_exposes_resolved_runtime_metadata_for_lifecycle_consumers(self):
        report_path = self.root / "report.json"

        code = main(self._common_args(apply=False) + ["--report", str(report_path)])

        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        modules = {item["ref"]: item for item in report["components"] if item["kind"] == "module"}
        runtime = modules["module:present-module"]
        self.assertEqual(runtime["status"], "resolved")
        self.assertEqual(runtime["detail"]["catalog_id"], "present-module")
        self.assertEqual(runtime["detail"]["provides"], ["runtime.host"])
        self.assertEqual(runtime["detail"]["requires"], ["routing.default"])
        self.assertEqual(runtime["detail"]["entrypoints"], {"service": "present-module serve"})
        self.assertEqual(runtime["detail"]["package"], "present-module")
        self.assertEqual(runtime["detail"]["kind"], "runtime")
        self.assertEqual(
            runtime["detail"]["local_path"],
            str((self.catalog_path.parent / "present-module").resolve(strict=False)),
        )

    def test_default_skills_dir_is_under_workspace_not_live_claude_skills(self):
        report_path = self.root / "report.json"
        main(self._common_args(apply=False) + ["--report", str(report_path)])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(Path(report["skills_dir"]), self.workspace / "skills")
        self.assertNotEqual(Path(report["skills_dir"]), Path.home() / ".claude" / "skills")

    def test_apply_activates_the_skill_and_writes_an_activation_log(self):
        code = main(self._common_args(apply=True))
        self.assertEqual(code, 0)
        skills_dir = self.workspace / "skills"
        self.assertTrue((skills_dir / "decide" / "SKILL.md").is_file())
        log_path = self.workspace / "ocean-dev.activation-log.json"
        self.assertTrue(log_path.is_file())
        log = json.loads(log_path.read_text(encoding="utf-8"))
        refs = [e["ref"] for e in log["entries"]]
        self.assertIn("skill:decide", refs)

    def test_new_module_receipt_merges_with_existing_skill_rollback_entries(self):
        log_path = self.workspace / "ocean-dev.activation-log.json"
        prior_skill = self.workspace / "skills" / "decide"
        prior_skill.mkdir(parents=True)
        log_path.write_text(json.dumps({
            "schema": "ellmos.open-ocean-activation-log.v1",
            "entries": [{
                "type": "skill",
                "ref": "skill:decide",
                "id": "decide",
                "dest": str(prior_skill.resolve(strict=False)),
            }],
        }), encoding="utf-8")
        module_dest = self.workspace / "modules" / "software-endpoint-registry"
        outcome = SimpleNamespace(
            action="fetched",
            ref="module:software-endpoint-registry",
            detail={"dest": str(module_dest)},
        )

        write_activation_log(log_path, [outcome], [])
        write_activation_log(log_path, [outcome], [])

        merged = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [(entry["type"], entry["ref"]) for entry in merged["entries"]],
            [
                ("skill", "skill:decide"),
                ("module", "module:software-endpoint-registry"),
            ],
        )

    def test_malformed_existing_activation_log_is_not_overwritten(self):
        log_path = self.workspace / "ocean-dev.activation-log.json"
        log_path.parent.mkdir(parents=True)
        log_path.write_text('{"schema":"wrong","entries":[]}', encoding="utf-8")
        before = log_path.read_bytes()

        with self.assertRaises(ActivationLogError):
            write_activation_log(log_path, [], [{
                "action": "activated",
                "ref": "skill:decide",
                "skill_name": "decide",
                "detail": {"dest": str(self.workspace / "skills" / "decide")},
            }])

        self.assertEqual(log_path.read_bytes(), before)

    def test_conflicting_prior_receipt_stops_apply_before_activation(self):
        log_path = self.workspace / "ocean-dev.activation-log.json"
        log_path.parent.mkdir(parents=True)
        log_path.write_text(json.dumps({
            "schema": "ellmos.open-ocean-activation-log.v1",
            "entries": [{
                "type": "skill",
                "ref": "skill:decide",
                "id": "decide",
                "dest": str((self.root / "wrong-target" / "decide").resolve(strict=False)),
            }],
        }), encoding="utf-8")

        code = main(self._common_args(apply=True))

        self.assertEqual(code, 4)
        self.assertFalse((self.workspace / "skills" / "decide").exists())

    def test_apply_never_overwrites_a_preexisting_skill(self):
        skills_dir = self.workspace / "skills" / "decide"
        skills_dir.mkdir(parents=True)
        (skills_dir / "PRE-EXISTING.txt").write_text("do not touch")
        code = main(self._common_args(apply=True))
        self.assertEqual(code, 0)
        self.assertTrue((skills_dir / "PRE-EXISTING.txt").is_file())
        self.assertFalse((skills_dir / "SKILL.md").exists())

    def test_second_apply_run_is_a_clean_noop_not_a_failure(self):
        main(self._common_args(apply=True))
        code = main(self._common_args(apply=True))
        self.assertEqual(code, 0)

    def test_rollback_removes_what_apply_created(self):
        main(self._common_args(apply=True))
        skills_dir = self.workspace / "skills"
        self.assertTrue((skills_dir / "decide").is_dir())
        log_path = self.workspace / "ocean-dev.activation-log.json"
        code = main([
            "--rollback", str(log_path), "--workspace", str(self.workspace),
            "--skills-dir", str(skills_dir),
        ])
        self.assertEqual(code, 0)
        self.assertFalse((skills_dir / "decide").exists())

    def test_rollback_with_different_skill_target_fails_closed(self):
        main(self._common_args(apply=True))
        original = self.workspace / "skills" / "decide"
        other_workspace = self.root / "other-workspace"
        foreign = other_workspace / "skills" / "decide"
        foreign.mkdir(parents=True)
        (foreign / "FOREIGN.txt").write_text("keep")

        code = main([
            "--rollback", str(self.workspace / "ocean-dev.activation-log.json"),
            "--workspace", str(other_workspace),
            "--skills-dir", str(other_workspace / "skills"),
        ])

        self.assertEqual(code, 4)
        self.assertTrue((original / "SKILL.md").is_file())
        self.assertTrue((foreign / "FOREIGN.txt").is_file())

    def test_unknown_log_entry_fails_before_any_delete(self):
        target = self.workspace / "skills" / "decide"
        target.mkdir(parents=True)
        (target / "KEEP.txt").write_text("keep")
        log_path = self.root / "invalid-log.json"
        log_path.write_text(json.dumps({
            "schema": "ellmos.open-ocean-activation-log.v1",
            "entries": [{"type": "unknown", "ref": "skill:decide", "id": "decide", "dest": str(target)}],
        }), encoding="utf-8")

        code = main([
            "--rollback", str(log_path), "--workspace", str(self.workspace),
            "--skills-dir", str(self.workspace / "skills"),
        ])

        self.assertEqual(code, 4)
        self.assertTrue((target / "KEEP.txt").is_file())

    def test_module_delete_noop_is_not_reported_as_success(self):
        module_dest = self.workspace / "modules" / "module-a"
        module_dest.mkdir(parents=True)
        (module_dest / "KEEP.txt").write_text("keep")
        log_path = self.root / "module-log.json"
        log_path.write_text(json.dumps({
            "schema": "ellmos.open-ocean-activation-log.v1",
            "entries": [{"type": "module", "ref": "module:module-a", "dest": str(module_dest)}],
        }), encoding="utf-8")

        with mock.patch("tools.ocean_dev.force_rmtree", return_value=None):
            code = main([
                "--rollback", str(log_path), "--workspace", str(self.workspace),
                "--skills-dir", str(self.workspace / "skills"),
            ])

        self.assertEqual(code, 4)
        self.assertTrue((module_dest / "KEEP.txt").is_file())

    def test_legacy_module_log_uses_catalog_destination_case_on_posix(self):
        module_dest = self.workspace / "modules" / "catalog-name"
        module_dest.mkdir(parents=True)
        (module_dest / "created-by-apply.txt").write_text("remove")
        log_path = self.root / "legacy-case-log.json"
        log_path.write_text(json.dumps({
            "schema": "ellmos.open-ocean-activation-log.v1",
            "entries": [{
                "type": "module", "ref": "module:CATALOG-NAME", "dest": str(module_dest),
            }],
        }), encoding="utf-8")

        code = main([
            "--rollback", str(log_path), "--workspace", str(self.workspace),
            "--skills-dir", str(self.workspace / "skills"),
        ])

        self.assertEqual(code, 0)
        self.assertFalse(module_dest.exists())

    def test_explicit_skills_dir_can_target_a_real_looking_directory(self):
        """Proves the escape hatch works -- an operator who deliberately
        wants the live directory can still get it -- without this test suite
        itself ever touching a real ~/.claude/skills."""
        explicit_dir = self.root / "pretend-live-skills"
        code = main(self._common_args(apply=True, skills_dir=explicit_dir))
        self.assertEqual(code, 0)
        self.assertTrue((explicit_dir / "decide" / "SKILL.md").is_file())


class OceanDevRealGitFetchIntegrationTests(unittest.TestCase):
    """One end-to-end test with a real disposable git origin and a real skill
    source, proving one CLI invocation performs Fetch and Activate together,
    and that its one activation log lets --rollback undo both writes."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin"
        self.origin.mkdir()
        self._git(["init", "-q"], cwd=self.origin)
        (self.origin / "marker.txt").write_text("x")
        self._git(["add", "marker.txt"], cwd=self.origin)
        self._git(["-c", "user.email=t@example.invalid", "-c", "user.name=T", "commit", "-q", "-m", "i"], cwd=self.origin)
        self.sha = self._git(["rev-parse", "HEAD"], cwd=self.origin).stdout.strip()

        self.bundles_root = self.root / "bundles"
        (self.bundles_root / "manifests" / "bundles").mkdir(parents=True)
        self.catalog_path = self.root / "modules.catalog.json"
        self.registry_path = self.root / "skills-source" / "registry" / "components.json"
        self.workspace = self.root / "workspace"
        self.catalog_path.write_text(json.dumps({"modules": [{
            "id": "fetchable-module",
            "source_of_truth": {"type": "git-repository", "repository": str(self.origin)},
            "resolved_source": "not-actually-here", "version": self.sha, "visibility": "public",
        }]}), encoding="utf-8")
        skill_dir = self.root / "skills-source" / "skills" / "dev" / "decide"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: decide\n---\nbody", encoding="utf-8")
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text(json.dumps({"components": [{
            "id": "skill:dev:decide", "name": "decide",
            "path": "skills/dev/decide/SKILL.md", "status": "active",
        }]}), encoding="utf-8")
        manifest = _bundle("b1", [
            _component("module", "fetchable-module", requirement="required"),
            _component("skill", "decide", requirement="recommended"),
        ])
        bundle_dir = self.bundles_root / "manifests" / "bundles" / "b1"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "bundle.v1.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.skeleton = self.root / "skeleton.json"
        self.skeleton.write_text(json.dumps({
            "authority": {"runtime_authority": False},
            "bundle_refs": [{"ref": "b1", "content_hash": manifest["content_hash"]}],
            "rings": {"1": {"name": "core", "members": ["b1"]}},
        }), encoding="utf-8")

    @staticmethod
    def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_one_apply_fetches_and_activates_then_one_rollback_removes_both(self):
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1", "--skeleton", str(self.skeleton),
            "--modules-catalog", str(self.catalog_path), "--skills-registry", str(self.registry_path),
            "--workspace", str(self.workspace), "--apply",
        ])
        self.assertEqual(code, 0)
        dest = self.workspace / "modules" / "fetchable-module"
        skill_dest = self.workspace / "skills" / "decide"
        self.assertTrue((dest / "marker.txt").is_file())
        self.assertTrue((skill_dest / "SKILL.md").is_file())

        log_path = self.workspace / "ocean-dev.activation-log.json"
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [(entry["type"], entry["ref"]) for entry in log["entries"]],
            [("module", "module:fetchable-module"), ("skill", "skill:decide")],
        )
        self.assertEqual(log["entries"][0]["id"], "fetchable-module")
        code = main([
            "--rollback", str(log_path), "--workspace", str(self.workspace),
            "--skills-dir", str(self.workspace / "skills"),
        ])
        self.assertEqual(code, 0)
        self.assertFalse(dest.exists())
        self.assertFalse(skill_dest.exists())

    def test_rollback_with_different_workspace_preserves_original_and_foreign_targets(self):
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1", "--skeleton", str(self.skeleton),
            "--modules-catalog", str(self.catalog_path), "--skills-registry", str(self.registry_path),
            "--workspace", str(self.workspace), "--apply",
        ])
        self.assertEqual(code, 0)
        original_module = self.workspace / "modules" / "fetchable-module"
        original_skill = self.workspace / "skills" / "decide"

        other_workspace = self.root / "other-workspace"
        foreign_module = other_workspace / "modules" / "fetchable-module"
        foreign_skill = other_workspace / "skills" / "decide"
        foreign_module.mkdir(parents=True)
        foreign_skill.mkdir(parents=True)
        (foreign_module / "FOREIGN.txt").write_text("keep")
        (foreign_skill / "FOREIGN.txt").write_text("keep")

        code = main([
            "--rollback", str(self.workspace / "ocean-dev.activation-log.json"),
            "--workspace", str(other_workspace),
            "--skills-dir", str(other_workspace / "skills"),
        ])

        self.assertEqual(code, 4)
        self.assertTrue((original_module / "marker.txt").is_file())
        self.assertTrue((original_skill / "SKILL.md").is_file())
        self.assertTrue((foreign_module / "FOREIGN.txt").is_file())
        self.assertTrue((foreign_skill / "FOREIGN.txt").is_file())


if __name__ == "__main__":
    unittest.main()
