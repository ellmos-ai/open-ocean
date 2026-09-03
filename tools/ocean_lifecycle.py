"""User-facing lifecycle orchestration built on the Open Ocean transaction engine.

This module deliberately does not duplicate Resolve, Verify, Fetch, Place, Activate,
or Roll back.  It invokes :mod:`tools.ocean_dev` as the transaction boundary and adds
the missing product concern: selecting and operating one declared ``runtime.host``.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tools.source_pins import DEFAULT_SOURCE_PINS


TOOLS_DIR = Path(__file__).resolve().parent
TRANSACTION_CLI = TOOLS_DIR / "ocean_dev.py"
SUPERVISOR_CLI = TOOLS_DIR / "runtime_supervisor.py"
RUNTIME_USER_CLI = TOOLS_DIR / "runtime_user.py"
OCEAN_RUNTIME_CLI = TOOLS_DIR / "ocean_runtime.py"
INSTALL_STATE = "ocean.install.json"
RUNTIME_STATE = "ocean.runtime.json"
RUNTIME_SPEC = "ocean.runtime-spec.json"
START_LOCK = "ocean.start.lock"
OCEAN_OPERATOR_PREFIX = "/control"
OCEAN_OPERATOR_TITLE = "OCEAN Full Dev"
OCEAN_OPERATOR_CONFIG = "unified-gui.config.json"


class LifecycleError(RuntimeError):
    """The composition cannot safely advance to the requested lifecycle state."""

    def __init__(self, message: str, *, exit_code: int = 4) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class RuntimeProvider:
    id: str
    ref: str
    local_path: Path
    entrypoints: dict[str, str]
    package: str | None
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ref": self.ref,
            "capability": "runtime.host",
            "local_path": str(self.local_path),
            "entrypoints": self.entrypoints,
            "package": self.package,
        }


def run_transaction(
    *,
    bundles_root: Path,
    system_manifest: Path,
    modules_catalog: Path,
    skills_registry: Path,
    workspace: Path,
    component_bindings: Path | None = None,
    source_pins: Path = DEFAULT_SOURCE_PINS,
    apply: bool = False,
) -> dict[str, Any]:
    """Run the existing transaction CLI and return its JSON report."""
    command = [
        sys.executable,
        str(TRANSACTION_CLI),
        "--bundles-root", str(bundles_root),
        "--system-manifest", str(system_manifest),
        "--modules-catalog", str(modules_catalog),
        "--skills-registry", str(skills_registry),
        "--workspace", str(workspace),
        "--source-pins", str(source_pins),
        "--json",
    ]
    if component_bindings is not None:
        command.extend(["--component-bindings", str(component_bindings)])
    if apply:
        command.append("--apply")
    proc = subprocess.run(
        command,
        cwd=TOOLS_DIR.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "transaction failed without output"
        raise LifecycleError(
            f"Open-Ocean-Transaktion fehlgeschlagen (Exit {proc.returncode}): {detail}",
            exit_code=proc.returncode,
        )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LifecycleError(f"Open-Ocean-Transaktion lieferte kein gültiges JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise LifecycleError("Open-Ocean-Transaktion lieferte kein JSON-Objekt")
    return report


def select_runtime_provider(components: list[dict[str, Any]]) -> RuntimeProvider:
    """Select exactly one resolved module declaring ``runtime.host``."""
    candidates = []
    for component in components:
        detail = component.get("detail") or {}
        if (
            component.get("kind") == "module"
            and component.get("status") == "resolved"
            and "runtime.host" in (detail.get("provides") or [])
        ):
            candidates.append(component)
    if not candidates:
        raise LifecycleError(
            "Die Komposition enthält keinen lokal aufgelösten Anbieter für runtime.host."
        )
    if len(candidates) != 1:
        refs = ", ".join(sorted(str(item.get("ref")) for item in candidates))
        raise LifecycleError(
            f"Die Komposition enthält mehrere runtime.host-Anbieter ({refs}); Auswahl muss deklarativ eindeutig sein."
        )
    component = candidates[0]
    detail = component["detail"]
    raw_path = detail.get("local_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise LifecycleError(f"Runtime-Anbieter {component['ref']} hat keinen lokalen Quellpfad.")
    entrypoints = detail.get("entrypoints") or {}
    if not isinstance(entrypoints, dict) or not entrypoints.get("service"):
        raise LifecycleError(f"Runtime-Anbieter {component['ref']} deklariert keinen Service-Einstieg.")
    return RuntimeProvider(
        id=str(detail.get("catalog_id") or component["ref"].split(":", 1)[-1]),
        ref=str(component["ref"]),
        local_path=Path(raw_path).resolve(strict=False),
        entrypoints={str(k): str(v) for k, v in entrypoints.items()},
        package=str(detail["package"]) if detail.get("package") else None,
        detail=dict(detail),
    )


def lifecycle_plan(transaction_report: dict[str, Any]) -> dict[str, Any]:
    components = transaction_report.get("components")
    if not isinstance(components, list):
        raise LifecycleError("Transaktionsbericht enthält keine Komponentenauflösung.")
    runtime = select_runtime_provider(components)
    required_missing = sorted(
        str(component.get("ref"))
        for component in components
        if component.get("requirement") == "required"
        and component.get("kind") in {"module", "skill"}
        and component.get("status") != "resolved"
    )
    composition = transaction_report.get("composition") or {}
    return {
        "schema": "ellmos.open-ocean-lifecycle-plan.v1",
        "composition": {
            "id": composition.get("id"),
            "mode": composition.get("mode"),
            "schema": composition.get("schema"),
        },
        "runtime": runtime.as_dict(),
        "readiness": {
            "runtime_host": True,
            "required_components_missing": required_missing,
            "full_composition": not required_missing,
        },
        "transaction": transaction_report,
    }


def plan_from_paths(
    *,
    bundles_root: Path,
    system_manifest: Path,
    modules_catalog: Path,
    skills_registry: Path,
    workspace: Path,
    component_bindings: Path | None = None,
    source_pins: Path = DEFAULT_SOURCE_PINS,
) -> dict[str, Any]:
    return lifecycle_plan(run_transaction(
        bundles_root=bundles_root,
        system_manifest=system_manifest,
        modules_catalog=modules_catalog,
        skills_registry=skills_registry,
        workspace=workspace,
        component_bindings=component_bindings,
        source_pins=source_pins,
        apply=False,
    ))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _restrict_to_current_user_windows(path: Path) -> None:
    """Best-effort ACL lockdown for a secret-bearing file on Windows, where
    chmod()/Path.chmod() only ever toggle the read-only attribute bit and
    grant no real access control. Uses the platform's own icacls.exe (no new
    dependency): drop inherited ACEs and grant only the current user access.
    (T-20260903-113508213 Blocker 1)"""
    username = os.environ.get("USERNAME")
    if not username:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True, check=False,
        )
    except OSError:
        pass


def _write_json_private(path: Path, value: dict[str, Any]) -> None:
    """Like _write_json_atomic, but for a file whose content is a secret:
    permissions are set AT CREATION, not after the fact -- a chmod() called
    once write_text() has already created the file leaves a window where it
    briefly carries the default, wider permissions. POSIX gets the mode from
    the os.open() syscall itself; Windows (where that mode is meaningless)
    gets an owner-only ACL. (T-20260903-113508213 Blocker 1)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    if os.name == "nt":
        _restrict_to_current_user_windows(temporary)
    temporary.replace(path)


