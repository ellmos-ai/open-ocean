"""Tests for tools/fetch_place.py -- the Fetch+Place step of
architecture/INSTALLER-TARGET.md, ported (not imported) from
sovereign-private's pilot installer, minus its known silent-default-branch-
fallback bug (INSTALLER-REUSE-BEFUND_2026-08-07.md Sec. 5.4).

Two kinds of tests here, deliberately:
  - Synthetic-fixture tests (no git subprocess) for the decision logic in
    plan_and_fetch: present / no-catalog-entry / unfetchable-source-type /
    unpinnable / skipped-present-in-workspace. These need no git and no
    network, matching the suite's "must pass on a bare machine" convention.
  - A small number of REAL git tests against a disposable local throwaway
    repository (git supports a plain filesystem path as a remote), the same
    isolated-repo technique INSTALLER-REUSE-BEFUND Sec. 5.4 itself used to
    find the bug this module exists to not repeat. These prove the actual
    git mechanic works, which no amount of mocking would prove -- and they
    still need no network and no real system data, so they stay
    host-independent.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.fetch_place import (
    FetchError,
    fetch_module_at_sha,
    force_rmtree,
    is_git_sha,
    plan_and_fetch,
    resolve_pin_for_module,
    verify_bound_provider,
)

VALID_SHA = "a" * 40
BOGUS_BUT_SHA_SHAPED = "f" * 40  # well-formed, does not exist in any repo


def _component(ref: str, status: str, detail: dict) -> SimpleNamespace:
    """A stand-in for resolve_bundles.ResolvedComponent -- plan_and_fetch only
    reads .ref/.kind/.status/.detail, so a plain namespace is enough and
    keeps this test file independent of resolve_bundles' dataclass."""
    kind, name = ref.split(":", 1)
    return SimpleNamespace(ref=ref, kind=kind, status=status, detail=detail)


class IsGitShaTests(unittest.TestCase):
    def test_accepts_forty_lowercase_hex_chars(self):
        self.assertTrue(is_git_sha("0123456789abcdef0123456789abcdef01234567"))

    def test_rejects_semver_string(self):
        self.assertFalse(is_git_sha("0.1.0"))

    def test_rejects_a_placeholder_like_v4_shadow(self):
        self.assertFalse(is_git_sha("v4-shadow"))

    def test_rejects_uppercase_hex(self):
        self.assertFalse(is_git_sha("A" * 40))

    def test_rejects_short_sha(self):
        self.assertFalse(is_git_sha("abc1234"))

    def test_rejects_none(self):
        self.assertFalse(is_git_sha(None))


