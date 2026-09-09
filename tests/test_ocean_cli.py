"""User-facing OCEAN lifecycle CLI acceptance tests."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import ocean as ocean_cli
import tools.ocean_lifecycle as ocean_lifecycle
from tools.ocean_lifecycle import (
    LifecycleError,
    RuntimeProvider,
    _assert_composition_complete,
    _ellmos_core_runtime_spec,
    _start_lock,
)
from tools.resolve_bundles import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[1]
OCEAN = REPO_ROOT / "ocean.py"


def test_root_help_exposes_the_complete_first_usable_lifecycle():
    """Catches shipping another installer-only entry point without lifecycle verbs."""
    proc = subprocess.run(
        [sys.executable, str(OCEAN), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0, proc.stderr
    assert "plan" in proc.stdout
    assert "up" in proc.stdout
    assert "start" in proc.stdout
    assert "status" in proc.stdout
    assert "down" in proc.stdout
    assert "user" in proc.stdout
    assert "prüfen" in proc.stdout
    assert "\ufffd" not in proc.stdout
    assert "\ufffd" not in proc.stderr


def test_plan_help_exposes_the_exact_component_binding_overlay():
    """Keeps the per-module integration seam visible on the product CLI."""
    proc = subprocess.run(
        [sys.executable, str(OCEAN), "plan", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0, proc.stderr
    assert "--component-bindings" in proc.stdout
    assert "exaktes OCEAN-Integrations-Overlay" in proc.stdout
    assert "\ufffd" not in proc.stdout
    assert "\ufffd" not in proc.stderr


def _write_plan_fixture(root: Path, *, runtime_providers: int = 1) -> dict[str, Path]:
    bundles_root = root / "composition"
    manifest_dir = bundles_root / "manifests" / "bundles" / "core"
    manifest_dir.mkdir(parents=True)
    components = []
    catalog_modules = []
    for index in range(runtime_providers):
        module_id = f"fixture-runtime-{index + 1}"
        source = root / module_id
        source.mkdir()
        components.append({
            "type": "module",
            "ref": {"ref": f"module:{module_id}", "version": "fixture"},
            "role": "runtime",
            "requirement": "required",
            "provides": [],
            "consumes": [],
        })
        catalog_modules.append({
            "id": module_id,
            "kind": "runtime",
            "package": module_id,
            "provides": ["runtime.host"],
            "requires": [],
            "entrypoints": {"service": f"{module_id} serve"},
            "resolved_source": source.name,
            "source_of_truth": {"type": "local-directory", "repository": "fixture"},
            "boundaries": {"network": "local", "data": "synthetic"},
        })
    bundle = {
        "schema": "ellmos.bundle.v1",
        "id": "core",
        "version": "1.0.0",
        "components": components,
        "choice_groups": [],
    }
    bundle["content_hash"] = canonical_hash(bundle)
    (manifest_dir / "bundle.v1.json").write_text(json.dumps(bundle), encoding="utf-8")
    system = root / "system.v1.json"
    system.write_text(json.dumps({
        "schema": "ellmos.system.v1",
        "id": "fixture-ocean",
        "authority": {"runtime_authority": False},
        "bundle_refs": [{"ref": "core", "content_hash": bundle["content_hash"]}],
    }), encoding="utf-8")
    catalog = root / "modules.catalog.json"
    catalog.write_text(json.dumps({"modules": catalog_modules}), encoding="utf-8")
    skills = root / "skills" / "registry" / "components.json"
    skills.parent.mkdir(parents=True)
    skills.write_text(json.dumps({"components": []}), encoding="utf-8")
    return {
        "bundles_root": bundles_root,
        "system": system,
        "catalog": catalog,
        "skills": skills,
        "workspace": root / "workspace",
    }


def _write_runnable_ellmos_core_fixture(root: Path) -> dict[str, Path]:
    fixture = _write_plan_fixture(root)
    catalog = json.loads(fixture["catalog"].read_text(encoding="utf-8"))
    entry = catalog["modules"][0]
    old_source = root / entry["resolved_source"]
    source = root / "ellmos-core"
    old_source.rename(source)
    entry.update({
        "id": "ellmos-core",
        "package": "ellmos-core",
        "resolved_source": source.name,
        "entrypoints": {"service": "ellmos-core serve"},
    })
    fixture["catalog"].write_text(json.dumps(catalog), encoding="utf-8")
    manifest_path = fixture["bundles_root"] / "manifests" / "bundles" / "core" / "bundle.v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"][0]["ref"]["ref"] = "module:ellmos-core"
    manifest["content_hash"] = canonical_hash(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    system = json.loads(fixture["system"].read_text(encoding="utf-8"))
    system["bundle_refs"][0]["content_hash"] = manifest["content_hash"]
    fixture["system"].write_text(json.dumps(system), encoding="utf-8")

    package = source / "src" / "ellmos_core"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(textwrap.dedent("""
        from __future__ import annotations
        import argparse
        import json
        import os
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from pathlib import Path

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/health":
                    body = json.dumps({"status": "ok", "runtime": "fixture"}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self.end_headers()
            def log_message(self, *_args):
                return

        def cmd_init_user(args):
            marker = Path(os.environ["ELLMOS_CORE_DB_PATH"]).with_suffix(".user.json")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                "username": args.username,
                "email": args.email,
                "role": args.role,
            }), encoding="utf-8")

        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("command", choices=["serve", "init-user"])
            parser.add_argument("--username")
            parser.add_argument("--email")
            parser.add_argument("--role")
            args = parser.parse_args()
            if args.command == "serve":
                host = os.environ["ELLMOS_CORE_HOST"]
                port = int(os.environ["ELLMOS_CORE_PORT"])
                ThreadingHTTPServer((host, port), Handler).serve_forever()
            if args.command == "init-user":
                cmd_init_user(args)

        if __name__ == "__main__":
            main()
    """), encoding="utf-8")
    return fixture


def _free_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_ocean(
    *args: str,
    input_text: str | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(OCEAN), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        timeout=timeout,
    )


def _workspace_snapshot(workspace: Path) -> dict[str, bytes]:
    """Return the entire fixture workspace without exposing its contents."""
    if not workspace.is_dir():
        return {}
    return {
        str(path.relative_to(workspace)): path.read_bytes()
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def _down_fixture(workspace: Path) -> None:
    """Finish a fixture runtime despite a short Windows state-file handoff."""
    deadline = time.monotonic() + 5.0
    last_error = "kein Down-Ergebnis"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(
                "Fixture-Cleanup hat keine Restzeit im 5-s-Gesamtbudget; "
                f"letzter Fehler: {last_error}"
            )
        try:
            last = _run_ocean(
                "down", "--workspace", str(workspace), "--json", timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(
                "Fixture-Cleanup Zeitüberschreitung im 5-s-Gesamtbudget; "
                f"verbleibende Frist: {remaining:.3f}s ({exc})"
            )
        if last.returncode == 0:
            return
        last_error = last.stderr or f"ocean down endete mit Exit {last.returncode}"
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.05, remaining))


def test_run_ocean_forwards_an_optional_timeout_to_subprocess(monkeypatch):
    """The fixture runner must pass its remaining budget to the real child."""
    observed = {}

    def fake_run(command, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _run_ocean("down", "--workspace", "fixture", timeout=1.25)

    assert result.returncode == 0
    assert observed["timeout"] == 1.25


def test_down_fixture_uses_an_absolute_budget_for_slow_failed_attempts(tmp_path, monkeypatch):
    """Two slow failed attempts may never consume more than the 5-s total budget."""
    clock = {"now": 0.0}
    timeouts = []

    def slow_down(*args, timeout=None, **_kwargs):
        timeouts.append(timeout)
        duration = 3.0 if timeout is None else min(3.0, timeout)
        clock["now"] += duration
        if timeout is not None and timeout < 3.0:
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, 3, "", "fixture state temporarily locked")

    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setattr(sys.modules[__name__], "_run_ocean", slow_down)

    with pytest.raises(pytest.fail.Exception) as failed:
        _down_fixture(tmp_path)

    assert all(timeout is not None for timeout in timeouts)
    assert timeouts[0] == pytest.approx(5.0)
    assert clock["now"] <= 5.0
    assert "Gesamtbudget" in str(failed.value)


def test_down_fixture_reports_a_hanging_child_timeout_within_the_budget(tmp_path, monkeypatch):
    """TimeoutExpired is a visible cleanup failure, never an unbounded hang."""
    clock = {"now": 0.0}
    timeouts = []

    def hanging_down(*args, timeout=None, **_kwargs):
        timeouts.append(timeout)
        clock["now"] += timeout
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(sys.modules[__name__], "_run_ocean", hanging_down)

    with pytest.raises(pytest.fail.Exception) as failed:
        _down_fixture(tmp_path)

    assert timeouts == [pytest.approx(5.0)]
    assert clock["now"] <= 5.0
    assert "Zeitüberschreitung" in str(failed.value)


def test_down_fixture_does_not_start_a_call_without_remaining_budget(tmp_path, monkeypatch):
    """An exhausted deadline fails visibly before a new subprocess is started."""
    moments = iter([0.0, 5.0])
    calls = []

    monkeypatch.setattr(time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(sys.modules[__name__], "_run_ocean", lambda *_a, **_k: calls.append(True))

    with pytest.raises(pytest.fail.Exception) as failed:
        _down_fixture(tmp_path)

    assert calls == []
    assert "keine Restzeit" in str(failed.value)


def test_down_fixture_accepts_a_successful_child_within_the_budget(tmp_path, monkeypatch):
    """A real zero exit remains the sole successful fixture-cleanup outcome."""
    clock = {"now": 0.0}
    timeouts = []

    def successful_down(*args, timeout=None, **_kwargs):
        timeouts.append(timeout)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(sys.modules[__name__], "_run_ocean", successful_down)

    _down_fixture(tmp_path)

    assert timeouts == [pytest.approx(5.0)]


def test_runtime_spec_exposes_resolved_operator_ui_as_the_ocean_surface(tmp_path):
    """Catches accepting a domain app's HTTP 200 as the OCEAN product surface."""
    core = tmp_path / "ellmos-core"
    (core / "src" / "ellmos_core").mkdir(parents=True)
    operator_ui = tmp_path / "ellmos-unified-gui"
    (operator_ui / "src" / "unified_gui").mkdir(parents=True)
    manifest = tmp_path / "sovereign.manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    provider = RuntimeProvider(
        id="ellmos-core",
        ref="module:ellmos-core",
        local_path=core,
        entrypoints={"service": "ellmos-core serve"},
        package="ellmos-core",
        detail={},
    )
    components = [
        {
            "kind": "module",
            "status": "resolved",
            "ref": "module:ellmos-core",
            "detail": {"local_path": str(core), "provides": ["runtime.host"]},
        },
        {
            "kind": "module",
            "status": "resolved",
            "ref": "module:ellmos-unified-gui",
            "detail": {
                "catalog_id": "ellmos-unified-gui",
                "local_path": str(operator_ui),
                "provides": ["operator.ui", "unified-gui.host"],
            },
        },
    ]

    spec = _ellmos_core_runtime_spec(
        provider,
        components,
        tmp_path / "workspace",
        manifest,
        "127.0.0.1",
        8810,
    )

    assert spec["runtime_url"] == "http://127.0.0.1:8810/control/"
    assert spec["health_url"] == "http://127.0.0.1:8810/api/health"
    assert spec["env"]["ELLMOS_CORE_CONSOLE_ENABLED"] == "1"
    assert spec["env"]["ELLMOS_CORE_CONSOLE_PREFIX"] == "/control"
    assert Path(spec["command"][1]).name == "ocean_runtime.py"
    assert str(operator_ui / "src") in spec["env"]["PYTHONPATH"]
    assert Path(spec["cwd"]) == (tmp_path / "workspace").resolve(strict=False)
    assert json.loads(
        (tmp_path / "workspace" / "unified-gui.config.json").read_text(encoding="utf-8")
    ) == {"title": "OCEAN Full Dev"}


