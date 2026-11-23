# Open-Ocean — CLI-Referenz (`ocean.py`, automatisch generiert, #2556)

- **Hauptbefehle:** `16`
- **Unterbefehle:** `16`
- **Manifest-SHA256:** `9d3ec2cd9c310fa598fdef0e8e9deab7d31797a3c37ec63bca694cd7bd488ed9`

| Befehl | Aufruf | Beschreibung | Optionen |
|---|---|---|---|
| `agents` | `ocean agents` | Agenten und Hintergrundworker steuern | — |
| `authority` | `ocean authority` | Autoritätsprüfung (Folgeschritt-Regel / 3-Stufen-Tunneling) und Feedback auswerten | — |
| `chat` | `ocean chat` | Interaktive Terminal-Konsole oder Single-Shot-Chat mit einem Agenten | `--agent`, `--session`, `--once`, `--tools`, `--stream`, `--json`, `--url`, `--token`, `--workspace` |
| `console` | `ocean console` | Alias für 'ocean chat' | `--agent`, `--session`, `--once`, `--tools`, `--stream`, `--json`, `--url`, `--token`, `--workspace` |
| `down` | `ocean down` | Nur die zugehörige OCEAN-Laufzeit kontrolliert beenden | `--workspace`, `--json` |
| `gui` | `ocean gui` | gepinntes System-GUI-Kit prüfen oder lokal bereitstellen | `--archive`, `--dist-root`, `--receipt`, `--brand-config`, `--workspace`, `--universal-fallback`, `--host`, `--port`, `--serve`, `--json` |
| `inspect` | `ocean inspect` | installierte Komponenten mit nativer System-Explorer-Evidenz rein lesend prüfen | `--workspace`, `--resolution`, `--receipt`, `--trust-store`, `--trust-store-sha256`, `--expected-instance-id`, `--expected-host-id`, `--root-only-resolution`, `--evaluated-at`, `--expected-provider-version`, `--component-bindings`, `--json` |
| `plan` | `ocean plan` | Komposition und Laufzeit rein lesend prüfen | `--bundles-root`, `--system-manifest`, `--modules-catalog`, `--skills-registry`, `--component-bindings`, `--source-pins`, `--workspace`, `--gui-archive`, `--gui-source-commit`, `--gui-archive-sha256`, `--json` |
| `sessions` | `ocean sessions` | Session-Snapshots und Transkripte einsehen und übergeben | — |
| `stack-status` | `ocean stack-status` | Status aller 11 kanonischen Ocean-Module im Plattformkern anzeigen | `--json` |
| `start` | `ocean start` | installierten OCEAN-Stand oder eine deklarierte Modulrolle starten | `--workspace`, `--host`, `--port`, `--health-timeout`, `--json`, `--manifest`, `--provider`, `--model`, `--effort`, `--request`, `--cwd`, `--name`, `--dry-run` |
| `status` | `ocean status` | Installations- und Laufzeitstatus live prüfen | `--workspace`, `--json` |
| `task` | `ocean task` | Einheitliches Task-Lifecycle-Werkzeug über den Taskkern taskplan (list\|take\|renew\|submit\|return\|block\|reclaim) | — |
| `tasks` | `ocean tasks` | Tasks über die Runtime-API verwalten und zuweisen | — |
| `up` | `ocean up` | OCEAN in einer lokalen Sandbox installieren und starten | `--bundles-root`, `--system-manifest`, `--modules-catalog`, `--skills-registry`, `--component-bindings`, `--source-pins`, `--workspace`, `--gui-archive`, `--gui-source-commit`, `--gui-archive-sha256`, `--json`, `--host`, `--port`, `--apply`, `--policy-registry`, `--lock-cache`, `--health-timeout` |
| `user` | `ocean user` | Benutzer der aktiven OCEAN-Laufzeit verwalten | — |

## Unterbefehle

| Aufruf | Beschreibung | Positionsargumente | Pflichtoptionen | Weitere Optionen |
|---|---|---|---|---|
| `ocean agents list` | Agenten und Hintergrundworker auflisten | — | — | `--status`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean agents pause` | Agenten oder Worker pausieren | `agent_id` | — | `--json`, `--url`, `--token`, `--workspace` |
| `ocean agents resume` | Agenten oder Worker fortsetzen | `agent_id` | — | `--json`, `--url`, `--token`, `--workspace` |
| `ocean agents show` | Detailstatus eines Agenten oder Workers | `agent_id` | — | `--json`, `--url`, `--token`, `--workspace` |
| `ocean agents start` | Agenten oder Worker starten | `agent_id` | — | `--json`, `--url`, `--token`, `--workspace` |
| `ocean agents stop` | Agenten oder Worker stoppen | `agent_id` | — | `--json`, `--url`, `--token`, `--workspace` |
| `ocean authority check` | Prüft ob eine Aktion durch Auftrag, Zitat oder Hard-Gate gedeckt ist | — | `--action-class` | `--irreversible`, `--target-locked`, `--authority-ref`, `--goal-id`, `--goal-quote`, `--follows-from-goal/--no-follows-from-goal`, `--new-tradeoff/--no-new-tradeoff`, `--strict-followup`, `--source-id`, `--quote`, `--source-text-file`, `--decision-id`, `--has-hard-gate`, `--json` |
| `ocean authority feedback` | Nachbetrachtung einer Rückfrage oder Aktion klassifizieren (error_authority_desert / error_overreach) | — | `--action-class` | `--prompted-user`, `--intent-in-context`, `--exceeded-intent`, `--json` |
| `ocean sessions list` | Session-Snapshots auflisten | — | — | `--agent`, `--source`, `--problems`, `--limit`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean sessions resume` | Session an Hintergrundworker übergeben | `snapshot_id` | `--worker` | `--prompt`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean sessions show` | Session-Transkript ausgeben | `snapshot_id` | — | `--tools`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean tasks assign` | Task einem Agenten zuweisen | `task_id` | `--agent` | `--json`, `--url`, `--token`, `--workspace` |
| `ocean tasks list` | Tasks auflisten | — | — | `--status`, `--assigned`, `--limit`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean tasks returns` | Task-Rückgaben anzeigen | — | — | `--hours`, `--worker`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean tasks show` | Task-Details anzeigen | `task_id` | — | `--history`, `--json`, `--url`, `--token`, `--workspace` |
| `ocean user add` | Benutzer mit verdeckter Passworteingabe anlegen | — | `--workspace`, `--username`, `--email` | `--role`, `--password-stdin`, `--json` |
