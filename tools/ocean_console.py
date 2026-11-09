"""OCEAN Console & Interactive Chat REPL.

Implements the CLI handlers for:
- ocean chat / ocean console (Interactive REPL & Single-Shot)
- ocean agents (list, show, start, resume, pause, stop)
- ocean sessions (list, show, resume)
- ocean tasks (list, show, assign, returns)
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from tools.ocean_api_client import OceanApiClient, OceanApiError


# Optional readline history support
try:
    import readline  # type: ignore

    HAVE_READLINE = True
except ImportError:
    HAVE_READLINE = False


def _init_history() -> Path | None:
    if not HAVE_READLINE:
        return None
    hist_dir = Path.home() / ".ocean"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_file = hist_dir / "chat_history"
    if hist_file.is_file():
        try:
            readline.read_history_file(str(hist_file))
        except OSError:
            pass
    return hist_file


def _save_history(hist_file: Path | None) -> None:
    if HAVE_READLINE and hist_file:
        try:
            readline.write_history_file(str(hist_file))
        except OSError:
            pass


# =============================================================================
# Agents CLI Handler
# =============================================================================

def handle_agents(client: OceanApiClient, args: argparse.Namespace) -> int:
    subcmd = getattr(args, "agents_subcommand", "list") or "list"

    if subcmd == "list":
        status_filter = getattr(args, "status", None)
        agents = client.list_agents(status_filter=status_filter)
        if getattr(args, "json", False):
            print(json.dumps(agents, indent=2, ensure_ascii=False))
            return 0

        # Pretty terminal display grouped by status
        groups: dict[str, list[dict[str, Any]]] = {
            "running": [],
            "ready": [],
            "paused": [],
            "error": [],
        }
        for a in agents:
            grp = a.get("status_group", "ready")
            groups.setdefault(grp, []).append(a)

        status_labels = {
            "running": "⚡ RUNNING · AKTIV",
            "ready": "🟢 READY · BEREIT",
            "paused": "⏸️  PAUSED · PAUSIERT",
            "error": "❌ ERROR · FEHLER",
        }

        print(f"\nOCEAN Agenten ({len(agents)} gesamt):")
        print("=" * 78)
        for grp_key in ("running", "ready", "paused", "error"):
            items = groups.get(grp_key, [])
            if not items and status_filter:
                continue
            print(f"\n{status_labels.get(grp_key, grp_key.upper())} ({len(items)}):")
            print("-" * 78)
            if not items:
                print("  (keine Einträge)")
                continue
            for item in items:
                kind_badge = "[Core]" if item["kind"] == "core" else "[Worker]"
                model = f"({item['model']})" if item["model"] else ""
                activity = f" - {item['activity']}" if item["activity"] else ""
                print(f"  * {item['id']:<26} {kind_badge:<9} {item['name']} {model}{activity}")
        print("=" * 78 + "\n")
        return 0

    if subcmd == "show":
        agent_id = args.agent_id
        try:
            agent = client.show_agent(agent_id)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(agent, indent=2, ensure_ascii=False))
            return 0

        print(f"\n=== Agent: {agent['name']} ({agent['id']}) ===")
        print(f"Typ:               {agent['kind'].upper()}")
        print(f"Statusgruppe:      {agent['status_group'].upper()} (Rohstatus: {agent['raw_status']})")
        print(f"Modell:            {agent['model'] or 'nicht festgelegt'}")
        print(f"Aktivität:         {agent['activity'] or 'keine'}")
        print(f"Runtime Verified:  {'Ja' if agent['runtime_verified'] else 'Nein'}")
        print("===========================================\n")
        return 0

    if subcmd in ("start", "resume", "pause", "stop"):
        agent_id = args.agent_id
        try:
            res = client.control_agent(agent_id, action=subcmd)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"[OK] Agent/Worker '{agent_id}' -> Aktion '{subcmd}' erfolgreich übermittelt.")
        return 0

    print(f"[FEHLER] Unbekanntes Subkommando 'ocean agents {subcmd}'.", file=sys.stderr)
    return 2


# =============================================================================
# Sessions CLI Handler
# =============================================================================

def handle_sessions(client: OceanApiClient, args: argparse.Namespace) -> int:
    subcmd = getattr(args, "sessions_subcommand", "list") or "list"

    if subcmd == "list":
        limit = getattr(args, "limit", 25) or 25
        agent = getattr(args, "agent", None)
        source = getattr(args, "source", None)
        problems = getattr(args, "problems", False)

        try:
            data = client.list_sessions(agent=agent, source=source, problems=problems, limit=limit)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0

        sessions = data.get("sessions", []) if isinstance(data, dict) else data
        print(f"\nOCEAN Sessions ({len(sessions)} von {data.get('total', len(sessions))}):")
        print("=" * 84)
        print(f"{'ID':<8} {'ERSTELLT':<20} {'QUELLE':<10} {'MSGS':<6} {'NAME / CHAT-ID'}")
        print("-" * 84)
        for s in sessions:
            sid = str(s.get("id", ""))
            created = str(s.get("created_at", ""))[:19].replace("T", " ")
            src = str(s.get("source", ""))
            count = str(s.get("stored_message_count", s.get("message_count", 0)))
            name = s.get("name") or s.get("chat_id") or ""
            print(f"{sid:<8} {created:<20} {src:<10} {count:<6} {name[:36]}")
        print("=" * 84 + "\n")
        return 0

    if subcmd == "show":
        snapshot_id = args.snapshot_id
        include_tools = getattr(args, "tools", False)
        try:
            data = client.show_session(snapshot_id, include_tools=include_tools)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0

        print(f"\n=== Session Snapshot #{snapshot_id}: {data.get('name', '')} ===")
        print(f"Chat-ID:   {data.get('chat_id')}")
        print(f"Erstellt:  {data.get('created_at')}")
        print(f"Nachrichten: {len(data.get('messages', []))}")
        print("-" * 78)

        for msg in data.get("messages", []):
            role = str(msg.get("role", "unknown")).upper()
            content = msg.get("content", "")
            if role == "TOOL":
                tool_name = msg.get("name", "tool")
                print(f"\n[{role}: {tool_name}]\n{content}\n")
            else:
                print(f"\n[{role}]\n{content}\n")
        print("=" * 78 + "\n")
        return 0

    if subcmd == "resume":
        snapshot_id = args.snapshot_id
        worker_id = args.worker
        prompt = getattr(args, "prompt", None)
        try:
            res = client.resume_session(snapshot_id, worker_id=worker_id, prompt=prompt)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"[OK] Session #{snapshot_id} an Worker '{worker_id}' zur Fortsetzung übergeben.")
        return 0

    print(f"[FEHLER] Unbekanntes Subkommando 'ocean sessions {subcmd}'.", file=sys.stderr)
    return 2


# =============================================================================
# Tasks CLI Handler
# =============================================================================

def handle_tasks(client: OceanApiClient, args: argparse.Namespace) -> int:
    subcmd = getattr(args, "tasks_subcommand", "list") or "list"

    if subcmd == "list":
        status = getattr(args, "status", None)
        assigned = getattr(args, "assigned", None)
        limit = getattr(args, "limit", 50) or 50
        try:
            data = client.list_tasks(status=status, assigned=assigned, limit=limit)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0

        tasks = data.get("tasks", []) if isinstance(data, dict) else data
        print(f"\nOCEAN Tasks ({len(tasks)} Einträge):")
        print("=" * 80)
        print(f"{'ID':<6} {'STATUS':<12} {'PRIO':<6} {'TITEL':<38} {'ZUGEWIESEN'}")
        print("-" * 80)
        for t in tasks:
            tid = str(t.get("id", ""))
            tstat = str(t.get("status", ""))
            tprio = str(t.get("priority", ""))
            ttitle = str(t.get("title", ""))[:36]
            tassign = str(t.get("assigned_to", t.get("assignee", "")))
            print(f"#{tid:<5} {tstat:<12} {tprio:<6} {ttitle:<38} {tassign}")
        print("=" * 80 + "\n")
        return 0

    if subcmd == "show":
        task_id = args.task_id
        history = getattr(args, "history", False)
        try:
            data = client.show_task(task_id, history=history)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0

        print(f"\n=== Task #{task_id}: {data.get('title', '')} ===")
        print(f"Status:      {data.get('status')}")
        print(f"Priorität:   {data.get('priority')}")
        print(f"Zugewiesen:  {data.get('assigned_to') or 'niemand'}")
        print(f"Erstellt:    {data.get('created_at')}")
        desc = data.get("description")
        if desc:
            print(f"\nBeschreibung:\n{desc}\n")
        if "history_events" in data:
            print("Verlauf:")
            events = data["history_events"]
            raw_ev = events.get("events", events) if isinstance(events, dict) else events
            for ev in raw_ev if isinstance(raw_ev, list) else []:
                print(f"  * {ev.get('timestamp') or ev.get('created_at')}: {ev.get('action')} -> {ev.get('note', '')}")
        print("=" * 60 + "\n")
        return 0

    if subcmd == "assign":
        task_id = args.task_id
        agent_id = args.agent
        try:
            res = client.assign_task(task_id, agent_id=agent_id)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"[OK] Task #{task_id} erfolgreich an '{agent_id}' zugewiesen.")
        return 0

    if subcmd == "returns":
        hours = getattr(args, "hours", 24) or 24
        worker = getattr(args, "worker", None)
        try:
            data = client.list_task_returns(hours=hours, worker=worker)
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0

        print(f"\n=== Task-Rückgaben (letzte {hours} Stunden) ===")
        events = data.get("events", []) if isinstance(data, dict) else []
        print(f"Gesamt-Ereignisse: {data.get('total', len(events))}")
        for ev in events[:20]:
            print(f"  * Task #{ev.get('task_id')}: {ev.get('reason')} durch {ev.get('worker_id', '')} ({ev.get('created_at', '')})")
        print("=" * 60 + "\n")
        return 0

    print(f"[FEHLER] Unbekanntes Subkommando 'ocean tasks {subcmd}'.", file=sys.stderr)
    return 2


# =============================================================================
# Chat & Interactive REPL
# =============================================================================

HELP_TEXT = """
Verfügbare Slash-Befehle in der OCEAN-Konsole:
  /agent <id>         Wechselt den aktiven Agenten oder Worker
  /sessions [limit]   Listet gespeicherte Sessions des aktuellen Agenten
  /load <snapshot_id> Lädt ein gespeichertes Session-Transkript in die Konsole
  /fork [snapshot_id] Übernimmt eine Session in einen neuen Direkt-Chat
  /resume [hinweis]   Startet Hintergrundworker mit Übergabezettel neu
  /tools [on|off]     Schaltet die Anzeige von Tool-Aufrufen ein oder aus
  /status             Zeigt Detailstatus und Modellbindung des aktuellen Agenten
  /new                Startet einen frischen Direkt-Chat-Strang
  /exit | /quit       Beendet die OCEAN-Konsole
  /help               Zeigt diese Hilfe an
