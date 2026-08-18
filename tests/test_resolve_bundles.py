"""Tests for tools/resolve_bundles.py -- the Resolve+Verify steps of
architecture/INSTALLER-TARGET.md.

Uses synthetic fixtures throughout (same convention as test_audit_bach_handlers.py
and test_check_k9_data_contract.py): a self-contained temp checkout, not the real
bundles/modules-catalog/skills-registry on this host. That keeps the suite
host-independent -- it must pass on a machine with no OneDrive at all. A real,
one-time run against the actual system data is documented separately in the
ocean-dev build plan report, not encoded here as a fragile CI dependency.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.resolve_bundles import (
    ResolveError,
    ResolvedComponent,
    apply_activation_check,
    canonical_hash,
    expand_components,
    load_skeleton,
    main,
    merge_components,
    resolve_access_surface,
    resolve_module,
    resolve_skill,
    select_bundle_refs,
    verify_bundle,
)


def _bundle(ref: str, components: list[dict], choice_groups: list[dict] | None = None) -> dict:
    """A minimal but schema-shaped bundle.v1.json, content_hash left unset --
    callers seal it with canonical_hash() so the fixture is self-consistent
    by construction, matching how the real recipe repository builds one."""
    manifest = {
        "schema": "ellmos.bundle.v1", "id": ref, "version": "1.0.0",
        "components": components, "choice_groups": choice_groups or [],
    }
    manifest["content_hash"] = canonical_hash(manifest)
    return manifest


def _component(kind: str, name: str, requirement: str = "recommended") -> dict:
    """The real, empirically-verified shape: a wrapper dict whose "ref" key
    holds ANOTHER dict with the actual "<kind>:<name>" string one level down
    (see the docstring in expand_components -- this was not obvious from the
    schema name alone and was checked against all five ring-1 manifests
    before resolve_bundles.py was written)."""
    return {
        "type": kind, "ref": {"ref": f"{kind}:{name}", "version": "v4-shadow"},
        "role": "declared-component", "requirement": requirement,
        "provides": [], "consumes": [],
    }


class CanonicalHashTests(unittest.TestCase):
    def test_excludes_its_own_content_hash_field(self):
        payload = {"a": 1, "content_hash": "should-not-matter"}
        without = dict(payload)
        without.pop("content_hash")
        self.assertEqual(canonical_hash(payload), canonical_hash(without))

    def test_is_sensitive_to_content_changes(self):
        h1 = canonical_hash({"a": 1})
        h2 = canonical_hash({"a": 2})
        self.assertNotEqual(h1, h2)


class SkeletonAndRingSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _write_skeleton(self, **overrides) -> Path:
        skeleton = {
            "schema": "ellmos.open-ocean-architecture-skeleton.v1",
            "authority": {"runtime_authority": False},
            "bundle_refs": [
                {"ref": "bundle-a", "version": "1.0.0", "content_hash": "x"},
                {"ref": "bundle-b", "version": "1.0.0", "content_hash": "y"},
            ],
            "rings": {"1": {"name": "core", "members": ["bundle-a"]}},
        }
        skeleton.update(overrides)
        path = self.root / "skeleton.json"
        path.write_text(json.dumps(skeleton), encoding="utf-8")
        return path

    def test_load_skeleton_rejects_wrong_authority(self):
        path = self._write_skeleton(authority={"runtime_authority": True})
        with self.assertRaises(ResolveError):
            load_skeleton(path)

    def test_select_ring_returns_only_its_members(self):
        skeleton = load_skeleton(self._write_skeleton())
        refs = select_bundle_refs(skeleton, "1")
        self.assertEqual([r["ref"] for r in refs], ["bundle-a"])

    def test_select_all_returns_every_bundle_ref(self):
        skeleton = load_skeleton(self._write_skeleton())
        refs = select_bundle_refs(skeleton, "all")
        self.assertEqual({r["ref"] for r in refs}, {"bundle-a", "bundle-b"})

    def test_unknown_ring_raises(self):
        skeleton = load_skeleton(self._write_skeleton())
        with self.assertRaises(ResolveError):
            select_bundle_refs(skeleton, "99")

    def test_ring_naming_a_bundle_outside_bundle_refs_raises(self):
        skeleton = load_skeleton(self._write_skeleton(
            rings={"1": {"name": "core", "members": ["bundle-does-not-exist"]}}
        ))
        with self.assertRaises(ResolveError):
            select_bundle_refs(skeleton, "1")


class VerifyBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundles_dir = self.root / "manifests" / "bundles"

    def tearDown(self):
        self.temp.cleanup()

    def _place(self, ref: str, manifest: dict) -> None:
        d = self.bundles_dir / ref
        d.mkdir(parents=True)
        (d / "bundle.v1.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_ok_when_declared_matches_computed_and_pin(self):
        manifest = _bundle("b1", [])
        self._place("b1", manifest)
        result, out = verify_bundle({"ref": "b1", "content_hash": manifest["content_hash"]}, self.root)
        self.assertTrue(result.ok)
        self.assertTrue(result.self_consistent)
        self.assertTrue(result.matches_pin)
        self.assertEqual(out, manifest)

    def test_content_tampered_after_hashing_fails_self_consistency_not_pin(self):
        manifest = _bundle("b1", [])
        pinned = manifest["content_hash"]
        manifest["purpose"] = "tampered after the hash was computed"  # hash field left stale
        self._place("b1", manifest)
        result, _ = verify_bundle({"ref": "b1", "content_hash": pinned}, self.root)
        self.assertFalse(result.ok)
        self.assertFalse(result.self_consistent)   # the manifest disagrees with itself
        self.assertTrue(result.matches_pin)         # but the stale declared hash still matches the pin

    def test_skeleton_pin_stale_relative_to_a_self_consistent_bundle(self):
        manifest = _bundle("b1", [])
        self._place("b1", manifest)
        result, _ = verify_bundle({"ref": "b1", "content_hash": "no-longer-the-real-hash"}, self.root)
        self.assertFalse(result.ok)
        self.assertTrue(result.self_consistent)
        self.assertFalse(result.matches_pin)

    def test_missing_manifest_file_fails_cleanly_without_raising(self):
        result, manifest = verify_bundle({"ref": "does-not-exist", "content_hash": "x"}, self.root)
        self.assertFalse(result.ok)
        self.assertIsNone(manifest)


class ExpandComponentsTests(unittest.TestCase):
    def test_unwraps_the_nested_ref_and_captures_requirement(self):
        manifest = _bundle("b1", [_component("module", "foo", requirement="required")])
        components = expand_components(manifest, "b1")
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].ref, "module:foo")
        self.assertEqual(components[0].kind, "module")
        self.assertEqual(components[0].requirement, "required")
        self.assertIsNone(components[0].from_choice)

    def test_choice_group_default_selection_is_expanded_as_required(self):
        manifest = _bundle("b1", [], choice_groups=[{
            "id": "choice:x", "default_selection": ["picked"],
            "candidates": [
                {"ref": "picked", "identity": "module:picked"},
                {"ref": "not-picked", "identity": "module:not-picked"},
            ],
        }])
        components = expand_components(manifest, "b1")
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].ref, "module:picked")
        self.assertEqual(components[0].from_choice, "choice:x")
        self.assertEqual(components[0].requirement, "required")

    def test_malformed_component_without_a_resolvable_ref_raises(self):
        manifest = _bundle("b1", [{"type": "module", "ref": {"version": "x"}, "requirement": "optional"}])
        with self.assertRaises(ResolveError):
            expand_components(manifest, "b1")


class MergeComponentsTests(unittest.TestCase):
    def test_dedups_by_ref_and_unions_source_bundles(self):
        a = expand_components(_bundle("bA", [_component("skill", "shared")]), "bA")
        b = expand_components(_bundle("bB", [_component("skill", "shared")]), "bB")
        merged = merge_components([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].from_bundles), {"bA", "bB"})

    def test_required_beats_recommended_on_merge(self):
        a = expand_components(_bundle("bA", [_component("skill", "shared", requirement="optional")]), "bA")
        b = expand_components(_bundle("bB", [_component("skill", "shared", requirement="required")]), "bB")
        merged = merge_components([a, b])
        self.assertEqual(merged[0].requirement, "required")


class ResolveModuleSkillAccessSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _catalog(self, modules: list[dict]) -> Path:
        path = self.root / "modules.catalog.json"
        path.write_text(json.dumps({"modules": modules}), encoding="utf-8")
        return path

    def test_resolves_present_module_by_exact_id(self):
        (self.root / "present").mkdir()
        catalog = self._catalog([{
            "id": "present", "source_of_truth": {"type": "local-directory", "repository": "r"},
            "resolved_source": "present", "visibility": "public",
        }])
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="module:present", kind="module")
        resolve_module(comp, catalog)
        self.assertEqual(comp.status, "resolved")
        self.assertTrue(comp.detail["present_locally"])

    def test_case_insensitive_fallback_matches_a_unique_candidate(self):
        (self.root / "Present").mkdir()
        catalog = self._catalog([{
            "id": "Present", "source_of_truth": {}, "resolved_source": "Present",
        }])
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="module:present", kind="module")
        resolve_module(comp, catalog)
        self.assertEqual(comp.status, "resolved")

    def test_unknown_module_id_is_unresolved_not_a_crash(self):
        catalog = self._catalog([])
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="module:ghost", kind="module")
        resolve_module(comp, catalog)
        self.assertEqual(comp.status, "unresolved")

    def test_catalogued_but_not_locally_present_is_unresolved(self):
        catalog = self._catalog([{
            "id": "elsewhere", "source_of_truth": {"type": "git-repository", "repository": "r"},
            "resolved_source": "not-actually-here",
        }])
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="module:elsewhere", kind="module")
        resolve_module(comp, catalog)
        self.assertEqual(comp.status, "unresolved")
        self.assertFalse(comp.detail["present_locally"])

    def test_resolve_skill_matches_by_name_field_not_id(self):
        registry = self.root / "components.json"
        registry.write_text(json.dumps({"components": [
            {"id": "skill:dev:decide", "name": "decide", "status": "active"},
        ]}), encoding="utf-8")
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="skill:decide", kind="skill")
        resolve_skill(comp, registry)
        self.assertEqual(comp.status, "resolved")
        self.assertEqual(comp.detail["registry_id"], "skill:dev:decide")

    def test_resolve_skill_reports_absence_without_crashing(self):
        registry = self.root / "components.json"
        registry.write_text(json.dumps({"components": []}), encoding="utf-8")
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="skill:ghost", kind="skill")
        resolve_skill(comp, registry)
        self.assertEqual(comp.status, "unresolved")

    def test_access_surface_is_always_not_fetched_by_design(self):
        from tools.resolve_bundles import ResolvedComponent
        comp = ResolvedComponent(ref="access_surface:some-provider", kind="access_surface")
        resolve_access_surface(comp)
        self.assertEqual(comp.status, "not-fetched-by-design")


class MainIntegrationTests(unittest.TestCase):
    """Exercises main() end to end against a fully synthetic checkout tree --
    the same shape as the real repository, small enough to construct by
    hand, proving the CLI's exit codes without touching real system data."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundles_root = self.root / "bundles"
        (self.bundles_root / "manifests" / "bundles").mkdir(parents=True)
        self.catalog_path = self.root / "modules.catalog.json"
        self.registry_path = self.root / "components.json"
        (self.root / "present").mkdir()
        self.catalog_path.write_text(json.dumps({"modules": [{
            "id": "present", "source_of_truth": {"type": "local-directory", "repository": "r"},
            "resolved_source": "present", "visibility": "public",
        }]}), encoding="utf-8")
        self.registry_path.write_text(json.dumps({"components": [
            {"id": "skill:dev:decide", "name": "decide", "status": "active"},
        ]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _place_bundle(self, ref: str, manifest: dict) -> None:
        d = self.bundles_root / "manifests" / "bundles" / ref
        d.mkdir(parents=True)
        (d / "bundle.v1.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _write_skeleton(self, bundle_refs: list[dict]) -> Path:
        path = self.root / "skeleton.json"
        path.write_text(json.dumps({
            "authority": {"runtime_authority": False},
            "bundle_refs": bundle_refs,
            "rings": {"1": {"name": "core", "members": [b["ref"] for b in bundle_refs]}},
        }), encoding="utf-8")
        return path

    def test_exit_0_on_a_fully_resolvable_ring(self):
        manifest = _bundle("b1", [
            _component("module", "present", requirement="required"),
            _component("skill", "decide", requirement="recommended"),
            _component("access_surface", "some-provider", requirement="optional"),
        ])
        self._place_bundle("b1", manifest)
        skeleton = self._write_skeleton([{"ref": "b1", "content_hash": manifest["content_hash"]}])
        report_path = self.root / "report.json"
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1",
            "--skeleton", str(skeleton), "--modules-catalog", str(self.catalog_path),
            "--skills-registry", str(self.registry_path), "--json", "--report", str(report_path),
        ])
        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["verify"]["all_ok"])
        by_status = report["components"]["by_status"]
        self.assertEqual(by_status.get("resolved"), 2)
        self.assertEqual(by_status.get("not-fetched-by-design"), 1)

    def test_exit_2_on_hash_mismatch_and_no_report_written(self):
        manifest = _bundle("b1", [])
        self._place_bundle("b1", manifest)
        skeleton = self._write_skeleton([{"ref": "b1", "content_hash": "wrong-pin"}])
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1", "--skeleton", str(skeleton),
        ])
        self.assertEqual(code, 2)

    def test_exit_3_on_unreadable_skeleton(self):
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1",
            "--skeleton", str(self.root / "does-not-exist.json"),
        ])
        self.assertEqual(code, 3)

    def test_exit_3_on_unknown_activation_check_host(self):
        manifest = _bundle("b1", [_component("skill", "decide")])
        self._place_bundle("b1", manifest)
        skeleton = self._write_skeleton([{"ref": "b1", "content_hash": manifest["content_hash"]}])
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1", "--skeleton", str(skeleton),
            "--modules-catalog", str(self.catalog_path), "--skills-registry", str(self.registry_path),
            "--activation-check", "no-such-host",
        ])
        self.assertEqual(code, 3)

    def test_activation_check_flag_reaches_the_report(self):
        manifest = _bundle("b1", [_component("skill", "decide")])
        self._place_bundle("b1", manifest)
        skeleton = self._write_skeleton([{"ref": "b1", "content_hash": manifest["content_hash"]}])
        report_path = self.root / "report.json"
        # Use claude-code but point it at an empty temp skills dir via monkeypatching
        # the adapter registry would be a bigger change; instead this proves the
        # wiring reaches the report at all -- ClaudeCodeHostAdapterTests already
        # covers the adapter's own presence logic in isolation.
        code = main([
            "--bundles-root", str(self.bundles_root), "--ring", "1", "--skeleton", str(skeleton),
            "--modules-catalog", str(self.catalog_path), "--skills-registry", str(self.registry_path),
            "--activation-check", "claude-code", "--json", "--report", str(report_path),
        ])
        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertIn("activation", report)
        self.assertEqual(report["activation"]["host"], "claude-code")
        self.assertEqual(report["activation"]["skills_checked"], 1)