def test_plan_proves_one_runtime_host_without_creating_the_workspace(tmp_path):
    """Catches treating a verified recipe as usable without a runnable host."""
    fixture = _write_plan_fixture(tmp_path)

    proc = _run_ocean(
        "plan",
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
        "--json",
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["schema"] == "ellmos.open-ocean-lifecycle-plan.v1"
    assert report["composition"] == {
        "id": "fixture-ocean",
        "mode": "system-manifest",
        "schema": "ellmos.system.v1",
    }
    assert report["runtime"]["id"] == "fixture-runtime-1"
    assert report["runtime"]["capability"] == "runtime.host"
    assert report["readiness"]["runtime_host"] is True
    assert report["readiness"]["required_components_missing"] == []
    assert not fixture["workspace"].exists()


def test_up_status_down_runs_one_real_sandboxed_runtime_round_trip(tmp_path):
    """Catches a lifecycle that writes files but never reaches a live usable system."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        up = _run_ocean("up", *common, "--host", "127.0.0.1", "--port", str(port), "--apply", "--json")
        assert up.returncode == 0, up.stderr
        up_report = json.loads(up.stdout)
        assert up_report["schema"] == "ellmos.open-ocean-lifecycle-up.v1"
        assert up_report["runtime"]["id"] == "ellmos-core"
        assert up_report["runtime"]["status"] == "running"
        assert up_report["runtime"]["url"] == f"http://127.0.0.1:{port}"
        runtime_spec = json.loads(
            (fixture["workspace"] / "ocean.runtime-spec.json").read_text(encoding="utf-8")
        )
        assert runtime_spec["env"]["ELLMOS_CORE_DEBUG"] == "0"
        assert runtime_spec["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert runtime_spec["env"]["PYTHONUTF8"] == "1"
        assert len(runtime_spec["env"]["ELLMOS_CORE_SECRET_KEY"]) >= 32
        assert runtime_spec["env"]["ELLMOS_CORE_SECRET_KEY"] != "CHANGE-ME-IN-PRODUCTION"

        status = _run_ocean("status", "--workspace", str(fixture["workspace"]), "--json")
        assert status.returncode == 0, status.stderr
        status_report = json.loads(status.stdout)
        assert status_report["schema"] == "ellmos.open-ocean-lifecycle-status.v1"
        assert status_report["runtime"]["control"] == "running"
        assert status_report["runtime"]["health"] == "ok"
        assert status_report["readiness"]["full_composition"] is True
        assert (fixture["workspace"] / "sovereign.manifest.json").is_file()
        assert (fixture["workspace"] / "sovereign.lock.json").is_file()

        user = _run_ocean(
            "user", "add",
            "--workspace", str(fixture["workspace"]),
            "--username", "ocean-owner",
            "--email", "owner@example.test",
            "--role", "admin",
            "--password-stdin",
            "--json",
            input_text="fixture-password\n",
        )
        assert user.returncode == 0, user.stderr
        user_report = json.loads(user.stdout)
        assert user_report == {
            "schema": "ellmos.open-ocean-user-add.v1",
            "runtime_id": "ellmos-core",
            "username": "ocean-owner",
            "role": "admin",
            "created": True,
        }
        marker = fixture["workspace"] / "state" / "ellmos_core.user.json"
        assert json.loads(marker.read_text(encoding="utf-8")) == {
            "username": "ocean-owner",
            "email": "owner@example.test",
            "role": "admin",
        }

        down = _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")
        assert down.returncode == 0, down.stderr
        assert json.loads(down.stdout)["stopped"] is True

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            stopped = _run_ocean("status", "--workspace", str(fixture["workspace"]), "--json")
            if stopped.returncode == 1:
                break
            time.sleep(0.05)
        assert stopped.returncode == 1
        assert json.loads(stopped.stdout)["runtime"]["control"] == "stopped"

        restarted = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--apply",
            "--json",
        )
        assert restarted.returncode == 0, restarted.stderr
        restarted_report = json.loads(restarted.stdout)
        assert restarted_report["runtime"]["status"] == "running"
        assert restarted_report["runtime"]["health"] == "ok"
    finally:
        _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")


def test_health_timeout_is_configurable_and_names_an_empty_runtime_log(tmp_path):
    """T-20260903-224229063 Fall 2: a fixed 20s health window destroyed a
    runtime that only needed more time on a loaded host, and the failure
    pointed at supervisor.log instead of the log that actually shows what
    the child did (or didn't) do. --health-timeout must be reachable from
    the CLI, and giving up must say plainly that the child never even wrote
    its first log line -- the exact signal that distinguishes "slow" from
    "not starting at all"."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        up = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1", "--port", str(port),
            "--apply", "--health-timeout", "0.01", "--json",
        )
        assert up.returncode != 0
        assert "keinen grünen Health-Status" in up.stderr
        assert "ist leer" in up.stderr
        assert "runtime.log" in up.stderr
    finally:
        _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")


def test_valid_start_still_tees_lifecycle_errors_to_the_runtime_log(tmp_path, monkeypatch):
    """Input validation must not remove the scheduled start's error record."""
    original_stderr = sys.stderr

    def fail_start(*_args, **_kwargs):
        raise LifecycleError("fixture valid start failure", exit_code=4)

    monkeypatch.setattr(ocean_cli, "start_installed_runtime", fail_start)
    try:
        exit_code = ocean_cli.main([
            "start", "--workspace", str(tmp_path), "--health-timeout", "1",
        ])
    finally:
        tee = sys.stderr
        sys.stderr = original_stderr
        if isinstance(tee, ocean_cli._TeeWriter):
            tee._log.close()

    assert exit_code == 4
    log = (tmp_path / "logs" / "runtime.log").read_text(encoding="utf-8")
    assert "ocean.py start stderr" in log
    assert "fixture valid start failure" in log


def test_up_and_start_share_the_health_timeout_cli_option():
    """Both lifecycle entry points must expose the same explicit override."""
    parser = ocean_cli.build_parser()
    up = parser.parse_args([
        "up",
        "--bundles-root", "bundles",
        "--system-manifest", "system.json",
        "--modules-catalog", "catalog.json",
        "--skills-registry", "skills.json",
        "--workspace", "workspace",
        "--apply",
        "--health-timeout", "27.5",
    ])
    start = parser.parse_args([
        "start", "--workspace", "workspace", "--health-timeout", "27.5",
    ])

    assert up.health_timeout == 27.5
    assert start.health_timeout == 27.5


def _mock_supervisor_receipt(monkeypatch, workspace: Path, *, status: str) -> None:
    """Use a process-free supervisor double that writes only a test receipt."""
    launch = {
        "command": [sys.executable, "-c", "raise SystemExit(0)"],
        "cwd": str(workspace),
        "env": {},
        "runtime_url": "http://127.0.0.1:18991",
        "health_url": "http://127.0.0.1:18991/api/health",
    }
    monkeypatch.setattr(ocean_lifecycle, "_assert_runtime_start_available", lambda *_a, **_k: None)
    monkeypatch.setattr(ocean_lifecycle, "_ellmos_core_runtime_spec", lambda *_a, **_k: launch)

    def fake_popen(command, **_kwargs):
        spec = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        ocean_lifecycle._write_json_atomic(workspace / ocean_lifecycle.RUNTIME_STATE, {
            "schema": "ellmos.open-ocean-runtime-state.v1",
            "instance_id": spec["instance_id"],
            "runtime_id": "fixture-runtime",
            "status": status,
            "supervisor_pid": 0,
            "child_pid": 0,
            "control": {"host": "127.0.0.1", "port": 18991, "token": "fixture"},
            "runtime_url": launch["runtime_url"],
            "health_url": launch["health_url"],
        })
        return object()

    monkeypatch.setattr(ocean_lifecycle.subprocess, "Popen", fake_popen)


def test_default_timeout_allows_a_slow_but_living_fixture_child(tmp_path, monkeypatch):
    """A running child reaching health after 20 s must remain eligible before 60 s."""
    clock = {"now": 0.0}
    _mock_supervisor_receipt(monkeypatch, tmp_path, status="running")
    monkeypatch.setattr(ocean_lifecycle, "_control_request", lambda *_a, **_k: {"status": "running"})
    monkeypatch.setattr(ocean_lifecycle, "_health", lambda *_a, **_k: clock["now"] >= 20.1)
    monkeypatch.setattr(ocean_lifecycle.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        ocean_lifecycle.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    state = ocean_lifecycle.start_runtime(
        RuntimeProvider("fixture-runtime", "fixture", tmp_path, {}, None, {}),
        [],
        tmp_path,
        tmp_path / "manifest.json",
        host="127.0.0.1",
        port=18991,
    )

    assert state["status"] == "running"
    assert 20.0 < clock["now"] < ocean_lifecycle.DEFAULT_HEALTH_TIMEOUT


def test_default_timeout_fails_fast_when_the_fixture_child_is_already_stopped(tmp_path, monkeypatch):
    """A stopped receipt is an immediate failure signal, not a 60-s wait."""
    clock = {"now": 0.0}
    _mock_supervisor_receipt(monkeypatch, tmp_path, status="stopped")
    monkeypatch.setattr(ocean_lifecycle, "_control_request", lambda *_a, **_k: {"status": "stopped"})
    monkeypatch.setattr(ocean_lifecycle, "_health", lambda *_a, **_k: pytest.fail("stopped child was polled"))
    monkeypatch.setattr(ocean_lifecycle.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        ocean_lifecycle.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with pytest.raises(LifecycleError, match="60s keinen grünen Health-Status"):
        ocean_lifecycle.start_runtime(
            RuntimeProvider("fixture-runtime", "fixture", tmp_path, {}, None, {}),
            [],
            tmp_path,
            tmp_path / "manifest.json",
            host="127.0.0.1",
            port=18991,
        )

    assert clock["now"] == 0.0


@pytest.mark.parametrize("bad_timeout", ["-1", "0", "nan", "inf", "-inf"])
def test_up_rejects_a_non_positive_or_non_finite_health_timeout_before_starting_anything(
    tmp_path, bad_timeout
):
    """T-20260903-224229063 Blocker 1: `deadline = time.monotonic() +
    startup_timeout` is already in the past (or, for +inf, never in the
    past) before the poll loop's first check for a negative/zero/NaN/+-inf
    timeout -- the loop body then never runs even once, so it can't reach
    its own stop-and-report path either. The public `up` entry point must
    reject the value before its transaction creates installation, projection,
    activation, spec, or state files."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    fixture["workspace"].mkdir()
    (fixture["workspace"] / "preexisting.marker").write_bytes(b"preserve this fixture workspace")
    before = _workspace_snapshot(fixture["workspace"])
    port = _free_tcp_port()
    up = _run_ocean(
        "up",
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
        "--host", "127.0.0.1", "--port", str(port),
        "--apply", f"--health-timeout={bad_timeout}", "--json",
    )

    assert up.returncode == 2, up.stdout + up.stderr
    assert "--health-timeout" in up.stderr
    assert _workspace_snapshot(fixture["workspace"]) == before
    with socket.socket() as probe:
        probe.settimeout(0.2)
        with pytest.raises(OSError):
            probe.connect(("127.0.0.1", port))


@pytest.mark.parametrize("bad_timeout", ["-1", "0", "nan", "inf", "-inf"])
def test_start_rejects_a_non_positive_or_non_finite_health_timeout_before_healthy_reuse(
    tmp_path, bad_timeout
):
    """An invalid timeout must not be accepted merely because a live runtime is reusable."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        initial = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1", "--port", str(port),
            "--apply", "--json",
        )
        assert initial.returncode == 0, initial.stderr
        before = _workspace_snapshot(fixture["workspace"])

        start = _run_ocean(
            "start", "--workspace", str(fixture["workspace"]),
            f"--health-timeout={bad_timeout}", "--json",
        )

        assert start.returncode == 2, start.stdout + start.stderr
        assert "--health-timeout" in start.stderr
        assert _workspace_snapshot(fixture["workspace"]) == before
    finally:
        _down_fixture(fixture["workspace"])


def test_second_up_rejects_a_running_runtime_before_fetch_or_activate(tmp_path):
    """A running sandbox is a write preflight gate, not a late start error."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        first = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--apply",
            "--json",
        )
        assert first.returncode == 0, first.stderr
        log_path = fixture["workspace"] / "ocean-dev.activation-log.json"
        log_before = log_path.read_bytes() if log_path.exists() else None

        manifest_path = (
            fixture["bundles_root"]
            / "manifests"
            / "bundles"
            / "core"
            / "bundle.v1.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["components"].append({
            "type": "skill",
            "ref": {"ref": "skill:late-skill", "version": "fixture"},
            "role": "fixture",
            "requirement": "recommended",
            "provides": [],
            "consumes": [],
        })
        manifest["content_hash"] = canonical_hash(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        system = json.loads(fixture["system"].read_text(encoding="utf-8"))
        system["bundle_refs"][0]["content_hash"] = manifest["content_hash"]
        fixture["system"].write_text(json.dumps(system), encoding="utf-8")

        skill_source = (
            fixture["skills"].parent.parent
            / "skills"
            / "fixture"
            / "late-skill"
        )
        skill_source.mkdir(parents=True)
        (skill_source / "SKILL.md").write_text("# Late skill\n", encoding="utf-8")
        fixture["skills"].write_text(json.dumps({
            "components": [{
                "id": "skill:fixture:late-skill",
                "name": "late-skill",
                "category": "fixture",
                "status": "active",
                "path": "skills/fixture/late-skill/SKILL.md",
            }],
        }), encoding="utf-8")

        second = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--apply",
            "--json",
        )

        assert second.returncode != 0
        assert "läuft bereits" in second.stderr
        assert not (fixture["workspace"] / "skills" / "late-skill").exists()
        log_after = log_path.read_bytes() if log_path.exists() else None
        assert log_after == log_before
    finally:
        _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")


def test_start_recovers_an_installed_runtime_from_stale_running_state(tmp_path):
    """Catches an OS/process loss leaving OCEAN permanently blocked by stale JSON."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        up = _run_ocean(
            "up", *common,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--apply",
            "--json",
        )
        assert up.returncode == 0, up.stderr
        down = _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")
        assert down.returncode == 0, down.stderr

        state_path = fixture["workspace"] / "ocean.runtime.json"
        stale = json.loads(state_path.read_text(encoding="utf-8"))
        stale["status"] = "running"
        stale["control"]["port"] = _free_tcp_port()
        state_path.write_text(json.dumps(stale), encoding="utf-8")

        # Starting an installed snapshot must not consult changed/missing live recipe authority.
        fixture["system"].unlink()
        restarted = _run_ocean("start", "--workspace", str(fixture["workspace"]), "--json")

        assert restarted.returncode == 0, restarted.stderr
        report = json.loads(restarted.stdout)
        assert report["schema"] == "ellmos.open-ocean-lifecycle-start.v1"
        assert report["runtime"] == {
            "id": "ellmos-core",
            "status": "running",
            "url": f"http://127.0.0.1:{port}",
            "health": "ok",
        }
        status = _run_ocean("status", "--workspace", str(fixture["workspace"]), "--json")
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout)["runtime"]["health"] == "ok"
    finally:
        _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")


