#!/usr/bin/env python3
"""OCEAN Full Dev lifecycle entry point."""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.ocean_lifecycle import (
    DEFAULT_HEALTH_TIMEOUT,
    LifecycleError,
    down_for_workspace,
    plan_from_paths,
    start_installed_runtime,
    status_for_workspace,
    up_from_paths,
    user_add_for_workspace,
)
from tools.resolve_bundles import DEFAULT_COMPONENT_BINDINGS
from tools.source_pins import DEFAULT_SOURCE_PINS


DEFAULT_OCEAN_PORT = 8810
ROLE_MANIFEST_ENV = "UNIFIED_GUI_ROLE_MANIFESTS"


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


class _TeeWriter:
    """Writes to both an original stream and a log file, tolerating either
    one being unusable. Exists for one reason: under the headless launcher
    that starts OCEAN at logon (pythonw.exe, no console -- see
    EllmosOceanFullUserStart), sys.stderr is a silent sink. A startup
    failure -- the handled LifecycleError print() in main() below, or an
    unhandled traceback via Python's default excepthook, which also writes
    to sys.stderr -- would otherwise vanish, leaving only a bare process
    exit code with no diagnostic (T-20260902-313385481)."""

    def __init__(self, original, log_handle) -> None:
        self._original = original
        self._log = log_handle

    def write(self, data: str) -> int:
        for stream in (self._original, self._log):
            if stream is None:
                continue
            try:
                stream.write(data)
                stream.flush()
            except OSError:
                pass
        return len(data)

    def flush(self) -> None:
        for stream in (self._original, self._log):
            if stream is None:
                continue
            try:
                stream.flush()
            except OSError:
                pass


def _attach_stderr_log(workspace: Path) -> None:
    """Tee sys.stderr into <workspace>/logs/runtime.log -- the same file
    tools/runtime_supervisor.py already redirects the supervised runtime
    child's own stdout/stderr to -- so a headless 'ocean.py start' failure
    is findable after the fact. Scoped to the 'start' command only: that is
    the one Scheduled Tasks actually invoke unattended (via pythonw.exe);
    every other command still runs interactively with a real console."""
    log_path = workspace / "logs" / "runtime.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8", errors="replace")
    log_handle.write(f"\n=== ocean.py start stderr @ {datetime.now(timezone.utc).isoformat()} ===\n")
    log_handle.flush()
    sys.stderr = _TeeWriter(sys.stderr, log_handle)


