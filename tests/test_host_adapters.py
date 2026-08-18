"""Tests for tools/host_adapters.py -- the vendor-neutral Activate-readiness
abstraction (INSTALLER-TARGET.md), Claude Code as the reference implementation
(precedent: D-20260817-005, "Claude als Referenz")."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.host_adapters import ActivateResult, ClaudeCodeHostAdapter, HostAdapter, known_adapters


class ClaudeCodeHostAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.skills_dir = Path(self.temp.name)
        (self.skills_dir / "present-skill").mkdir()
        # A file, not a directory, must not count as "present" -- Activate
        # cares whether the skill is actually usable, not whether the name
        # merely occurs on disk.
        (self.skills_dir / "just-a-file").write_text("not a skill dir")

    def tearDown(self):
        self.temp.cleanup()

    def test_present_skill_directory_is_true(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        self.assertTrue(adapter.skill_present("present-skill"))

    def test_missing_skill_is_false(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        self.assertFalse(adapter.skill_present("ghost-skill"))

    def test_a_plain_file_of_that_name_does_not_count(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        self.assertFalse(adapter.skill_present("just-a-file"))

    def test_default_skills_dir_is_dot_claude_skills_under_home(self):
        adapter = ClaudeCodeHostAdapter()
        self.assertEqual(adapter.skills_dir, Path.home() / ".claude" / "skills")

    def test_conforms_to_the_host_adapter_protocol(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        self.assertIsInstance(adapter, HostAdapter)
        self.assertEqual(adapter.name, "claude-code")


class KnownAdaptersTests(unittest.TestCase):
    def test_registry_contains_claude_code(self):
        adapters = known_adapters()
        self.assertIn("claude-code", adapters)
        self.assertIs(adapters["claude-code"], ClaudeCodeHostAdapter)


class ActivateSkillTests(unittest.TestCase):
    """Write-side Activate. skills_dir here is always an explicit temp dir --
    never the live default -- matching the calling-convention rule this
    module's docstring documents (tools/ocean_dev.py is the only caller
    responsible for keeping that rule at the CLI level; these tests prove
    the mechanism itself, given whatever directory it's told to use)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.skills_dir = self.root / "skills"
        self.source = self.root / "source" / "my-skill"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_text("---\nname: my-skill\n---\nbody")

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_plans_without_touching_disk(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        result = adapter.activate_skill("my-skill", self.source, apply=False)
        self.assertEqual(result.action, "planned")
        self.assertFalse(self.skills_dir.exists())

    def test_apply_copies_the_skill_directory(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        result = adapter.activate_skill("my-skill", self.source, apply=True)
        self.assertEqual(result.action, "activated")
        self.assertTrue((self.skills_dir / "my-skill" / "SKILL.md").is_file())

    def test_never_overwrites_an_existing_destination(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        (self.skills_dir / "my-skill").mkdir(parents=True)
        (self.skills_dir / "my-skill" / "PRE-EXISTING.txt").write_text("do not touch")
        result = adapter.activate_skill("my-skill", self.source, apply=True)
        self.assertEqual(result.action, "skipped-exists")
        self.assertTrue((self.skills_dir / "my-skill" / "PRE-EXISTING.txt").is_file())
        self.assertFalse((self.skills_dir / "my-skill" / "SKILL.md").exists())

    def test_missing_source_directory_fails_cleanly(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        result = adapter.activate_skill("ghost", self.root / "no-such-source", apply=True)
        self.assertEqual(result.action, "failed")
        self.assertFalse((self.skills_dir / "ghost").exists())

    def test_returns_an_activate_result(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        result = adapter.activate_skill("my-skill", self.source, apply=False)
        self.assertIsInstance(result, ActivateResult)


class RollbackActivateSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.skills_dir = Path(self.temp.name) / "skills"
        self.skills_dir.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_removes_an_activated_skill(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        (self.skills_dir / "my-skill").mkdir()
        (self.skills_dir / "my-skill" / "SKILL.md").write_text("x")
        result = adapter.rollback_activate_skill("my-skill")
        self.assertEqual(result.action, "rolled-back")
        self.assertFalse((self.skills_dir / "my-skill").exists())

    def test_rolling_back_something_absent_fails_cleanly_not_a_crash(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        result = adapter.rollback_activate_skill("never-was-here")
        self.assertEqual(result.action, "failed")

    def test_round_trip_activate_then_rollback_restores_empty_state(self):
        adapter = ClaudeCodeHostAdapter(self.skills_dir)
        source = Path(self.temp.name) / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("x")
        adapter.activate_skill("round-trip", source, apply=True)
        self.assertTrue(adapter.skill_present("round-trip"))
        adapter.rollback_activate_skill("round-trip")
        self.assertFalse(adapter.skill_present("round-trip"))


if __name__ == "__main__":
    unittest.main()