class ResolvePinForModuleTests(unittest.TestCase):
    def test_sha_shaped_version_is_the_pin(self):
        sha, raw = resolve_pin_for_module({"version": VALID_SHA})
        self.assertEqual(sha, VALID_SHA)
        self.assertEqual(raw, VALID_SHA)

    def test_semver_version_is_unpinnable_but_reported(self):
        sha, raw = resolve_pin_for_module({"version": "0.1.0"})
        self.assertIsNone(sha)
        self.assertEqual(raw, "0.1.0")

    def test_missing_version_field_is_unpinnable(self):
        sha, raw = resolve_pin_for_module({})
        self.assertIsNone(sha)
        self.assertIsNone(raw)

    def test_commit_sha_field_is_preferred_over_semver_version(self):
        """.MODULES/_scripts/build_catalog.py's builder-computed pin field --
        the fix this test class exists for."""
        sha, raw = resolve_pin_for_module({"version": "0.1.0", "commit_sha": VALID_SHA})
        self.assertEqual(sha, VALID_SHA)
        self.assertEqual(raw, "0.1.0")  # raw_version_field stays `version`, not commit_sha

    def test_commit_sha_field_is_preferred_over_sha_shaped_version_too(self):
        """Even when version itself happens to be a valid SHA, a present
        commit_sha wins -- commit_sha is the one pin field, not a tiebreak."""
        other_sha = "b" * 40
        sha, raw = resolve_pin_for_module({"version": VALID_SHA, "commit_sha": other_sha})
        self.assertEqual(sha, other_sha)

    def test_missing_commit_sha_falls_back_to_sha_shaped_version(self):
        sha, raw = resolve_pin_for_module({"version": VALID_SHA, "commit_sha": None})
        self.assertEqual(sha, VALID_SHA)

    def test_malformed_commit_sha_falls_back_to_sha_shaped_version(self):
        """A present but not-40-hex commit_sha (e.g. truncated/corrupt data)
        does not silently win over a valid version pin -- it is simply not a
        SHA, so resolution falls through to the next field, same as an
        absent field."""
        sha, raw = resolve_pin_for_module({"version": VALID_SHA, "commit_sha": "not-a-sha"})
        self.assertEqual(sha, VALID_SHA)

    def test_both_fields_non_sha_is_unpinnable(self):
        sha, raw = resolve_pin_for_module({"version": "0.1.0", "commit_sha": "not-a-sha"})
        self.assertIsNone(sha)
        self.assertEqual(raw, "0.1.0")

    def test_both_fields_missing_is_unpinnable(self):
        sha, raw = resolve_pin_for_module({"commit_sha": None})
        self.assertIsNone(sha)
        self.assertIsNone(raw)