def write_runtime_projection(
    workspace: Path,
    transaction_report: dict[str, Any],
) -> tuple[Path, Path]:
    """Create the read-only compatibility projection consumed by ellmos-core's module page."""
    components = transaction_report["components"]
    fetch_by_ref = {item["ref"]: item for item in transaction_report.get("fetch", [])}
    modules = []
    locked = []
    for component in components:
        if component.get("kind") != "module":
            continue
        detail = component.get("detail") or {}
        binding = detail.get("binding") or {}
        module_id = str(
            binding.get("placement_id")
            or detail.get("catalog_id")
            or component["ref"].split(":", 1)[-1]
        )
        fetch = fetch_by_ref.get(component["ref"], {})
        fetch_action = fetch.get("action")
        resolved = component.get("status") == "resolved" or fetch_action in {
            "fetched",
            "present-pinned-provider",
        }
        optional = component.get("requirement") == "optional"
        fetch_detail = fetch.get("detail") or {}
        source_path = (
            fetch_detail.get("dest")
            if fetch_action in {"fetched", "present-pinned-provider"}
            else detail.get("local_path")
        )
        modules.append({
            "name": module_id,
            "kind": detail.get("kind") or "module",
            "bundles": component.get("from_bundles") or [],
            "enabled": resolved or not optional,
            "source": {
                "type": detail.get("source_type") or "unresolved",
                "repo": detail.get("repository"),
                "path": source_path,
            },
            "boundaries": {
                "net": (detail.get("boundaries") or {}).get("network", ""),
                "targets": [],
            },
            "wiring": {
                "provides": detail.get("provides") or [],
                "consumes": detail.get("requires") or [],
            },
        })
        if resolved:
            if fetch_action == "fetched":
                status = "cloned"
            elif fetch_action == "present-pinned-provider":
                status = "pinned-local"
            else:
                status = "local-present"
        else:
            status = "skipped" if optional else "error"
        locked.append({"name": module_id, "status": status})

    composition = transaction_report.get("composition") or {}
    manifest = {
        "schema": "ellmos-sovereign-manifest-v1",
        "name": composition.get("id") or "open-ocean",
        "tier": "DEV",
        "authority": "compatibility-projection-only",
        "modules": modules,
    }
    lock = {
        "schema": "ellmos.open-ocean-runtime-lock.v1",
        "manifest": manifest["name"],
        "tier": "DEV",
        "modules": locked,
    }
    manifest_path = workspace / "sovereign.manifest.json"
    lock_path = workspace / "sovereign.lock.json"
    _write_json_atomic(manifest_path, manifest)
    _write_json_atomic(lock_path, lock)
    return manifest_path, lock_path


