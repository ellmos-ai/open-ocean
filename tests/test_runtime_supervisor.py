from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.runtime_supervisor import _restrict_to_current_user_windows, _write_json_atomic


class RuntimeSupervisorStateTests(unittest.TestCase):
    def test_private_state_acl_fails_closed_on_icacls_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "ocean.runtime.json"
            state_path.write_text("{}\n", encoding="utf-8")
            with patch.dict(os.environ, {"USERNAME": "tester"}), patch(
                "tools.runtime_supervisor.subprocess.run"
            ) as run:
                run.return_value.returncode = 5
                run.return_value.stderr = "Access is denied"
                run.return_value.stdout = ""
                with self.assertRaisesRegex(OSError, "icacls exited 5: Access is denied"):
                    _restrict_to_current_user_windows(state_path)

    def test_atomic_state_write_retries_transient_windows_replace_contention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "ocean.runtime.json"
            state_path.write_text('{"status":"running"}\n', encoding="utf-8")
            original_replace = Path.replace
            attempts = 0

            def replace_with_one_transient_failure(source: Path, target: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("simulated Windows reader contention")
                return original_replace(source, target)

            with patch.object(Path, "replace", new=replace_with_one_transient_failure):
                _write_json_atomic(state_path, {"status": "stopped"})

            self.assertEqual(attempts, 2)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")),
                {"status": "stopped"},
            )


if __name__ == "__main__":
    unittest.main()