def _add_composition_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundles-root", type=Path, required=True)
    parser.add_argument("--system-manifest", type=Path, required=True)
    parser.add_argument("--modules-catalog", type=Path, required=True)
    parser.add_argument("--skills-registry", type=Path, required=True)
    parser.add_argument(
        "--component-bindings",
        type=Path,
        default=DEFAULT_COMPONENT_BINDINGS,
        help="exaktes OCEAN-Integrations-Overlay für deklarierte Komponenten",
    )
    parser.add_argument(
        "--source-pins",
        type=Path,
        default=DEFAULT_SOURCE_PINS,
        help="selbst gehashter Quellenvertrag; wird vor Resolve und Fetch geprüft",
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocean",
        description="OCEAN Full Dev planen, starten, prüfen und kontrolliert beenden.",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    plan = commands.add_parser("plan", help="Komposition und Laufzeit rein lesend prüfen")
    _add_composition_arguments(plan)
    up = commands.add_parser("up", help="OCEAN in einer lokalen Sandbox installieren und starten")
    _add_composition_arguments(up)
    # choices bewusst identisch zu `start` (siehe unten): die Laufzeit bindet
    # ausschliesslich an Loopback (_assert_runtime_start_available). Ohne choices
    # nahm der Parser jeden Wert an und der Lauf starb erst tief im Lifecycle --
    # z.B. bei `--host claude-code`, das aus der Verwechslung mit dem
    # gleichnamigen, aber voellig anderen `--host` in tools/ocean_dev.py stammt
    # (dort: Skill-Host-Adapter, nicht Netzwerk-Bind). T-20260830-639732633.
    up.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    up.add_argument(
        "--port",
        type=int,
        default=DEFAULT_OCEAN_PORT,
        help=f"dedizierter OCEAN-Port (Standard: {DEFAULT_OCEAN_PORT}; getrennt von ellmos-core/TerminPilot)",
    )
    up.add_argument("--apply", action="store_true", help="Transaktion und Laufzeit wirklich starten")
    up.add_argument(
        "--health-timeout",
        type=float,
        default=DEFAULT_HEALTH_TIMEOUT,
        help=(
            "Sekunden bis zum gruenen Health-Status, bevor die Laufzeit wieder "
            f"abgebaut wird (Standard: {DEFAULT_HEALTH_TIMEOUT:g}s; T-20260903-224229063: "
            "ein belasteter Host kann laenger brauchen, ohne dass der Start wirklich haengt)"
        ),
    )
    start = commands.add_parser(
        "start",
        help="installierten OCEAN-Stand oder eine deklarierte Modulrolle starten",
    )
    start.add_argument("role", nargs="?", help="optionale Rollen-ID fuer das Konsolenstartfenster")
    start.add_argument("--workspace", type=Path)
    start.add_argument("--host", choices=["127.0.0.1", "localhost"])
    start.add_argument("--port", type=int, help="optional neuer Port; sonst wird der installierte Port verwendet")
    start.add_argument(
        "--health-timeout",
        type=float,
        default=DEFAULT_HEALTH_TIMEOUT,
        help="siehe 'ocean up --health-timeout'",
    )
    start.add_argument("--json", action="store_true")
    start.add_argument("--manifest", action="append", default=[], help="roles[]-Modulmanifest; wiederholbar")
    start.add_argument("--provider", help="Anbieter fuer den Rollenstart")
    start.add_argument("--model", default="", help="optionales Modell nur fuer diesen Rollenstart")
    start.add_argument("--effort", default="", help="optionaler Effort nur fuer diesen Rollenstart")
    start.add_argument("--request", default="", help="optionaler Nutzerauftrag statt Manifest-Default")
    start.add_argument("--cwd", type=Path, help="Arbeitsverzeichnis der Rolle")
    start.add_argument("--name", default="", help="Name des Rollenprozesses")
    start.add_argument("--dry-run", action="store_true", help="Rollenstart nur anzeigen")
    status = commands.add_parser("status", help="Installations- und Laufzeitstatus live prüfen")
    status.add_argument("--workspace", type=Path, required=True)
    status.add_argument("--json", action="store_true")
    down = commands.add_parser("down", help="Nur die zugehörige OCEAN-Laufzeit kontrolliert beenden")
    down.add_argument("--workspace", type=Path, required=True)
    down.add_argument("--json", action="store_true")
    user = commands.add_parser("user", help="Benutzer der aktiven OCEAN-Laufzeit verwalten")
    user_add = user.add_subparsers(dest="user_command", metavar="COMMAND").add_parser(
        "add", help="Benutzer mit verdeckter Passworteingabe anlegen"
    )
    user_add.add_argument("--workspace", type=Path, required=True)
    user_add.add_argument("--username", required=True)
    user_add.add_argument("--email", required=True)
    user_add.add_argument("--role", choices=["admin", "user"], default="admin")
    user_add.add_argument(
        "--password-stdin",
        action="store_true",
        help="Passwort aus der Standardeingabe lesen (für lokale Automatisierung)",
    )
    user_add.add_argument("--json", action="store_true")
    return parser


def _role_console_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, "-m", "unified_gui.console", "start", args.role]
    for manifest in args.manifest:
        command.extend(["--manifest", str(Path(manifest).expanduser().resolve())])
    for flag, value in (
        ("--provider", args.provider),
        ("--model", args.model),
        ("--effort", args.effort),
        ("--request", args.request),
        ("--cwd", args.cwd),
        ("--name", args.name),
    ):
        if value:
            command.extend([flag, str(value)])
    if args.dry_run:
        command.append("--dry-run")
    return command


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _fallback_role_command(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """Enger Notweg ohne unified-gui; liest nur denselben roles[]-Datensatz."""
    raw_manifests = list(args.manifest)
    if not raw_manifests:
        raw_manifests = [
            value for value in os.environ.get(ROLE_MANIFEST_ENV, "").split(os.pathsep)
            if value
        ]
    matches: list[tuple[str, dict, Path]] = []
    wanted = str(args.role).strip().lower()
    for raw_path in raw_manifests:
        path = Path(raw_path).expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Rollenmanifest nicht lesbar: {path}: {exc}") from exc
        module_id = str(payload.get("id") or "").strip()
        for role in payload.get("roles", []):
            if not isinstance(role, dict):
                continue
            role_id = str(role.get("id") or "").strip().lower()
            label = str(role.get("label") or "").strip().lower()
            key = f"{module_id}:{role_id}".lower()
            if wanted in {role_id, label, key}:
                matches.append((module_id, role, path))
    if len(matches) != 1:
        detail = "nicht gefunden" if not matches else "mehrdeutig; modul:rolle verwenden"
        raise ValueError(f"Rolle {args.role!r} {detail}")
    module_id, role, manifest = matches[0]
    prompt = (manifest.parent / str(role.get("prompt") or "")).resolve()
    if not prompt.is_file():
        raise ValueError(f"Prompt-Datei nicht gefunden: {prompt}")
    request = str(args.request or role.get("request") or "").strip()
    providers = [str(value).strip().lower() for value in role.get("providers", [])]
    provider = str(args.provider or (providers[0] if providers else "")).strip().lower()
    if not provider or provider not in providers:
        raise ValueError(f"Provider {provider!r} ist fuer {module_id}:{role.get('id')} nicht erlaubt")
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    notices = ["[FALLBACK] unified-gui-Konsole fehlt; verwende den nächsten Startweg."]

    if _module_available("taskplan"):
        command = [
            sys.executable, "-m", "taskplan", "launch",
            "--label", f"{module_id}:{role.get('id')}",
            "--prompt-file", str(prompt),
            "--request", request,
            "--provider", provider,
        ]
    elif _module_available("coma.session"):
        notices.append("[FALLBACK] task-master fehlt; verwende COMA direkt.")
        command = [
            sys.executable, "-m", "coma", "session",
            "--provider", provider,
            "--prompt-file", str(prompt),
            "--request", request,
            "--cwd", str(cwd),
        ]
    else:
        notices.extend((
            "[FALLBACK] task-master fehlt; COMA wird geprüft.",
            "[FALLBACK] COMA fehlt; verwende den modul-eigenen Starter.",
        ))
        starter = (manifest.parent / str(role.get("starter") or "")).resolve()
        if not starter.is_file():
            raise ValueError("Kein Startweg und kein vorhandener modul-eigener Starter")
        command = [str(starter)]
    if command[0] == sys.executable:
        if args.model and "--model" not in command:
            command.extend(["--model", args.model])
        if args.effort and "--effort" not in command:
            command.extend(["--effort", args.effort])
        if args.dry_run and "coma" in command:
            command.append("--dry-run")
    return command, notices


def _start_role(args: argparse.Namespace, *, run=None) -> int:
    runner = subprocess.run if run is None else run
    if _module_available("unified_gui.console"):
        command = _role_console_command(args)
        notices: list[str] = []
    else:
        command, notices = _fallback_role_command(args)
    for notice in notices:
        print(notice)
    if args.dry_run and command[0] != sys.executable:
        print(subprocess.list2cmdline(command))
        return 0
    env = None
    if args.dry_run and command[1:4] == ["-m", "taskplan", "launch"]:
        env = dict(os.environ, TASKPLAN_STARTER_DRY_RUN="1")
    completed = runner(
        command,
        cwd=str(args.cwd.resolve()) if args.cwd else None,
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "plan":
        try:
            report = plan_from_paths(
                bundles_root=args.bundles_root,
                system_manifest=args.system_manifest,
                modules_catalog=args.modules_catalog,
                skills_registry=args.skills_registry,
                workspace=args.workspace,
                component_bindings=args.component_bindings,
                source_pins=args.source_pins,
            )
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            missing = report["readiness"]["required_components_missing"]
            print(f"OCEAN-Plan: Runtime {report['runtime']['id']} ist verfügbar.")
            print(f"Fehlende Pflichtkomponenten: {len(missing)}")
        return 0
    if args.command == "up":
        if not args.apply:
            print("'ocean up' benötigt --apply; für den rein lesenden Vorlauf nutze 'ocean plan'.", file=sys.stderr)
            return 3
        try:
            report = up_from_paths(
                bundles_root=args.bundles_root,
                system_manifest=args.system_manifest,
                modules_catalog=args.modules_catalog,
                skills_registry=args.skills_registry,
                workspace=args.workspace,
                component_bindings=args.component_bindings,
                source_pins=args.source_pins,
                host=args.host,
                port=args.port,
                health_timeout=args.health_timeout,
            )
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else report["runtime"]["url"])
        return 0
    if args.command == "status":
        try:
            report = status_for_workspace(args.workspace)
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else f"OCEAN: {report['runtime']['control']} ({report['runtime']['health']})")
        return 0 if report["runtime"]["control"] == "running" and report["runtime"]["health"] == "ok" else 1
    if args.command == "start":
        if args.role:
            try:
                return _start_role(args)
            except ValueError as exc:
                print(f"[FEHLER] {exc}", file=sys.stderr)
                return 2
        if args.workspace is None:
            print("[FEHLER] 'ocean start' ohne Rolle benötigt --workspace.", file=sys.stderr)
            return 2
        _attach_stderr_log(args.workspace)
        try:
            report = start_installed_runtime(
                args.workspace,
                host=args.host,
                port=args.port,
                health_timeout=args.health_timeout,
            )
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else report["runtime"]["url"])
        return 0
    if args.command == "down":
        try:
            report = down_for_workspace(args.workspace)
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else "OCEAN wurde beendet.")
        return 0
    if args.command == "user" and args.user_command == "add":
        if args.password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = getpass.getpass("Passwort: ")
            if password != getpass.getpass("Passwort wiederholen: "):
                print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
                return 2
        try:
            report = user_add_for_workspace(
                args.workspace,
                username=args.username,
                email=args.email,
                role=args.role,
                password=password,
            )
        except LifecycleError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        print(
            json.dumps(report, indent=2, ensure_ascii=False)
            if args.json
            else f"Benutzer '{report['username']}' wurde angelegt."
        )
        return 0
    print(f"Der Befehl '{args.command}' wird in diesem Build noch nicht ausgeführt.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