def _ellmos_core_runtime_spec(
    provider: RuntimeProvider,
    components: list[dict[str, Any]],
    workspace: Path,
    manifest_path: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    if provider.id != "ellmos-core":
        raise LifecycleError(
            f"Für runtime.host {provider.id!r} ist noch kein OCEAN-Laufzeitadapter registriert."
        )
    package_root = provider.local_path / "src" / "ellmos_core"
    if not package_root.is_dir():
        raise LifecycleError(f"ellmos-core-Paket nicht unter {package_root} gefunden.")
    python_paths = []
    for component in components:
        if component.get("kind") != "module" or component.get("status") != "resolved":
            continue
        raw = (component.get("detail") or {}).get("local_path")
        if raw:
            source_dir = Path(raw) / "src"
            if source_dir.is_dir():
                python_paths.append(str(source_dir.resolve(strict=False)))
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        python_paths.append(inherited)
    base_url = f"http://{host}:{port}"
    operator_components = []
    for component in components:
        if component.get("kind") != "module" or component.get("status") != "resolved":
            continue
        detail = component.get("detail") or {}
        provides = set(detail.get("provides") or [])
        if "unified-gui.host" in provides:
            operator_components.append(component)
    if len(operator_components) > 1:
        refs = ", ".join(sorted(str(item.get("ref")) for item in operator_components))
        raise LifecycleError(
            f"Die Komposition enthält mehrere Operator-Oberflächen ({refs}); Auswahl muss eindeutig sein."
        )
    operator_enabled = bool(operator_components)
    if operator_enabled:
        operator_detail = operator_components[0].get("detail") or {}
        raw_operator_path = operator_detail.get("local_path")
        if not isinstance(raw_operator_path, str) or not raw_operator_path:
            raise LifecycleError("Die deklarierte OCEAN-Operator-Oberfläche hat keinen lokalen Quellpfad.")
        operator_path = Path(raw_operator_path) / "src" / "unified_gui"
        if not operator_path.is_dir():
            raise LifecycleError(
                f"Die deklarierte OCEAN-Operator-Oberfläche fehlt unter {operator_path}."
            )
    runtime_url = f"{base_url}{OCEAN_OPERATOR_PREFIX}/" if operator_enabled else base_url
    runtime_env = {
        "PYTHONPATH": os.pathsep.join(dict.fromkeys(python_paths)),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "ELLMOS_CORE_DEBUG": "0",
        "ELLMOS_CORE_SECRET_KEY": secrets.token_urlsafe(48),
        "ELLMOS_CORE_SECURE_COOKIES": "0",
        "ELLMOS_CORE_HOST": host,
        "ELLMOS_CORE_PORT": str(port),
        "ELLMOS_CORE_DB_PATH": str((workspace / "state" / "ellmos_core.db").resolve(strict=False)),
        "ELLMOS_CORE_MANIFEST_PATH": str(manifest_path.resolve(strict=False)),
    }
    if operator_enabled:
        _write_json_atomic(
            workspace / OCEAN_OPERATOR_CONFIG,
            {"title": OCEAN_OPERATOR_TITLE},
        )
        runtime_env.update({
            "ELLMOS_CORE_CONSOLE_ENABLED": "1",
            "ELLMOS_CORE_CONSOLE_PREFIX": OCEAN_OPERATOR_PREFIX,
            "OCEAN_OPERATOR_TITLE": OCEAN_OPERATOR_TITLE,
        })
    runtime_command = (
        [sys.executable, str(OCEAN_RUNTIME_CLI)]
        if operator_enabled
        else [sys.executable, "-m", "ellmos_core.cli", "serve"]
    )
    return {
        "runtime_id": provider.id,
        "command": runtime_command,
        "cwd": str(workspace.resolve(strict=False) if operator_enabled else provider.local_path),
        "env": runtime_env,
        "runtime_url": runtime_url,
        "health_url": f"{base_url}/api/health",
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Lokaler OCEAN-Status ist nicht lesbar: {path}: {exc}", exit_code=3) from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"Lokaler OCEAN-Status ist kein JSON-Objekt: {path}", exit_code=3)
    return value


def _control_request(state: dict[str, Any], action: str, timeout: float = 2.0) -> dict[str, Any]:
    control = state.get("control") or {}
    host, port, token = control.get("host"), control.get("port"), control.get("token")
    if host != "127.0.0.1" or not isinstance(port, int) or not isinstance(token, str):
        raise LifecycleError("Runtime-Status enthält keinen gültigen lokalen Kontrollkanal.", exit_code=3)
    method = "POST" if action == "stop" else "GET"
    request = urllib.request.Request(
        f"http://{host}:{port}/{action}",
        method=method,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Authentifizierter OCEAN-Kontrollkanal nicht erreichbar: {exc}", exit_code=3) from exc


def _health(health_url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def _tcp_endpoint_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _runtime_endpoint_open(state: dict[str, Any]) -> bool:
    try:
        parsed = urlsplit(str(state.get("runtime_url") or ""))
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise LifecycleError("Runtime-Status enthält keinen gültigen öffentlichen Endpunkt.", exit_code=3) from exc
    if host not in {"127.0.0.1", "localhost"} or port is None:
        raise LifecycleError("Runtime-Status enthält keinen gültigen lokalen öffentlichen Endpunkt.", exit_code=3)
    return _tcp_endpoint_open(host, port)


def _assert_runtime_start_available(workspace: Path, *, host: str, port: int) -> None:
    """Fail before composition writes when this sandbox cannot start safely.

    ``up`` runs this once before the transaction and ``start_runtime`` repeats it
    immediately before spawning. The second check closes the race in which a port
    becomes occupied while Resolve/Verify/Fetch/Activate is running.
    """
    if host not in {"127.0.0.1", "localhost"}:
        raise LifecycleError("OCEAN Full Dev bindet in diesem Bauabschnitt ausschließlich an Loopback.")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise LifecycleError(f"Ungültiger OCEAN-Port: {port}", exit_code=2)

    state_path = workspace / RUNTIME_STATE
    if state_path.exists():
        existing = _read_json(state_path)
        if existing.get("status") == "running":
            try:
                if _control_request(existing, "status").get("status") == "running":
                    raise LifecycleError("In dieser Sandbox läuft bereits eine OCEAN-Laufzeit.")
            except LifecycleError as exc:
                if "läuft bereits" in str(exc):
                    raise
                # A stop that just landed can still look "busy" for a beat
                # (socket teardown in flight, OS scheduling under load) even
                # though the runtime is already gone -- a single snapshot
                # reading right after a control-channel failure isn't proof
                # of a live process, only of a moment in time. Re-check a few
                # times before treating it as a real blocker
                # (T-20260903-224229063: this exact race left a dead runtime
                # looking "busy" long enough to refuse a legitimate restart).
                still_busy = True
                for attempt in range(5):
                    still_busy = (
                        _health(str(existing.get("health_url") or ""))
                        or _runtime_endpoint_open(existing)
                        or _tcp_endpoint_open(host, port)
                    )
                    if not still_busy or attempt == 4:
                        break
                    time.sleep(0.3)
                if still_busy:
                    raise LifecycleError(
                        "Vorhandener Runtime-Status ist nicht kontrollierbar, aber der Runtime-Port ist belegt; "
                        "kein zweiter Prozess wird gestartet."
                    ) from exc
    if _tcp_endpoint_open(host, port):
        raise LifecycleError(
            f"Der angeforderte OCEAN-Port {host}:{port} ist bereits belegt; Start abgebrochen."
        )


@contextlib.contextmanager
def _start_lock(workspace: Path):
    """Exclusive, OS-held start lock for one workspace.

    Two direct lifecycle invocations could both pass the empty-state preflight
    before either supervisor wrote ``ocean.runtime.json`` and end up with two
    supervisors on one sandbox. The lock closes that window: it is taken before
    the preflight and held until the runtime state is green or the start failed.
    It is a byte-range/flock lock on an open handle, so the OS drops it when the
    holder dies -- a crashed starter never leaves a stale lock behind.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    handle = (workspace / START_LOCK).open("a+b")
    try:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LifecycleError(
                "In dieser Sandbox läuft bereits ein OCEAN-Start; kein zweiter Prozess wird gestartet."
            ) from exc
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass  # closing the handle releases the lock anyway
        handle.close()


DEFAULT_HEALTH_TIMEOUT = 60.0
"""How long start_runtime() waits for a green health status before giving up
and tearing the child back down. Was 20.0 -- too tight for a real Python
interpreter start (imports, DB init, uvicorn boot) on a host doing anything
else at the same time: an `up --apply` on a laptop already running two other
agent processes plus pytest missed a 20s window and destroyed a runtime that
`ocean.py start` then brought up cleanly moments later on the identical,
unchanged install (T-20260903-224229063). 60s is a deliberate, overridable
default (--health-timeout), not a silent bump -- a process that is truly
dead fails fast regardless (see the `status == "stopped"` break below), so a
generous ceiling only matters for the genuinely-just-slow case this exists
to stop misdiagnosing as broken."""


def start_runtime(
    provider: RuntimeProvider,
    components: list[dict[str, Any]],
    workspace: Path,
    manifest_path: Path,
    *,
    host: str,
    port: int,
    startup_timeout: float = DEFAULT_HEALTH_TIMEOUT,
) -> dict[str, Any]:
    """Spawn the supervisor under the workspace start lock (see ``_start_lock``)."""
    # A non-positive or non-finite startup_timeout (0, negative, NaN, +-inf)
    # makes `deadline = time.monotonic() + startup_timeout` already-past (or,
    # for inf, never-past) before the poll loop's first iteration -- the loop
    # then never runs even once, so it never attempts the stop-and-report
    # path either. The supervisor is spawned unconditionally before that loop
    # starts, so the result was a live orphaned process while the caller was
    # told the start failed (T-20260903-224229063 Blocker 1). Reject here,
    # before the lock is even taken and nothing has been started yet, rather
    # than adding a cleanup path in the timeout branch.
    if not (math.isfinite(startup_timeout) and startup_timeout > 0):
        raise LifecycleError(
            f"--health-timeout muss eine positive, endliche Zahl sein, nicht {startup_timeout!r}.",
            exit_code=2,
        )
    with _start_lock(workspace):
        return _start_runtime_locked(
            provider,
            components,
            workspace,
            manifest_path,
            host=host,
            port=port,
            startup_timeout=startup_timeout,
        )


def _start_runtime_locked(
    provider: RuntimeProvider,
    components: list[dict[str, Any]],
    workspace: Path,
    manifest_path: Path,
    *,
    host: str,
    port: int,
    startup_timeout: float = DEFAULT_HEALTH_TIMEOUT,
) -> dict[str, Any]:
    _assert_runtime_start_available(workspace, host=host, port=port)
    state_path = workspace / RUNTIME_STATE

    launch = _ellmos_core_runtime_spec(provider, components, workspace, manifest_path, host, port)
    token = secrets.token_urlsafe(32)
    spec = {
        "schema": "ellmos.open-ocean-runtime-spec.v1",
        "instance_id": str(uuid.uuid4()),
        **launch,
        "state_path": str(state_path.resolve(strict=False)),
        "log_path": str((workspace / "logs" / "runtime.log").resolve(strict=False)),
    }
    # The bearer token used to be written into the spec file too, but nothing
    # else ever reads it from there -- only the supervisor we are about to
    # spawn, and only once, right after start. Handing it over as an env var
    # to that direct child means the control-channel secret never touches
    # disk at all here (T-20260903-113508213 Blocker 1). ELLMOS_CORE_SECRET_KEY
    # (inside `launch["env"]`) stays in the file: a later, independent
    # `ocean user add` invocation reads it back from RUNTIME_SPEC with no
    # process relationship to this one to inherit an env var from.
    spec_path = workspace / RUNTIME_SPEC
    _write_json_private(spec_path, spec)
    supervisor_log = workspace / "logs" / "supervisor.log"
    supervisor_log.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    supervisor_env = os.environ.copy()
    supervisor_env["OCEAN_RUNTIME_TOKEN"] = token
    with supervisor_log.open("ab", buffering=0) as log_handle:
        subprocess.Popen(
            [sys.executable, str(SUPERVISOR_CLI), "--spec", str(spec_path)],
            cwd=TOOLS_DIR.parent,
            env=supervisor_env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
            creationflags=creationflags,
        )
    deadline = time.monotonic() + startup_timeout
    runtime_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if state_path.is_file():
            runtime_state = _read_json(state_path)
            if runtime_state.get("instance_id") != spec["instance_id"]:
                time.sleep(0.1)
                continue
            try:
                control = _control_request(runtime_state, "status", timeout=0.5)
            except LifecycleError:
                control = {}
            if control.get("status") == "running" and _health(launch["health_url"], timeout=0.5):
                return runtime_state
            if runtime_state.get("status") == "stopped":
                break
        time.sleep(0.1)
    if runtime_state and runtime_state.get("status") == "running":
        try:
            _control_request(runtime_state, "stop")
        except LifecycleError:
            pass
    runtime_log = workspace / "logs" / "runtime.log"
    try:
        runtime_log_size = runtime_log.stat().st_size
    except OSError:
        runtime_log_size = 0
    # A completely silent runtime.log after `startup_timeout` (child never got
    # to its first line of output) is a materially different situation from
    # one that is actively logging -- distinguishes "not even initializing"
    # from "slow, but making progress" (T-20260903-224229063).
    child_diagnosis = (
        f"{runtime_log} ist leer (Kindprozess kam nicht bis zur ersten Log-Zeile)"
        if runtime_log_size == 0
        else f"siehe {runtime_log}"
    )
    raise LifecycleError(
        f"OCEAN-Laufzeit erreichte innerhalb von {startup_timeout:g}s keinen grünen Health-Status; "
        f"{child_diagnosis}; Supervisor-Log: {supervisor_log}."
    )


def _assert_composition_complete(plan: dict[str, Any], workspace: Path) -> None:
    """Fail before starting a runtime whose required components are missing.

    ``lifecycle_plan`` already computes ``readiness.required_components_missing``
    and ``readiness.full_composition``, but until T-20260830-639732633 nobody
    read them on the ``up`` path: ``up_from_paths`` returned the readiness block
    and started the runtime regardless. A failed provider fetch therefore left
    the operator with a runtime that reports "running" while the composition is
    incomplete -- the defect had to be found by reading the report afterwards.

    The composition and the install state are written before this gate on
    purpose: the artefacts and the report stay available for diagnosis, only the
    runtime is withheld.
    """
    readiness = plan.get("readiness") or {}
    missing = list(readiness.get("required_components_missing") or [])
    if not missing:
        return
    raise LifecycleError(
        "Komposition unvollständig -- Laufzeit wurde NICHT gestartet. "
        f"Nicht aufgelöste Pflichtkomponenten ({len(missing)}): {', '.join(missing)}. "
        f"Installationsstand und Bericht liegen in {workspace / INSTALL_STATE}; "
        "nach dem Beheben startet 'ocean start --workspace <dir>' die Laufzeit."
    )


def up_from_paths(
    *,
    bundles_root: Path,
    system_manifest: Path,
    modules_catalog: Path,
    skills_registry: Path,
    workspace: Path,
    component_bindings: Path | None = None,
    source_pins: Path = DEFAULT_SOURCE_PINS,
    host: str,
    port: int,
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
) -> dict[str, Any]:
    _assert_runtime_start_available(workspace, host=host, port=port)
    transaction = run_transaction(
        bundles_root=bundles_root,
        system_manifest=system_manifest,
        modules_catalog=modules_catalog,
        skills_registry=skills_registry,
        workspace=workspace,
        component_bindings=component_bindings,
        source_pins=source_pins,
        apply=True,
    )
    plan = lifecycle_plan(transaction)
    provider = select_runtime_provider(transaction["components"])
    manifest_path, lock_path = write_runtime_projection(workspace, transaction)
    install = {
        "schema": "ellmos.open-ocean-install-state.v1",
        "recorded_at": _now(),
        "workspace": str(workspace.resolve(strict=False)),
        "plan": plan,
        "projection": {"manifest": str(manifest_path), "lock": str(lock_path)},
    }
    _write_json_atomic(workspace / INSTALL_STATE, install)
    _assert_composition_complete(plan, workspace)
    runtime_state = start_runtime(
        provider,
        transaction["components"],
        workspace,
        manifest_path,
        host=host,
        port=port,
        startup_timeout=health_timeout,
    )
    return {
        "schema": "ellmos.open-ocean-lifecycle-up.v1",
        "composition": plan["composition"],
        "readiness": plan["readiness"],
        "runtime": {
            "id": provider.id,
            "status": runtime_state["status"],
            "url": runtime_state["runtime_url"],
            "health": "ok",
        },
        "workspace": str(workspace.resolve(strict=False)),
    }


def start_installed_runtime(
    workspace: Path,
    *,
    host: str | None = None,
    port: int | None = None,
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
) -> dict[str, Any]:
    """Start a verified installed snapshot without consulting live recipe authority."""
    install = _read_json(workspace / INSTALL_STATE)
    if install.get("schema") != "ellmos.open-ocean-install-state.v1":
        raise LifecycleError("Die Sandbox enthält keinen unterstützten OCEAN-Installationsstand.", exit_code=3)
    plan = install.get("plan") or {}
    transaction = plan.get("transaction") or {}
    components = transaction.get("components")
    if not isinstance(components, list):
        raise LifecycleError("Der installierte OCEAN-Stand enthält keine Komponentenauflösung.", exit_code=3)

    previous_spec = _read_json(workspace / RUNTIME_SPEC)
    previous_env = previous_spec.get("env") or {}
    selected_host = host or str(previous_env.get("ELLMOS_CORE_HOST") or "127.0.0.1")
    raw_port = port if port is not None else previous_env.get("ELLMOS_CORE_PORT")
    try:
        selected_port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise LifecycleError("Die installierte Runtime enthält keinen gültigen Port.", exit_code=3) from exc
    if not 1 <= selected_port <= 65535:
        raise LifecycleError(f"Ungültiger OCEAN-Port: {selected_port}", exit_code=2)

    live = status_for_workspace(workspace)
    if live["runtime"]["control"] == "running" and live["runtime"]["health"] == "ok":
        current_url = str(live["runtime"].get("url") or "")
        expected_base = f"http://{selected_host}:{selected_port}"
        if not current_url.startswith(expected_base):
            raise LifecycleError(
                "OCEAN läuft bereits an einem anderen Endpunkt; vor einem Portwechsel zuerst 'ocean down' ausführen."
            )
        return {
            "schema": "ellmos.open-ocean-lifecycle-start.v1",
            "runtime": {
                "id": live["runtime"]["id"],
                "status": "running",
                "url": current_url,
                "health": "ok",
            },
            "workspace": str(workspace.resolve(strict=False)),
            "reused": True,
        }

    provider = select_runtime_provider(components)
    manifest_path = workspace / "sovereign.manifest.json"
    if not manifest_path.is_file():
        raise LifecycleError(f"Installierte Runtime-Projektion fehlt: {manifest_path}", exit_code=3)
    runtime_state = start_runtime(
        provider,
        components,
        workspace,
        manifest_path,
        host=selected_host,
        port=selected_port,
        startup_timeout=health_timeout,
    )
    return {
        "schema": "ellmos.open-ocean-lifecycle-start.v1",
        "runtime": {
            "id": provider.id,
            "status": runtime_state["status"],
            "url": runtime_state["runtime_url"],
            "health": "ok",
        },
        "workspace": str(workspace.resolve(strict=False)),
        "reused": False,
    }


def status_for_workspace(workspace: Path) -> dict[str, Any]:
    install = _read_json(workspace / INSTALL_STATE)
    runtime = _read_json(workspace / RUNTIME_STATE)
    control_status = "stopped"
    if runtime.get("status") == "running":
        try:
            control_status = str(_control_request(runtime, "status").get("status", "unavailable"))
        except LifecycleError:
            control_status = "unavailable"
    health = "ok" if control_status == "running" and _health(str(runtime.get("health_url"))) else "unavailable"
    return {
        "schema": "ellmos.open-ocean-lifecycle-status.v1",
        "runtime": {
            "id": runtime.get("runtime_id"),
            "control": control_status,
            "health": health,
            "url": runtime.get("runtime_url"),
        },
        "composition": install["plan"]["composition"],
        "readiness": install["plan"]["readiness"],
        "workspace": str(workspace.resolve(strict=False)),
    }


def down_for_workspace(workspace: Path) -> dict[str, Any]:
    state_path = workspace / RUNTIME_STATE
    runtime = _read_json(state_path)
    if runtime.get("status") != "running":
        return {"schema": "ellmos.open-ocean-lifecycle-down.v1", "stopped": False, "already_stopped": True}
    try:
        result: Any = _control_request(runtime, "stop")
    except LifecycleError as exc:
        # The supervisor terminates the child and answers /stop before it
        # exits and writes the final "stopped" state -- a slow/loaded client
        # can lose that HTTP response even though the stop itself landed.
        # Don't fail closed on the lost reply alone; fall through to the same
        # state-file poll a confirmed response already uses below
        # (T-20260903-224229063 Fall 1: a real stop was reported as a
        # failure, leaving a stale "running" state behind).
        result = str(exc)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        current = _read_json(state_path)
        if current.get("status") == "stopped":
            return {
                "schema": "ellmos.open-ocean-lifecycle-down.v1",
                "stopped": True,
                "runtime_id": current.get("runtime_id"),
            }
        time.sleep(0.05)
    # State file never flipped either -- one more direct signal before
    # failing closed: a listening socket that is truly gone refuses new
    # connections immediately, so a closed port means stopped regardless of
    # what the (possibly stale) state file still says. Correct it so status/
    # a later start don't keep trusting the stale "running" flag.
    if not _runtime_endpoint_open(runtime):
        _write_json_atomic(state_path, {**runtime, "status": "stopped"})
        return {
            "schema": "ellmos.open-ocean-lifecycle-down.v1",
            "stopped": True,
            "runtime_id": runtime.get("runtime_id"),
        }
    raise LifecycleError(f"Runtime meldete Stop, Statusdatei blieb aber aktiv: {result}")


def user_add_for_workspace(
    workspace: Path,
    *,
    username: str,
    email: str,
    role: str,
    password: str,
) -> dict[str, Any]:
    """Delegate local user creation to the selected runtime over stdin."""
    username, email = username.strip(), email.strip()
    if not username or not email:
        raise LifecycleError("Benutzername und E-Mail-Adresse dürfen nicht leer sein.", exit_code=2)
    if role not in {"admin", "user"}:
        raise LifecycleError(f"Unbekannte Rolle: {role!r}", exit_code=2)
    if not password:
        raise LifecycleError("Das Passwort darf nicht leer sein.", exit_code=2)

    live = status_for_workspace(workspace)
    if live["runtime"]["control"] != "running" or live["runtime"]["health"] != "ok":
        raise LifecycleError("Benutzer können nur für eine aktive, gesunde OCEAN-Laufzeit angelegt werden.")
    spec = _read_json(workspace / RUNTIME_SPEC)
    runtime_id = str(spec.get("runtime_id") or "")
    runtime_env = spec.get("env") or {}
    if not runtime_id or not isinstance(runtime_env, dict):
        raise LifecycleError("Runtime-Spezifikation enthält keinen nutzbaren Benutzeradapter.", exit_code=3)

    command = [
        sys.executable,
        str(RUNTIME_USER_CLI),
        "--runtime-id", runtime_id,
        "--username", username,
        "--email", email,
        "--role", role,
    ]
    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in runtime_env.items()})
    proc = subprocess.run(
        command,
        cwd=str(spec.get("cwd") or workspace),
        env=env,
        input=password + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "user creation failed without output"
        raise LifecycleError(
            f"Runtime-Benutzer konnte nicht angelegt werden (Exit {proc.returncode}): {detail}",
            exit_code=proc.returncode,
        )
    return {
        "schema": "ellmos.open-ocean-user-add.v1",
        "runtime_id": runtime_id,
        "username": username,
        "role": role,
        "created": True,
    }
