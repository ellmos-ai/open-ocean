"""Tests for tools/host_adapters.py -- the vendor-neutral Activate-readiness
abstraction (INSTALLER-TARGET.md), Claude Code as the reference implementation
(precedent: D-20260817-005, "Claude als Referenz")."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.host_adapters import ClaudeCodeHostAdapter, HostAdapter, known_adapters


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


if __name__ == "__main__":
    unittest.main()
