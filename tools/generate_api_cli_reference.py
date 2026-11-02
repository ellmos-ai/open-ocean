# -*- coding: utf-8 -*-
"""Deterministic API & CLI Reference Generator for Open-Ocean (Task #2556).

Extracts all CLI subcommands from `ocean.py::build_parser()`, all HTTP API routes
mounted by `tools/gui_bridge.py` & `tools/gui_server.py`, and all 11 canonical
Ocean module bindings (`tools/ocean_stack_bridge.py`) into:
  - `docs/api/README.md`
  - `docs/api/cli-reference.md`
  - `docs/api/reference-manifest.json`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ocean import build_parser
from tools.ocean_stack_bridge import ocean_stack_status

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_RE = re.compile(r'@\w+\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')


def extract_cli_commands() -> list[dict[str, Any]]:
    parser = build_parser()
    subparsers_actions = [
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    commands: list[dict[str, Any]] = []
    for sub in subparsers_actions:
        help_map = {
            choice_action.dest: (choice_action.help or "")
            for choice_action in getattr(sub, "_choices_actions", [])
        }
        for name, subparser in sorted(sub.choices.items()):
            flags: list[str] = []
            for act in subparser._actions:
                if act.option_strings and act.option_strings != ["-h", "--help"]:
                    flags.append("/".join(act.option_strings))
            commands.append({
                "command": name,
                "prog": subparser.prog,
                "help": help_map.get(name, ""),
                "options": flags,
            })
    return commands


def extract_http_routes() -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for rel_path in ("tools/gui_bridge.py", "tools/gui_server.py"):
        target = REPO_ROOT / rel_path
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        for m in ROUTE_RE.finditer(text):
            method = m.group(1).upper()
            path = m.group(2)
            if (method, path) not in seen:
                seen.add((method, path))
                routes.append({"method": method, "path": path, "source": rel_path})
        for path in ("/api/gui/capabilities", "/api/gui/kit-manifest", "/health"):
            if ("GET", path) not in seen:
                seen.add(("GET", path))
                routes.append({"method": "GET", "path": path, "source": "tools/gui_server.py"})
    return sorted(routes, key=lambda r: (r["path"], r["method"]))


def build_reference_artifacts() -> dict[str, Any]:
    cli_commands = extract_cli_commands()
    http_routes = extract_http_routes()
    stack = ocean_stack_status()
    modules = [
        {"id": k, "module": v["module"], "bound": bool(v["bound"])}
        for k, v in sorted(stack["modules"].items())
    ]

    manifest_core = {
        "schema": "ellmos.api-cli-reference.v1",
        "product": "open-ocean",
        "cli_command_count": len(cli_commands),
        "http_route_count": len(http_routes),
        "module_binding_count": len(modules),
        "cli_commands": cli_commands,
        "http_routes": http_routes,
        "module_bindings": modules,
    }
    digest = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    manifest = {**manifest_core, "sha256": digest}

    api_lines = [
        "# Open-Ocean — HTTP-API & Modul-Referenz (automatisch generiert, #2556)",
        "",
        f"- **Schema:** `{manifest['schema']}`",
        f"- **HTTP-Routen:** `{len(http_routes)}`",
        f"- **Gebundene Ocean-Module:** `{len(modules)}`",
        f"- **Manifest-SHA256:** `{digest}`",
        "",
        "## 1. HTTP-API-Routen (`tools/gui_bridge.py` & `tools/gui_server.py`)",
        "",
        "| Methode | Pfad | Quelle |",
        "|---|---|---|",
    ]
    for r in http_routes:
        api_lines.append(f"| `{r['method']}` | `{r['path']}` | `{r['source']}` |")

    api_lines.extend([
        "",
        "## 2. Kanonische 11 Ocean-Modul-Bindungen (`tools/ocean_stack_bridge.py`)",
        "",
        "| Modul-ID | Python-Modul | Gebunden |",
        "|---|---|---|",
    ])
    for m in modules:
        api_lines.append(f"| `{m['id']}` | `{m['module']}` | `{'ja' if m['bound'] else 'nein'}` |")
    api_md = "\n".join(api_lines) + "\n"

    cli_lines = [
        "# Open-Ocean — CLI-Referenz (`ocean.py`, automatisch generiert, #2556)",
        "",
        f"- **Befehle gesamt:** `{len(cli_commands)}`",
        f"- **Manifest-SHA256:** `{digest}`",
        "",
        "| Befehl | Aufruf | Beschreibung | Optionen |",
        "|---|---|---|---|",
    ]
    for c in cli_commands:
        opts = ", ".join(f"`{o}`" for o in c["options"]) if c["options"] else "—"
        cli_lines.append(f"| `{c['command']}` | `{c['prog']}` | {c['help']} | {opts} |")
    cli_md = "\n".join(cli_lines) + "\n"

    return {
        "manifest": manifest,
        "api_markdown": api_md,
        "cli_markdown": cli_md,
    }


def write_reference_files(output_dir: str | Path | None = None) -> dict[str, Path]:
    base = Path(output_dir) if output_dir is not None else (REPO_ROOT / "docs" / "api")
    base.mkdir(parents=True, exist_ok=True)
    artifacts = build_reference_artifacts()
    readme_path = base / "README.md"
    cli_path = base / "cli-reference.md"
    manifest_path = base / "reference-manifest.json"
    readme_path.write_text(artifacts["api_markdown"], encoding="utf-8")
    cli_path.write_text(artifacts["cli_markdown"], encoding="utf-8")
    manifest_path.write_text(
        json.dumps(artifacts["manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "readme": readme_path,
        "cli": cli_path,
        "manifest": manifest_path,
    }


if __name__ == "__main__":
    write_reference_files()
