"""User-facing OCEAN lifecycle CLI acceptance tests."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from tools.ocean_lifecycle import RuntimeProvider, _ellmos_core_runtime_spec
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
