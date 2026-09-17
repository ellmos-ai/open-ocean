from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import call, patch

import tools.runtime_supervisor as runtime_supervisor
from tools.runtime_supervisor import _restrict_to_current_user_windows, _write_json_atomic


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _FakeChild:
    pid = 4242

    def __init__(self, *, timeout_on_first_wait: bool = False) -> None:
        self.returncode = None
        self.timeout_on_first_wait = timeout_on_first_wait
        self.wait_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, *, timeout):
        self.wait_calls += 1
        if self.timeout_on_first_wait and self.wait_calls == 1:
            raise subprocess.TimeoutExpired("fake-child", timeout)
        self.returncode = -15 if self.wait_calls == 1 else -9
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1


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

    def test_posix_stop_signals_the_fenced_group_and_waits_for_empty(self) -> None:
        child = _FakeChild()
        fence = {"kind": "posix-session-group", "pgid": child.pid, "sid": child.pid}
        with (
            patch.object(runtime_supervisor.os, "name", "posix"),
            patch.object(runtime_supervisor.os, "getpgid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "getsid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "killpg", create=True) as killpg,
            patch.object(runtime_supervisor, "_posix_group_empty", side_effect=[False, True]),
        ):
            runtime_supervisor._terminate_child(child, timeout=0.1, process_fence=fence)

        self.assertEqual(killpg.call_args_list, [call(child.pid, runtime_supervisor.POSIX_SIGTERM)])
        self.assertEqual(child.wait_calls, 1)
        self.assertEqual(child.terminate_calls, 0)
        self.assertEqual(child.kill_calls, 0)

    def test_posix_stop_escalates_to_sigkill_when_group_stays_nonempty(self) -> None:
        child = _FakeChild(timeout_on_first_wait=True)
        fence = {"kind": "posix-session-group", "pgid": child.pid, "sid": child.pid}
        with (
            patch.object(runtime_supervisor.os, "name", "posix"),
            patch.object(runtime_supervisor.os, "getpgid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "getsid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "killpg", create=True) as killpg,
            patch.object(runtime_supervisor, "_posix_group_empty", return_value=False),
            patch.object(runtime_supervisor, "_wait_posix_group_empty", side_effect=[False, True]),
        ):
            runtime_supervisor._terminate_child(child, timeout=0.1, process_fence=fence)

        self.assertEqual(
            killpg.call_args_list,
            [
                call(child.pid, runtime_supervisor.POSIX_SIGTERM),
                call(child.pid, runtime_supervisor.POSIX_SIGKILL),
            ],
        )
        self.assertEqual(child.wait_calls, 2)
        self.assertEqual(child.terminate_calls, 0)
        self.assertEqual(child.kill_calls, 0)

    def test_posix_stop_without_a_fence_fails_closed(self) -> None:
        child = _FakeChild()
        with patch.object(runtime_supervisor.os, "name", "posix"):
            with self.assertRaises(runtime_supervisor.ProcessFenceError):
                runtime_supervisor._terminate_child(child)

        self.assertEqual(child.terminate_calls, 0)
        self.assertEqual(child.kill_calls, 0)

    def test_posix_stop_refuses_a_changed_live_child_identity(self) -> None:
        child = _FakeChild()
        fence = {"kind": "posix-session-group", "pgid": child.pid, "sid": child.pid}
        with (
            patch.object(runtime_supervisor.os, "name", "posix"),
            patch.object(runtime_supervisor.os, "getpgid", return_value=child.pid + 1, create=True),
            patch.object(runtime_supervisor.os, "getsid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "killpg", create=True) as killpg,
        ):
            with self.assertRaises(runtime_supervisor.ProcessFenceError):
                runtime_supervisor._terminate_child(child, process_fence=fence)

        killpg.assert_not_called()

    def test_posix_stop_does_not_claim_success_when_group_survives_sigkill(self) -> None:
        child = _FakeChild(timeout_on_first_wait=True)
        fence = {"kind": "posix-session-group", "pgid": child.pid, "sid": child.pid}
        with (
            patch.object(runtime_supervisor.os, "name", "posix"),
            patch.object(runtime_supervisor.os, "getpgid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "getsid", return_value=child.pid, create=True),
            patch.object(runtime_supervisor.os, "killpg", create=True) as killpg,
            patch.object(runtime_supervisor, "_posix_group_empty", return_value=False),
            patch.object(runtime_supervisor, "_wait_posix_group_empty", return_value=False),
        ):
            with self.assertRaises(runtime_supervisor.ProcessFenceError):
                runtime_supervisor._terminate_child(child, process_fence=fence)

        self.assertEqual(
            killpg.call_args_list,
            [
                call(child.pid, runtime_supervisor.POSIX_SIGTERM),
                call(child.pid, runtime_supervisor.POSIX_SIGKILL),
            ],
        )

    @unittest.skipIf(os.name == "nt", "real process groups require POSIX")
    def test_real_posix_fence_stops_a_late_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            child_script = root / "child.py"
            descendant_pid_file = root / "descendant.pid"
            child_script.write_text(
                textwrap.dedent(
                    """
                    from pathlib import Path
                    import subprocess
                    import sys
                    import time

                    marker = Path(sys.argv[1])
                    descendant = subprocess.Popen(
                        [sys.executable, "-c", "import time; time.sleep(120)"]
                    )
                    marker.write_text(str(descendant.pid), encoding="ascii")
                    time.sleep(120)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            state_path = root / "ocean.runtime.json"
            log_path = root / "runtime.log"
            spec_path = root / "ocean.runtime-spec.json"
            spec_path.write_text(
                json.dumps({
                    "schema": "ellmos.open-ocean-runtime-spec.v1",
                    "instance_id": "fixture-instance",
                    "runtime_id": "fixture-runtime",
                    "command": [sys.executable, str(child_script), str(descendant_pid_file)],
                    "cwd": str(root),
                    "env": {},
                    "state_path": str(state_path),
                    "log_path": str(log_path),
                    "runtime_url": "http://127.0.0.1:1",
                    "health_url": "http://127.0.0.1:1/health",
                }),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["OCEAN_RUNTIME_TOKEN"] = "fixture-token"
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(runtime_supervisor.__file__).resolve()),
                    "--spec",
                    str(spec_path),
                ],
                cwd=root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 10
                state = None
                while time.monotonic() < deadline:
                    if supervisor.poll() is not None:
                        self.fail(f"Supervisor endete vor dem State-Receipt: {supervisor.returncode}")
                    if state_path.is_file() and descendant_pid_file.is_file():
                        state = json.loads(state_path.read_text(encoding="utf-8"))
                        if state.get("control", {}).get("port"):
                            break
                    time.sleep(0.02)
                self.assertIsNotNone(state)
                assert state is not None
                descendant_pid = int(descendant_pid_file.read_text(encoding="ascii"))
                self.assertTrue(_pid_exists(descendant_pid))
                control = state["control"]
                request = urllib.request.Request(
                    f"http://{control['host']}:{control['port']}/stop",
                    method="POST",
                    headers={"Authorization": f"Bearer {control['token']}"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    result = json.loads(response.read().decode("utf-8"))
                self.assertEqual(result["status"], "stopped")
                supervisor.wait(timeout=10)
                final_state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(final_state["status"], "stopped")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and _pid_exists(descendant_pid):
                    time.sleep(0.02)
                self.assertFalse(_pid_exists(descendant_pid))
            finally:
                if supervisor.poll() is None:
                    with contextlib.suppress(OSError):
                        os.kill(supervisor.pid, signal.SIGTERM)
                    try:
                        supervisor.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        supervisor.kill()
                        supervisor.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