"""


def _generate_chat_id(agent_id: str) -> str:
    return f"slot:{agent_id}:{secrets.token_hex(16)}"


def handle_chat(client: OceanApiClient, args: argparse.Namespace) -> int:
    agent_id = getattr(args, "agent", None) or "buddha_chat"
    chat_id = _generate_chat_id(agent_id)
    show_tools = getattr(args, "tools", False)
    use_stream = getattr(args, "stream", False)

    # Fork session if requested
    session_id = getattr(args, "session", None)
    if session_id:
        try:
            fork_res = client.fork_session(session_id, agent_id=agent_id)
            if isinstance(fork_res, dict) and fork_res.get("chat_id"):
                chat_id = fork_res["chat_id"]
        except OceanApiError as exc:
            print(f"[WARNUNG] Session-Fork für #{session_id} fehlgeschlagen: {exc}", file=sys.stderr)

    # 1. Single-Shot Mode
    once_prompt = getattr(args, "once", None)
    if once_prompt:
        try:
            if use_stream:
                full_resp: list[dict[str, Any]] = []
                for chunk in client.stream_chat(agent_id, once_prompt, chat_id=chat_id):
                    full_resp.append(chunk)
                    if not getattr(args, "json", False):
                        if chunk.get("type") == "token":
                            print(chunk.get("token", ""), end="", flush=True)
                        elif chunk.get("type") == "tool_call" and show_tools:
                            print(f"\n[Werkzeug] {chunk.get('name')}: {chunk.get('arguments')}")
                        elif chunk.get("type") == "done":
                            res_obj = chunk.get("response", {})
                            if isinstance(res_obj, dict) and "reply" in res_obj:
                                print(res_obj["reply"])
                if not getattr(args, "json", False):
                    print()
                if getattr(args, "json", False):
                    print(json.dumps(full_resp, indent=2, ensure_ascii=False))
                return 0

            resp = client.send_chat(agent_id, once_prompt, chat_id=chat_id)
            if getattr(args, "json", False):
                print(json.dumps(resp, indent=2, ensure_ascii=False))
            else:
                reply = (
                    resp.get("reply")
                    or resp.get("response")
                    or resp.get("content")
                    or json.dumps(resp, ensure_ascii=False)
                )
                print(reply)
            return 0
        except OceanApiError as exc:
            print(f"[FEHLER] {exc}", file=sys.stderr)
            return 1

    # 2. Interactive REPL Mode
    hist_file = _init_history()
    print("\n" + "=" * 65)
    print("🌊 OCEAN Interactive Console")
    print(f"Host:    {client.base_url}")
    print(f"Agent:   {agent_id}")
    print(f"Chat-ID: {chat_id}")
    print("Tippe '/help' für Befehle, '/exit' zum Beenden.")
    print("=" * 65 + "\n")

    try:
        while True:
            try:
                line = input(f"ocean [{agent_id}]> ").strip()
            except EOFError:
                print("\n[Beendet]")
                break
            except KeyboardInterrupt:
                print("\n(Abbruch mit /exit oder Ctrl+D)")
                continue

            if not line:
                continue

            # Slash commands
            if line.startswith("/"):
                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                cmd_arg = parts[1].strip() if len(parts) > 1 else ""

                if cmd in ("/exit", "/quit"):
                    print("[Beendet]")
                    break

                if cmd == "/help":
                    print(HELP_TEXT)
                    continue

                if cmd == "/agent":
                    if not cmd_arg:
                        print("Syntax: /agent <id>")
                        continue
                    try:
                        agent_info = client.show_agent(cmd_arg)
                        agent_id = agent_info["id"]
                        chat_id = _generate_chat_id(agent_id)
                        print(f"[OK] Aktiver Agent gewechselt zu: {agent_info['name']} ({agent_id})")
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                if cmd == "/status":
                    try:
                        info = client.show_agent(agent_id)
                        print(f"Agent:    {info['name']} ({info['id']})")
                        print(f"Status:   {info['status_group'].upper()} ({info['raw_status']})")
                        print(f"Modell:   {info['model']}")
                        print(f"Aktiv:    {info['activity'] or '-'}")
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                if cmd == "/new":
                    chat_id = _generate_chat_id(agent_id)
                    print(f"[OK] Neuer Chat-Strang gestartet: {chat_id}")
                    continue

                if cmd == "/tools":
                    if cmd_arg.lower() in ("on", "1", "true"):
                        show_tools = True
                    elif cmd_arg.lower() in ("off", "0", "false"):
                        show_tools = False
                    else:
                        show_tools = not show_tools
                    print(f"[OK] Tool-Ausgabe ist jetzt {'AKTIV' if show_tools else 'DEAKTIVIERT'}.")
                    continue

                if cmd == "/sessions":
                    lim = int(cmd_arg) if cmd_arg.isdigit() else 10
                    try:
                        s_data = client.list_sessions(agent=agent_id, limit=lim)
                        sess_list = s_data.get("sessions", []) if isinstance(s_data, dict) else s_data
                        print(f"\nSessions für '{agent_id}':")
                        for s in sess_list:
                            print(f"  #{s.get('id')} ({s.get('created_at')[:19]}): {s.get('name') or s.get('chat_id')}")
                        print()
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                if cmd == "/load":
                    if not cmd_arg:
                        print("Syntax: /load <snapshot_id>")
                        continue
                    try:
                        snap = client.show_session(cmd_arg, include_tools=show_tools)
                        print(f"\n--- Transkript #{cmd_arg}: {snap.get('name', '')} ---")
                        for m in snap.get("messages", []):
                            print(f"[{m.get('role', '').upper()}]: {m.get('content')}")
                        print("--- Ende Transkript ---\n")
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                if cmd == "/fork":
                    fork_snap = cmd_arg if cmd_arg else (session_id or "")
                    if not fork_snap:
                        print("Syntax: /fork <snapshot_id>")
                        continue
                    try:
                        f_res = client.fork_session(fork_snap, agent_id=agent_id)
                        if isinstance(f_res, dict) and f_res.get("chat_id"):
                            chat_id = f_res["chat_id"]
                        print(f"[OK] Session #{fork_snap} in neuen Chat geforkt: {chat_id}")
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                if cmd == "/resume":
                    resume_snap = session_id or cmd_arg
                    if not resume_snap:
                        print("Syntax: /resume [snapshot_id]")
                        continue
                    try:
                        client.resume_session(resume_snap, worker_id=agent_id)
                        print(f"[OK] Worker '{agent_id}' aus Session #{resume_snap} neu gestartet.")
                    except OceanApiError as exc:
                        print(f"[FEHLER] {exc}")
                    continue

                print(f"[FEHLER] Unbekannter Befehl '{cmd}'. Tippe '/help' für eine Übersicht.")
                continue

            # Standard prompt message
            try:
                if use_stream:
                    print(f"\n[{agent_id}]", end=" ", flush=True)
                    for chunk in client.stream_chat(agent_id, line, chat_id=chat_id):
                        if chunk.get("type") == "token":
                            print(chunk.get("token", ""), end="", flush=True)
                        elif chunk.get("type") == "tool_call" and show_tools:
                            print(f"\n[Werkzeug] {chunk.get('name')}: {chunk.get('arguments')}")
                        elif chunk.get("type") == "done":
                            res_obj = chunk.get("response", {})
                            if isinstance(res_obj, dict) and "reply" in res_obj:
                                print(f"\n{res_obj['reply']}")
                    print("\n")
                else:
                    resp = client.send_chat(agent_id, line, chat_id=chat_id)
                    reply = (
                        resp.get("reply")
                        or resp.get("response")
                        or resp.get("content")
                        or json.dumps(resp, ensure_ascii=False)
                    )
                    print(f"\n[{agent_id}]\n{reply}\n")
            except OceanApiError as exc:
                print(f"\n[FEHLER] {exc}\n")
    finally:
        _save_history(hist_file)

    return 0