def test_start_lock_is_exclusive_per_workspace(tmp_path):
    """Two starters on one workspace: the second fails closed instead of racing the
    empty-state preflight; once the first releases, a later start proceeds."""
    with _start_lock(tmp_path):
        with pytest.raises(LifecycleError, match="läuft bereits ein OCEAN-Start"):
            with _start_lock(tmp_path):
                pass
    with _start_lock(tmp_path):
        pass


def test_start_fails_closed_while_another_process_holds_the_workspace_lock(tmp_path):
    """End to end: `ocean start` in a second process must not spawn a supervisor while
    a starter holds the workspace lock, and must succeed once it is released."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--workspace", str(fixture["workspace"]),
    ]
    try:
        up = _run_ocean("up", *common, "--host", "127.0.0.1", "--port", str(port), "--apply", "--json")
        assert up.returncode == 0, up.stderr
        down = _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")
        assert down.returncode == 0, down.stderr

        with _start_lock(fixture["workspace"]):
            blocked = _run_ocean("start", "--workspace", str(fixture["workspace"]), "--json")
        assert blocked.returncode != 0
        assert "läuft bereits ein OCEAN-Start" in blocked.stderr
        state = json.loads((fixture["workspace"] / "ocean.runtime.json").read_text(encoding="utf-8"))
        assert state["status"] == "stopped"

        restarted = _run_ocean("start", "--workspace", str(fixture["workspace"]), "--json")
        assert restarted.returncode == 0, restarted.stderr
        assert json.loads(restarted.stdout)["runtime"]["health"] == "ok"
    finally:
        _run_ocean("down", "--workspace", str(fixture["workspace"]), "--json")


def test_up_rejects_a_non_loopback_host_at_the_parser():
    """Catches accepting --host values the lifecycle will refuse anyway.

    `up` used to declare --host without choices while `start` already had them,
    so a wrong value was accepted by the parser and only died deep inside
    _assert_runtime_start_available. The realistic wrong value is
    `--host claude-code`: tools/ocean_dev.py has a same-named flag that means a
    skill-host adapter, not a network bind (T-20260830-639732633).
    """
    proc = subprocess.run(
        [sys.executable, str(OCEAN), "up", "--host", "claude-code"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--host" in proc.stderr
    assert "claude-code" in proc.stderr
    assert "127.0.0.1" in proc.stderr


def test_up_withholds_the_runtime_when_required_components_are_missing(tmp_path):
    """Catches starting a runtime on an incomplete composition.

    lifecycle_plan always computed readiness.required_components_missing, but
    up_from_paths never read it and called start_runtime unconditionally -- a
    failed provider fetch produced a runtime that reports "running" while the
    composition is incomplete (T-20260830-639732633).
    """
    unvollstaendig = {
        "readiness": {
            "runtime_host": True,
            "required_components_missing": ["module:ellmos-core", "skill:assist:buero"],
            "full_composition": False,
        }
    }

    with pytest.raises(LifecycleError) as fehler:
        _assert_composition_complete(unvollstaendig, tmp_path)

    meldung = str(fehler.value)
    assert "NICHT gestartet" in meldung
    assert "module:ellmos-core" in meldung
    assert "skill:assist:buero" in meldung
    assert "ocean start" in meldung


def test_up_starts_normally_when_the_composition_is_complete(tmp_path):
    """The gate must not fire on a healthy composition -- otherwise it blocks every up."""
    vollstaendig = {
        "readiness": {
            "runtime_host": True,
            "required_components_missing": [],
            "full_composition": True,
        }
    }

    assert _assert_composition_complete(vollstaendig, tmp_path) is None
