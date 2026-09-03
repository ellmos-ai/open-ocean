"""User-facing OCEAN lifecycle CLI acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.ocean_lifecycle import (
    LifecycleError,
    RuntimeProvider,
    _assert_composition_complete,
    _ellmos_core_runtime_spec,
    _restrict_to_current_user_windows,
    _start_lock,
    _write_json_private,
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
    assert "--source-pins" in proc.stdout
    assert "exaktes OCEAN-Integrations-Overlay" in proc.stdout
    assert "\ufffd" not in proc.stdout
    assert "\ufffd" not in proc.stderr


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_fixture(recipe: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=recipe,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout.strip()


def _seal_recipe_fixture(fixture: dict[str, Path]) -> None:
    recipe = fixture["bundles_root"]
    if not (recipe / ".git").exists():
        _git_fixture(recipe, "init", "--initial-branch=main")
        _git_fixture(recipe, "config", "user.name", "OCEAN Test")
        _git_fixture(recipe, "config", "user.email", "ocean-test@example.invalid")
        _git_fixture(recipe, "remote", "add", "origin", "https://example.invalid/recipe.git")
    _git_fixture(recipe, "add", ".")
    _git_fixture(recipe, "commit", "--no-gpg-sign", "-m", "seal fixture recipe")
    commit = _git_fixture(recipe, "rev-parse", "HEAD")
    bindings = json.loads(fixture["provider_bindings"].read_text(encoding="utf-8"))
    crosswalk_hash = _sha256(fixture["crosswalk"].read_bytes())
    registry_hash = _sha256(fixture["skills"].read_bytes())
    registry_uri = bindings["sources"]["registry:skills-components"]["uri"]
    contract = {
        "schema": "ellmos.open-ocean-source-pins.v1",
        "id": "fixture-source-pins",
        "version": "1.0.0",
        "authority": {"kind": "integration-pin", "runtime_authority": False},
        "recipe": {
            "repository": "https://example.invalid/recipe.git",
            "commit": commit,
            "component_bindings": {
                "path": "manifests/component.registry.bindings.v1.json",
                "content_hash": bindings["content_hash"],
            },
            "skills_crosswalk": {
                "path": "manifests/skills.registry.crosswalk.v1.json",
                "sha256": crosswalk_hash,
            },
        },
        "skills_registry": {"uri": registry_uri, "sha256": registry_hash},
    }
    contract["content_hash"] = canonical_hash(contract)
    fixture["source_pins"].write_text(json.dumps(contract), encoding="utf-8")


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
    crosswalk = bundles_root / "manifests" / "skills.registry.crosswalk.v1.json"
    crosswalk.write_text(json.dumps({"skills": []}), encoding="utf-8")
    registry_uri = (
        "repo://ellmos-ai/skills@"
        "08e1fe212d58075bc00e2f8403c104a507857c05/registry/components.json"
    )
    provider_bindings = bundles_root / "manifests" / "component.registry.bindings.v1.json"
    provider_binding = {
        "schema": "ellmos.component-registry-bindings.v1",
        "sources": {
            "registry:skills-components": {
                "uri": registry_uri,
                "sha256": _sha256(skills.read_bytes()),
            },
            "crosswalk:skills": {
                "uri": "repo://manifests/skills.registry.crosswalk.v1.json",
                "sha256": _sha256(crosswalk.read_bytes()),
            },
        },
    }
    provider_binding["content_hash"] = canonical_hash(provider_binding)
    provider_bindings.write_text(json.dumps(provider_binding), encoding="utf-8")
    fixture = {
        "bundles_root": bundles_root,
        "system": system,
        "catalog": catalog,
        "skills": skills,
        "workspace": root / "workspace",
        "provider_bindings": provider_bindings,
        "crosswalk": crosswalk,
        "source_pins": root / "source-pins.json",
    }
    _seal_recipe_fixture(fixture)
    return fixture


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
    _seal_recipe_fixture(fixture)
    return fixture


def _free_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_ocean(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(OCEAN), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
    )


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


def test_write_json_private_sets_owner_only_permissions_at_creation(tmp_path):
    """T-20260903-113508213 Blocker 1: a secret-bearing file must never
    exist, even briefly, with default/wider permissions. On POSIX the mode
    comes from the os.open() syscall that creates the file. On Windows,
    where that mode is meaningless, icacls.exe must be invoked instead."""
    target = tmp_path / "ocean.runtime-spec.json"

    with patch("tools.ocean_lifecycle._restrict_to_current_user_windows") as restrict:
        _write_json_private(target, {"token": "secret"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"token": "secret"}
    if os.name == "nt":
        restrict.assert_called_once()
    else:
        restrict.assert_not_called()
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_restrict_to_current_user_windows_invokes_icacls_with_an_owner_only_grant(tmp_path):
    target = tmp_path / "ocean.runtime-spec.json"
    target.write_text("{}", encoding="utf-8")

    with patch.dict(os.environ, {"USERNAME": "tester"}), \
            patch("tools.ocean_lifecycle.subprocess.run") as run:
        _restrict_to_current_user_windows(target)

    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[0] == "icacls"
    assert command[1] == str(target)
    assert "/inheritance:r" in command
    assert "tester:F" in command


def test_plan_proves_one_runtime_host_without_creating_the_workspace(tmp_path):
    """Catches treating a verified recipe as usable without a runnable host."""
    fixture = _write_plan_fixture(tmp_path)

    proc = _run_ocean(
        "plan",
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--source-pins", str(fixture["source_pins"]),
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
    assert report["transaction"]["source_pins"]["status"] == "verified"
    assert not fixture["workspace"].exists()


def test_up_rejects_registry_drift_before_fetch_or_workspace_writes(tmp_path):
    """The product lifecycle must never turn a stale registry pin into an apply."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    fixture["skills"].write_text(
        json.dumps({"components": [{"id": "unreviewed-drift"}]}),
        encoding="utf-8",
    )

    proc = _run_ocean(
        "up",
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--source-pins", str(fixture["source_pins"]),
        "--workspace", str(fixture["workspace"]),
        "--port", str(_free_tcp_port()),
        "--apply",
        "--json",
    )

    assert proc.returncode == 3
    assert "Skills Registry SHA-256 mismatch" in proc.stderr
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
        "--source-pins", str(fixture["source_pins"]),
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
        # T-20260903-113508213 Blocker 1: the control-channel bearer token
        # used to live in this file too. It is handed to the supervisor via
        # an env var instead -- if that handoff were broken, status/down/
        # user-add below (all authenticated over that channel) would fail.
        assert "token" not in runtime_spec
        if os.name != "nt":
            spec_path = fixture["workspace"] / "ocean.runtime-spec.json"
            assert stat.S_IMODE(spec_path.stat().st_mode) == 0o600

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


def test_second_up_rejects_a_running_runtime_before_fetch_or_activate(tmp_path):
    """A running sandbox is a write preflight gate, not a late start error."""
    fixture = _write_runnable_ellmos_core_fixture(tmp_path)
    port = _free_tcp_port()
    common = [
        "--bundles-root", str(fixture["bundles_root"]),
        "--system-manifest", str(fixture["system"]),
        "--modules-catalog", str(fixture["catalog"]),
        "--skills-registry", str(fixture["skills"]),
        "--source-pins", str(fixture["source_pins"]),
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
        "--source-pins", str(fixture["source_pins"]),
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
        "--source-pins", str(fixture["source_pins"]),
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
