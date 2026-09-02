# Open-Ocean-Aufgaben

*[English](TODO.md)*

## Unmittelbare Zuverlässigkeitsaufgaben

- [x] Workspacegebundene Interprozess-Startsperre ergänzt (`_start_lock`, `ocean.start.lock`,
  vom OS gehaltene Byte-Range-/flock-Sperre, wird beim Tod des Starters vom OS freigegeben;
  ein zweiter gleichzeitiger Start scheitert an der CLI geschlossen). Ursprungsbeschreibung: Zwei direkte
  Lebenszyklusaufrufe können derzeit die Leerer-Zustand-Vorprüfung passieren, bevor einer der
  Supervisoren den Laufzeitstatus schreibt. Der ASUS-GEI-Logon-Task vermeidet das durch
  deaktiviertes `StartWhenAvailable` und genau einen Trigger; der Lebenszyklus selbst muss bei
  gleichzeitigen Starts jedoch geschlossen fehlschlagen.
- [x] Favicon ausgeliefert: `ellmos-core` beantwortet `/favicon.ico` mit seinem PWA-Icon
  (ellmos-core `6185504`); wirkt auf einem Host, sobald dessen Runtime-Provider-Kopie diesen
  Commit trägt. Ursprungsbeschreibung: Ein OCEAN-Favicon ausliefern oder die Favicon-Anforderung entfernen. Die aktuelle
  Browserabnahme ist gesund, protokolliert aber einen nicht funktionalen `/favicon.ico`-404.
