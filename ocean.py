#!/usr/bin/env python3
"""OCEAN Full Dev lifecycle entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.ocean_lifecycle import (
    LifecycleError,
    down_for_workspace,
    plan_from_paths,
    start_installed_runtime,
    status_for_workspace,
    up_from_paths,
    user_add_for_workspace,
)
from tools.resolve_bundles import DEFAULT_COMPONENT_BINDINGS


DEFAULT_OCEAN_PORT = 8810


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
    start = commands.add_parser(
        "start",
        help="bereits installierten OCEAN-Stand starten oder nach Prozessverlust wiederherstellen",
    )
    start.add_argument("--workspace", type=Path, required=True)
    start.add_argument("--host", choices=["127.0.0.1", "localhost"])
    start.add_argument("--port", type=int, help="optional neuer Port; sonst wird der installierte Port verwendet")
    start.add_argument("--json", action="store_true")
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
                host=args.host,
                port=args.port,
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
        _attach_stderr_log(args.workspace)
        try:
            report = start_installed_runtime(
                args.workspace,
                host=args.host,
                port=args.port,
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