class FetchModuleAtShaRealGitTests(unittest.TestCase):
    """Uses a real, disposable local git repository as the "remote" -- no
    network access, but real git subprocess calls, proving the mechanic
    itself (not just the branching logic around it)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin"
        self.origin.mkdir()
        self._git(["init", "-q"], cwd=self.origin)
        (self.origin / "marker.txt").write_text("hello from the throwaway origin\n")
        (self.origin / "ellmos-module.v2.json").write_text(json.dumps({
            "schema": "ellmos.module.v2",
            "id": "system-explorer",
            "provides": ["software.endpoint.registry"],
        }), encoding="utf-8")
        self._git(["add", "marker.txt", "ellmos-module.v2.json"], cwd=self.origin)
        self._git(
            ["-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-q", "-m", "initial"],
            cwd=self.origin,
        )
        self.sha = self._git(["rev-parse", "HEAD"], cwd=self.origin).stdout.strip()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)

    def test_fetching_the_real_commit_sha_lands_on_exactly_that_commit(self):
        dest = self.root / "dest"
        outcome = fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=False)
        self.assertEqual(outcome.action, "fetched")
        self.assertEqual(outcome.detail["head"], self.sha)
        self.assertTrue((dest / "marker.txt").is_file())

    def test_a_bogus_sha_shaped_pin_fails_loudly_and_leaves_nothing_behind(self):
        """The load-bearing test: this is what distinguishes "ported the
        pattern" from "ported the bug". A ref that git cannot fetch must
        raise, not fall back to cloning the default branch, and must not
        leave a partial/wrong-commit checkout on disk."""
        dest = self.root / "dest-bogus"
        with self.assertRaises(FetchError):
            fetch_module_at_sha(str(self.origin), BOGUS_BUT_SHA_SHAPED, dest, dry_run=False)
        self.assertFalse(dest.exists(), "a failed fetch must not leave a directory behind")

    def test_non_sha_pin_is_refused_before_any_git_command_runs(self):
        dest = self.root / "dest-unpinned"
        with self.assertRaises(FetchError):
            fetch_module_at_sha(str(self.origin), "main", dest, dry_run=False)
        self.assertFalse(dest.exists())

    def test_dry_run_performs_no_git_operation_and_creates_nothing(self):
        dest = self.root / "dest-dry"
        outcome = fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=True)
        self.assertEqual(outcome.action, "planned")
        self.assertFalse(dest.exists())

    def test_refuses_to_fetch_into_an_existing_destination(self):
        dest = self.root / "dest-exists"
        dest.mkdir()
        with self.assertRaises(FetchError):
            fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=False)

    def test_bound_provider_verifies_commit_repository_identity_and_capability(self):
        dest = self.root / "bound-provider"
        fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=False)

        proof = verify_bound_provider(dest, {
            "catalog_id": "system-explorer",
            "repository": str(self.origin),
            "commit": self.sha,
            "placement_id": "software-endpoint-registry",
            "required_provides": ["software.endpoint.registry"],
            "provider_manifest": "ellmos-module.v2.json",
        })

        self.assertEqual(proof["head"], self.sha)
        self.assertEqual(proof["provider_id"], "system-explorer")
        self.assertEqual(proof["verified_provides"], ["software.endpoint.registry"])

    def test_bound_provider_rejects_an_unproven_capability(self):
        dest = self.root / "bound-provider-missing-capability"
        fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=False)

        with self.assertRaisesRegex(FetchError, "capabilit"):
            verify_bound_provider(dest, {
                "catalog_id": "system-explorer",
                "repository": str(self.origin),
                "commit": self.sha,
                "placement_id": "software-endpoint-registry",
                "required_provides": ["missing.capability"],
                "provider_manifest": "ellmos-module.v2.json",
            })

    def test_bound_provider_rejects_a_dirty_worktree_at_the_pinned_head(self):
        dest = self.root / "bound-provider-dirty"
        fetch_module_at_sha(str(self.origin), self.sha, dest, dry_run=False)
        (dest / "marker.txt").write_text("locally changed\n", encoding="utf-8")

        with self.assertRaisesRegex(FetchError, "uncommitted"):
            verify_bound_provider(dest, {
                "catalog_id": "system-explorer",
                "repository": str(self.origin),
                "commit": self.sha,
                "placement_id": "software-endpoint-registry",
                "required_provides": ["software.endpoint.registry"],
                "provider_manifest": "ellmos-module.v2.json",
            })

    def test_fetching_bound_provider_promotes_an_unresolved_component(self):
        catalog_path = self.root / "modules.catalog.json"
        catalog_path.write_text(json.dumps({"modules": [{
            "id": "system-explorer",
        }]}), encoding="utf-8")
        comp = _component("module:software-endpoint-registry", "unresolved", {
            "catalog_id": "system-explorer",
            "source_type": "git-repository",
            "present_locally": False,
            "repository": str(self.origin),
            "provides": [],
            "binding": {
                "catalog_id": "system-explorer",
                "repository": str(self.origin),
                "commit": self.sha,
                "placement_id": "software-endpoint-registry",
                "required_provides": ["software.endpoint.registry"],
                "provider_manifest": "ellmos-module.v2.json",
                "provider_verified": False,
            },
        })

        outcomes = plan_and_fetch(
            [comp], catalog_path, self.root / "workspace", apply=True
        )

        self.assertEqual(outcomes[0].action, "fetched")
        self.assertEqual(comp.status, "resolved")
        self.assertTrue(comp.detail["binding"]["provider_verified"])


class ForceRmtreeTests(unittest.TestCase):
    def test_reports_failure_when_rmtree_returns_but_target_remains(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            target.mkdir()
            (target / "file.txt").write_text("still here")
            with mock.patch("tools.fetch_place.shutil.rmtree", return_value=None):
                with self.assertRaisesRegex(OSError, "target remains"):
                    force_rmtree(target)
            self.assertTrue(target.is_dir())

    def test_fetch_reports_cleanup_failure_instead_of_hiding_it(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "partial"
            failed_git = SimpleNamespace(returncode=1, stderr="fetch failed", stdout="")
            with mock.patch("tools.fetch_place._run_git", return_value=failed_git), mock.patch(
                "tools.fetch_place.force_rmtree", side_effect=OSError("locked")
            ):
                with self.assertRaisesRegex(FetchError, "cleanup.*failed"):
                    fetch_module_at_sha("https://example.invalid/repo.git", VALID_SHA, dest, dry_run=False)
            self.assertTrue(dest.is_dir())


class PlanAndFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        self.catalog_path = Path(self.temp.name) / "modules.catalog.json"

    def tearDown(self):
        self.temp.cleanup()

    def _write_catalog(self, modules: list[dict]) -> None:
        import json
        self.catalog_path.write_text(json.dumps({"modules": modules}), encoding="utf-8")

    def test_non_module_components_are_ignored(self):
        comp = _component("skill:decide", "resolved", {})
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes, [])

    def test_already_resolved_module_is_reported_present(self):
        comp = _component("module:USMC", "resolved", {"present_locally": True})
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "present")

    def test_dry_run_reports_present_without_touching_disk_for_a_resolved_module(self):
        """T-20260902-313385481: a resolved-but-unbound module (e.g. the
        shared catalog's `resolved_source` pointing into an OneDrive mirror)
        must not be copied anywhere during a dry run."""
        source = Path(self.temp.name) / "mirror" / "some-module"
        (source / "src").mkdir(parents=True)
        comp = _component("module:some-module", "resolved", {
            "catalog_id": "some-module", "present_locally": True, "local_path": str(source),
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "present")
        self.assertFalse((self.workspace / "modules" / "some-module").exists())
        self.assertEqual(comp.detail["local_path"], str(source))

    def test_apply_places_a_resolved_module_without_binding_into_the_workspace(self):
        source = Path(self.temp.name) / "mirror" / "some-module"
        (source / "src").mkdir(parents=True)
        (source / "src" / "marker.py").write_text("x = 1", encoding="utf-8")
        comp = _component("module:some-module", "resolved", {
            "catalog_id": "some-module", "present_locally": True, "local_path": str(source),
        })

        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=True)

        dest = self.workspace / "modules" / "some-module"
        self.assertEqual(outcomes[0].action, "placed")
        self.assertTrue((dest / "src" / "marker.py").is_file())
        self.assertEqual(comp.detail["local_path"], str(dest.resolve(strict=False)))

    def test_second_apply_of_a_resolved_module_is_a_noop_not_an_overwrite(self):
        source = Path(self.temp.name) / "mirror" / "some-module"
        source.mkdir(parents=True)
        dest = self.workspace / "modules" / "some-module"
        dest.mkdir(parents=True)
        (dest / "already-here.txt").write_text("do not touch", encoding="utf-8")
        comp = _component("module:some-module", "resolved", {
            "catalog_id": "some-module", "present_locally": True, "local_path": str(source),
        })

        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=True)

        self.assertEqual(outcomes[0].action, "placed")
        self.assertEqual((dest / "already-here.txt").read_text(encoding="utf-8"), "do not touch")

    def test_bound_alias_uses_overlay_pin_and_placement_even_when_catalog_mirror_is_present(self):
        self._write_catalog([{
            "id": "system-explorer",
            "version": "0.4.0",
            "commit_sha": "b" * 40,
        }])
        comp = _component("module:software-endpoint-registry", "resolved", {
            "catalog_id": "system-explorer",
            "source_type": "git-repository",
            "present_locally": True,
            "repository": "https://example.invalid/system-explorer.git",
            "binding": {
                "catalog_id": "system-explorer",
                "repository": "https://example.invalid/system-explorer.git",
                "commit": VALID_SHA,
                "placement_id": "software-endpoint-registry",
                "required_provides": ["software.endpoint.registry"],
                "provider_manifest": "ellmos-module.v2.json",
                "provider_verified": False,
            },
        })

        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)

        self.assertEqual(outcomes[0].action, "planned")
        self.assertEqual(outcomes[0].detail["sha"], VALID_SHA)
        self.assertEqual(
            Path(outcomes[0].detail["dest"]),
            self.workspace / "modules" / "software-endpoint-registry",
        )
        self.assertEqual(outcomes[0].detail["pin_source"], "component-binding")

    def test_unresolved_without_catalog_id_is_no_catalog_entry(self):
        comp = _component("module:memory-hooker", "unresolved", {"reason": "no catalog entry"})
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "no-catalog-entry")

    def test_local_directory_source_type_is_unfetchable_not_a_crash(self):
        comp = _component("module:something", "unresolved", {
            "catalog_id": "something", "source_type": "local-directory", "present_locally": False,
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "unfetchable-source-type")

    def test_git_repository_with_semver_version_is_unpinnable(self):
        self._write_catalog([{"id": "WikiStub-Seed", "version": "0.1.0"}])
        comp = _component("module:WikiStub-Seed", "unresolved", {
            "catalog_id": "WikiStub-Seed", "source_type": "git-repository",
            "present_locally": False, "repository": "https://example.invalid/repo.git",
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "unpinnable")
        self.assertEqual(outcomes[0].detail["raw_version"], "0.1.0")

    def test_git_repository_with_commit_sha_is_pinnable_despite_semver_version(self):
        """The exact case build_catalog.py's new field exists to fix: a
        module with a human semver version but a real builder-computed pin."""
        self._write_catalog([{"id": "WikiStub-Seed", "version": "0.1.0", "commit_sha": VALID_SHA}])
        comp = _component("module:WikiStub-Seed", "unresolved", {
            "catalog_id": "WikiStub-Seed", "source_type": "git-repository",
            "present_locally": False, "repository": "https://example.invalid/repo.git",
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "planned")
        self.assertEqual(outcomes[0].detail["sha"], VALID_SHA)

    def test_unpinnable_outcome_reports_both_raw_fields(self):
        self._write_catalog([{"id": "build-your-users-mind", "version": "1.1.0-dev", "commit_sha": None}])
        comp = _component("module:build-your-users-mind", "unresolved", {
            "catalog_id": "build-your-users-mind", "source_type": "git-repository",
            "present_locally": False, "repository": "https://example.invalid/repo.git",
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "unpinnable")
        self.assertEqual(outcomes[0].detail["raw_version"], "1.1.0-dev")
        self.assertIsNone(outcomes[0].detail["raw_commit_sha"])

    def test_git_repository_with_real_sha_is_planned_in_dry_run(self):
        self._write_catalog([{"id": "some-module", "version": VALID_SHA}])
        comp = _component("module:some-module", "unresolved", {
            "catalog_id": "some-module", "source_type": "git-repository",
            "present_locally": False, "repository": "https://example.invalid/repo.git",
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=False)
        self.assertEqual(outcomes[0].action, "planned")
        # dry-run must not touch the filesystem at all
        self.assertFalse((self.workspace / "modules" / "some-module").exists())

    def test_existing_workspace_destination_is_never_overwritten(self):
        dest = self.workspace / "modules" / "some-module"
        dest.mkdir(parents=True)
        (dest / "already-here.txt").write_text("do not touch")
        self._write_catalog([{"id": "some-module", "version": VALID_SHA}])
        comp = _component("module:some-module", "unresolved", {
            "catalog_id": "some-module", "source_type": "git-repository",
            "present_locally": False, "repository": "https://example.invalid/repo.git",
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=True)
        self.assertEqual(outcomes[0].action, "skipped-present-in-workspace")
        self.assertEqual((dest / "already-here.txt").read_text(), "do not touch")

    def test_missing_repository_url_fails_without_crashing(self):
        self._write_catalog([{"id": "some-module", "version": VALID_SHA}])
        comp = _component("module:some-module", "unresolved", {
            "catalog_id": "some-module", "source_type": "git-repository",
            "present_locally": False, "repository": None,
        })
        outcomes = plan_and_fetch([comp], self.catalog_path, self.workspace, apply=True)
        self.assertEqual(outcomes[0].action, "failed")


if __name__ == "__main__":
    unittest.main()