- [ ] ASUS-GEI tatsächlich neu starten und danach den unveränderten Task
  `EllmosOceanFullUserStart`, den exakten Tag-Checkout, das Prozess-Tupel, die Portbelegung, die
  HTTP-Identität und die Full-Ocean-Bereitschaft nachlesen.
  **2026-09-02: de facto geschehen und FEHLGESCHLAGEN.** Nach dem Boot um 21:04 lief der
  Logon-Task um 21:07:23 und endete mit Exit 4 (Runtime-Kind Exit 1 nach 21 s, Port 8810 nie
  gebunden). Ursache: 12 von 14 Runtime-Providern auf dem Spec-PYTHONPATH sind OneDrive-
  Lesekopien, und OneDrive.exe startete erst um 21:14:27 — sieben Minuten nach dem Task. Ein
  manueller `ocean.py start` danach ist grün. Ticket T-20260902-313385481 (Provider in den Workspace
  platzieren; kein OneDrive-Laufzeitpfad; Kind-stderr nach `logs/runtime.log`). Übergangsweise
  auf ASUS-GEI: Task-Neustart bei Fehler 5× alle 2 min (XML-Backup in `logs/`). Bleibt offen,
  bis ein Reboot-Readback grün ist.
  **2026-09-02, später am selben Tag: beide Code-Fixes gelandet (b59d1ee).**
  `fetch_place.plan_and_fetch()` kopiert ("placed") jetzt jedes von Resolve gefundene Modul ohne
  exakte Bindung bei `--apply` nach `<workspace>/modules/<catalog_id>` und setzt dessen
  `local_path` dorthin um — genau wie die bereits bestehende Platzierung exakt gebundener
  Provider; `ocean.py start` spiegelt `sys.stderr` zusätzlich nach
  `<workspace>/logs/runtime.log` (pythonw hat keine Konsole, ein headless `LifecycleError`-Print
  — oder jede unbehandelte Ausnahme, da Pythons Default-Excepthook ebenfalls nach stderr
  schreibt — verschwand bisher spurlos, übrig blieb nur der nackte Exitcode). Auf ASUS-GEI ohne
  Neustart nachgeprüft: der gepinnte Runtime-Checkout wurde auf `b59d1ee` vorgespult, `ocean.py
  down` + `up --apply` (mit denselben bundles-root/system-manifest/catalog/skills-registry wie
  bei der ursprünglichen Installation) lief sauber durch, und das entstandene
  `ocean.runtime-spec.json` enthält jetzt **null** OneDrive-Einträge unter allen 14
  PYTHONPATH-Pfaden (alle unter `C:\_Local_DEV\ocean-full\modules\`).
  `Start-ScheduledTask EllmosOceanFullUserStart` nach einem `ocean.py down` hat die reale
  Logon-Aktion Ende-zu-Ende nachgestellt: `LastTaskResult 0`, Prozessabstammung `pythonw
  ocean.py start` → `pythonw runtime_supervisor.py` → `pythonw ocean_runtime.py` (PID 26608)
  lauscht auf 8810, `/api/health` → `{"ok":true,...}`, und sowohl die Stderr-Tee-Kopfzeile als
  auch die eigene Uvicorn-Ausgabe des Kindes landeten wie vorgesehen in `logs/runtime.log`.
  **Das ist NICHT der oben verlangte Reboot-Readback** — OneDrive lief während dieses Tests
  durchgehend, kann also das eigentliche Wettrennen (OneDrive beim Logon noch nicht eingehängt)
  nicht reproduzieren; es belegt nur, dass der Fix dieses Wettrennen konstruktiv beseitigt (kein
  OneDrive-Pfad mehr, gegen den gelaufen werden könnte) und dass die Kette
  Task/Prozess/Port/Health auf dem reparierten Checkout Ende-zu-Ende funktioniert. Bleibt offen,
  bis ein echter ASUS-GEI-Neustart es live bestätigt.
- [x] `--host`-Argument bei `ocean.py up` korrigiert (7d4de09): `up` traegt jetzt
  dieselben `choices=["127.0.0.1", "localhost"]` wie `start`, ein falscher Wert scheitert
  sofort am Parser statt tief im Lifecycle. Folgeschritt erledigt:
  das gleichnamige `--host` in `tools/ocean_dev.py` (dort Skill-Host-Adapter,
  nicht Netzwerk-Bind) heißt jetzt `--skill-host`; `--host` bleibt als Legacy-Alias gültig, kein Aufrufer bricht.
  Ursprungsbeschreibung: `--host`-Argument bei `ocean.py up` korrigieren: `ocean.py` und `tools/ocean_dev.py`
  besitzen jeweils einen eigenen, gleichnamigen `--host`-Parameter; `ocean.py` reicht sein
  `--host` nie an den `ocean_dev.py`-Subprozess weiter, der stattdessen immer seinen eigenen
  Default `"claude-code"` verwendet. Ein vorgegebenes `--host claude-code` bei `up` bricht
  deshalb deterministisch mit `LifecycleError` ab; `--host` bei `up` weglassen (Default
  `127.0.0.1`), so wie es jeder erfolgreiche Lauf im Bauplan tut.
- [x] Readiness-Gate für `up --apply` ergänzt (7d4de09): neues
  `_assert_composition_complete` in `ocean_lifecycle.py` haelt die Laufzeit zurueck und nennt
  die fehlenden Pflichtkomponenten. Komposition und Installationsstand werden bewusst VORHER
  geschrieben, damit Artefakte und Bericht zur Diagnose bleiben. Ursprungsbeschreibung:
  Readiness-Gate für `up --apply` ergänzen: Es prüft die Provider-Vollständigkeit nicht vor
  dem Start der Laufzeit — ein fehlgeschlagener Provider-Fetch startet trotzdem eine
  unvollständige Komposition (`ocean_lifecycle.py:546-596`; Readiness wird nur berichtet, nie
  durchgesetzt).
- [x] Am 2026-08-30 neu gemessen; die Referenz muss nicht korrigiert werden. Am Pin des
  Recipe-Providers `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` ist
  `manifests/skills.registry.crosswalk.v1.json` eine Identitätsabbildung mit 81 Einträgen und der
  deklarierten Top-Level-Sammlung `skills`. Derselbe Binding-Vertrag deklariert davon getrennt die
  native Skills-Registry `components.json` mit ihrem Top-Level-Array `components`. OCEAN verwendet
  letztere korrekt zum Auflösen/Installieren und schließt jetzt mit einer eindeutigen Schema-Ursache,
  falls der Crosswalk stattdessen als Registry übergeben wird. Die exakte Quellenprüfung zeigte
  zusätzlich veraltete Rohdatei-SHA-Pins; deren Re-Pin bleibt die eigene Folgearbeit
  `T-20260830-702817310`.

## Freigabebreite

- [ ] Eine vollständige frische Full-Ocean-Installation auf einem anderen Rechner ausführen.
- [ ] Die standardmäßig geschlossene öffentliche OPEN-OCEAN-Allowlist unabhängig von FULL OCEAN
  ableiten und testen.
- [ ] Die funktionale BACH-Parität weiterführen; neu entdeckte BACH-Eigenheiten nur ausnahmsweise
  und wertgebunden in einem eigenen Modulzyklus extrahieren.
- [x] (2026-09-02) Gemergt: `gardener` #4 (master ddd3a84), `ellmos-controlcenter-mcp` #9 (main 34cd95d); `policy-registry` #3 zugunsten des Decision-Index-Pfad-Slices geschlossen (https://github.com/ellmos-ai/policy-registry/pull/4). Übernahme (hostlokaler Registry-Seed, ControlCenter-Konfiguration, ccm-0.6.0-npm-Release) bleibt offen. Ursprünglich: Die offenen Governance-PRs mergen und übernehmen (`policy-registry` #3, `gardener` #4,
  `ellmos-controlcenter-mcp` #9) — alle offen, mergefähig, CI grün zum Stand 2026-08-30, keiner
  gemergt. Hostlokale Registry-Initialisierung, Gardener-Systemquellen und
  ControlCenter-Konfiguration werden erst danach relevant.
- [ ] Geräteseitige OS-Konto-Kopplung für die OCEAN-Benutzeridentität prüfen (ein
  Windows-/macOS-Konto je Gerät) statt eines zusätzlichen App-Passworts; Anlass: Die
  WORKSTATION-LG-Installation läuft ohne OCEAN-Benutzer, während `/control/` und `/api/health`
  ohne Auth erreichbar bleiben.

Diese Punkte autorisieren weder eine Veröffentlichung noch eine Sichtbarkeitsänderung oder die
Entfernung von `PRIVATE.txt`.