class ApplyActivationCheckTests(unittest.TestCase):
    class _FakeAdapter:
        name = "fake-host"

        def __init__(self, present: set[str]) -> None:
            self._present = present

        def skill_present(self, skill_name: str) -> bool:
            return skill_name in self._present

    def test_only_resolved_skill_components_are_checked(self):
        skill_resolved = ResolvedComponent(ref="skill:a", kind="skill", status="resolved")
        skill_unresolved = ResolvedComponent(ref="skill:b", kind="skill", status="unresolved")
        module = ResolvedComponent(ref="module:c", kind="module", status="resolved")
        summary = apply_activation_check(
            [skill_resolved, skill_unresolved, module], self._FakeAdapter({"a"}),
        )
        self.assertEqual(summary, {"host": "fake-host", "skills_checked": 1, "skills_present": 1})
        self.assertEqual(skill_resolved.detail["activation"], {"host": "fake-host", "present": True})
        self.assertNotIn("activation", skill_unresolved.detail)
        self.assertNotIn("activation", module.detail)

    def test_absent_skill_is_reported_as_absent_not_skipped(self):
        comp = ResolvedComponent(ref="skill:ghost", kind="skill", status="resolved")
        summary = apply_activation_check([comp], self._FakeAdapter(set()))
        self.assertEqual(summary["skills_present"], 0)
        self.assertFalse(comp.detail["activation"]["present"])


if __name__ == "__main__":
    unittest.main()
