# Open-Ocean-Aufgaben

*[English](TODO.md)*

## Unmittelbare Zuverlässigkeitsaufgaben

- [x] Workspacegebundene Interprozess-Startsperre ergänzt (`_start_lock`, `ocean.start.lock`,
  vom OS gehaltene Byte-Range-/flock-Sperre, wird beim Tod des Starters vom OS freigegeben;
  ein zweiter gleichzeitiger Start scheitert an der CLI geschlossen). Ursprungsbeschreibung: Zwei direkte
  Lebenszyklusaufrufe können derzeit die Leerer-Zustand-Vorprüfung passieren, bevor einer der
  Supervisoren den Laufzeitstatus schreibt. Der `<DEV-HOST>`-Logon-Task vermeidet das durch
  deaktiviertes `StartWhenAvailable` und genau einen Trigger; der Lebenszyklus selbst muss bei
  gleichzeitigen Starts jedoch geschlossen fehlschlagen.
- [x] Favicon ausgeliefert: `ellmos-core` beantwortet `/favicon.ico` mit seinem PWA-Icon
  (ellmos-core `6185504`); wirkt auf einem Host, sobald dessen Runtime-Provider-Kopie diesen
  Commit trägt. Ursprungsbeschreibung: Ein OCEAN-Favicon ausliefern oder die Favicon-Anforderung entfernen. Die aktuelle
  Browserabnahme ist gesund, protokolliert aber einen nicht funktionalen `/favicon.ico`-404.
- [ ] `<DEV-HOST>` tatsächlich neu starten und danach den unveränderten Task
  `EllmosOceanFullUserStart`, den exakten Tag-Checkout, das Prozess-Tupel, die Portbelegung, die
  HTTP-Identität und die Full-Ocean-Bereitschaft nachlesen.
  **2026-09-02: de facto geschehen und FEHLGESCHLAGEN.** Nach dem Boot um 21:04 lief der
  Logon-Task um 21:07:23 und endete mit Exit 4 (Runtime-Kind Exit 1 nach 21 s, Port 8810 nie
  gebunden). Ursache: 12 von 14 Runtime-Providern auf dem Spec-PYTHONPATH sind OneDrive-
  Lesekopien, und OneDrive.exe startete erst um 21:14:27 — sieben Minuten nach dem Task. Ein
  manueller `ocean.py start` danach ist grün. Ticket T-20260902-313385481 (Provider in den Workspace
  platzieren; kein OneDrive-Laufzeitpfad; Kind-stderr nach `logs/runtime.log`). Übergangsweise
  auf `<DEV-HOST>`: Task-Neustart bei Fehler 5× alle 2 min (XML-Backup in `logs/`). Bleibt offen,
  bis ein Reboot-Readback grün ist.
  **2026-09-02, später am selben Tag: beide Code-Fixes gelandet (b59d1ee).**
  `fetch_place.plan_and_fetch()` kopiert ("placed") jetzt jedes von Resolve gefundene Modul ohne
  exakte Bindung bei `--apply` nach `<workspace>/modules/<catalog_id>` und setzt dessen
  `local_path` dorthin um — genau wie die bereits bestehende Platzierung exakt gebundener
  Provider; `ocean.py start` spiegelt `sys.stderr` zusätzlich nach
  `<workspace>/logs/runtime.log` (pythonw hat keine Konsole, ein headless `LifecycleError`-Print
  — oder jede unbehandelte Ausnahme, da Pythons Default-Excepthook ebenfalls nach stderr
  schreibt — verschwand bisher spurlos, übrig blieb nur der nackte Exitcode). Auf `<DEV-HOST>` ohne
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
  bis ein echter `<DEV-HOST>`-Neustart es live bestätigt.
  **2026-09-10: Der echte Neustart hat endlich stattgefunden — und ist ERNEUT FEHLGESCHLAGEN,
  aus einem anderen Grund.** `LastBootUpTime 2026-09-10T19:42:24+02:00`; der Logon-Task lief um
  19:42:38 und endete wieder mit Exit 4. Die OneDrive-Ursache war beseitigt
  (`ocean.runtime-spec.json`: null OneDrive-Einträge, alle 14 PYTHONPATH-Verzeichnisse lokal),
  und der angeheftete Checkout trug bereits die 60-Sekunden-Frist (`bb12d541`). Das Kind lebte
  57,5 s (`started_at 17:43:27,8Z` → `stopped_at 17:44:25,4Z`), ohne eine einzige Uvicorn-Zeile
  auszugeben — bei jedem erfolgreichen Start erscheint `Started server process` binnen Sekunden,
  es kam also nie über seine Importe hinaus.
  **2026-09-12, Ursache gemessen: Der Start ist dateicache-dominiert, und 60 s liegen genau
  zwischen dem warmen und dem kalten Wert.** Zwei Läufe desselben unveränderten Installs, selber
  Task, selber Checkout: Der erste Start nach zwei Tagen Inaktivität erreichte `/api/health` 200
  nach **209,8 s**, ein unmittelbar folgender zweiter Start nach **38,9 s** — Faktor 5,4 allein
  durch den Cache-Zustand. Diese eine Zahl erklärt die ganze Vorgeschichte: Jeder Demand-Start
  und jede Staging-Probe war warm und grün (49,6 s am 2026-09-09), jeder Start zur Bootzeit war
  kalt und starb an der Frist. Bemerkenswert: Der 209,8-s-Lauf war selbst ein *Demand*-Start — er
  wäre auch unter der alten 60-s-Frist gescheitert. Das ist der erste direkte Beleg dafür, dass
  die Frist und nicht ein Defekt den Kaltstart tötet. Die Importe erklären es nicht (gemessen mit
  der echten Spec-Umgebung: `import ellmos_core.app` + `OceanOriginApp()` + beide Validatoren =
  10,8 s warm, 23,3 s bei kaltem Dateicache; `init_db()` läuft gegen eine 139-KB-SQLite-Datei).
  **Reparatur (host-lokal, keine Codeänderung): Der Logon-Task übergibt jetzt
  `--health-timeout 600`** — genau dafür wurde die Option geschaffen (`43072b1`/`b59d1ee`: „eine
  großzügige Obergrenze zählt nur für den wirklich-nur-langsamen Fall"). Ein tatsächlich toter
  Prozess scheitert weiterhin sofort über den `status == "stopped"`-Abbruch; die Obergrenze
  kostet also weder im Erfolgs- noch im Absturzfall etwas, sie kauft nur im Fall „lebt, aber
  langsam" Zeit. Der 60-s-Standard bleibt für interaktive Nutzung unverändert. Task-XML-Backup:
  `logs/EllmosOceanFullUserStart.before-health-timeout-20260912.xml`.
  **Ende-zu-Ende mit dem finalen Wert verifiziert** (2026-09-12 09:00:28, aus gestoppter
  Laufzeit): `LastTaskResult 0`, einziger Listener `127.0.0.1:8810` (PID 5184), `/api/health` 200
  nach 38,9 s, Receipt `running`. **Bleibt offen, bis ein echter Neustart es bestätigt** — der
  Kaltstartpfad selbst ist ohne Neustart nicht reproduzierbar. `<FRESH-HOST>` braucht sehr
  wahrscheinlich dasselbe Task-Argument (dort prüfen, nicht unterstellen).
- [ ] Klären, warum ein OCEAN-Start überhaupt 39 s warm und 210 s kalt braucht. Durch Messung am
  2026-09-12 ausgeschlossen (siehe Reboot-Punkt oben): Modulimporte, `OceanOriginApp()`,
  `validate_production_security()`, `validate_model_locality()` und `init_db()` machen zusammen
  ~11 s warm aus. Der Rest liegt zwischen dem Spawn des Kindes und seiner ersten Health-Antwort,
  also innerhalb von `uvicorn.run()` bzw. im ASGI-Lifespan des `ellmos-core`-Providers — ein
  anderes Modul, daher eine eigene Untersuchung. Solange das ungeklärt ist, ist die
  Health-Frist des Logon-Tasks eine Kompensation, keine Heilung.
  **Bytecode-Kompilierung als Ursache ausgeschlossen, gemessen am 2026-09-12.** Die Runtime-Spec
  setzt `PYTHONDONTWRITEBYTECODE=1`, jeder Start kompiliert also den gesamten Importbaum neu —
  ein naheliegender Verdächtiger. Lenkt man den Cache per `PYTHONPYCACHEPREFIX` in den Workspace
  und misst den echten Kindimport dreimal je Variante, ergibt sich ein Median von 8,37 s ohne
  gegen 7,80 s mit Cache: **0,58 s, rund 7 %**, während der einmalige Cache-Aufbau 25,4 s und
  10,5 MB in 644 `.pyc`-Dateien kostet. Gegen einen Start, der kalt 210 s braucht, ist das
  Rauschen; der Produktvertrag wurde deshalb bewusst NICHT geändert. Was die Zahlen dagegen
  zeigen: Der Unterschied kalt/warm wird vom **Dateisystem-Cache** bestimmt, nicht von der
  Kompilierung — derselbe Import dauert 23,3 s bei kaltem und 7,8-13,6 s bei warmem Cache. Die
  nächste Sonde sollte deshalb Dateizugriffe messen, nicht CPU.
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
  falls der Crosswalk stattdessen als Registry übergeben wird.
- [x] Die Reproduzierbarkeits-Implementierung für `T-20260830-702817310` ist als begrenzte
  Review-Einheit geschlossen. Der Recipe-Provider-PR `ellmos-development-system#91` aktualisiert
  ausschließlich die unabhängig nachgemessenen Skills-Registry- und Crosswalk-Pins und hält die
  unveränderliche Repository-URI der Registry fest. OCEAN liefert jetzt einen inhaltsgehashten
  Quellen-Pin-Vertrag aus und verwirft einen schmutzigen/falschen Recipe-Checkout sowie Binding-,
  Crosswalk- oder Skills-Registry-Drift vor Resolve/Fetch. Die Review-Branches werden durch diese
  Einheit weder gemergt noch veröffentlicht; andere Modul-/MCP-Quellendriften bleiben außerhalb.

## Freigabebreite

- [ ] Eine vollständige frische Full-Ocean-Installation auf einem anderen Rechner ausführen.
- [ ] Die standardmäßig geschlossene öffentliche OPEN-OCEAN-Allowlist unabhängig von FULL OCEAN
  ableiten und testen.
- [ ] Die funktionale BACH-Parität weiterführen; neu entdeckte BACH-Eigenheiten nur ausnahmsweise
  und wertgebunden in einem eigenen Modulzyklus extrahieren.
  **Historische Reifemessung vom 2026-09-12.** Ein Zyklus im Sinne von Bauplan §5 verdrahtet ein
  Modul in BACH und/oder OCEAN und schaltet danach den abgelösten Altpfad ab. Die Tabelle hält die
  fünf damals gemessenen Kandidaten als Beleg fest; sie beschreibt nicht den aktuellen Zustand:

  | Paar | Klon | fremde Dirty-Dateien | Zielmodul importierbar | BACH-Altpfad |
  |---|---|---|---|---|
  | `agent-launcher` | ja | 0 | **nein** | `system/hub/agent_launcher.py`, 2637 Zeilen |
  | `ellmos-scheduler` | ja | 0 | **nein** | `system/hub/scheduler.py`, 2092 Zeilen |
  | ~~`swarm-ai`~~ | ja | 0 | siehe Nachzertifizierung unten | `system/hub/schwarm.py`, 793 Zeilen |
  | `web-scraper` | ja | 5 | **nein** | `system/hub/web_scrape.py`, 415 Zeilen |
  | `doc-services` | ja | 1 | **nein** | `system/hub/_services/document` |

  Zu diesem Zeitpunkt löste kein Ziel über `importlib.util.find_spec` auf, und BACH hielt zu keinem
  einen Seam. Die beiden größten Paare waren außerdem zu breit für einen begrenzten
  Äquivalenzzyklus. Spätere Arbeiten an `web-scraper` und `doc-services` sowie spätere BACH-Lock-
  und Branchzustände haben diese Momentaufnahme überholt; der aktuelle Stand ist aus dem
  Programmticket zu lesen und darf nicht aus dieser Tabelle abgeleitet werden.

  **Nachzertifizierung von `swarm-ai` und OC-C-Entscheid (2026-09-15): Paar gestrichen.** Die
  frühere Beschreibung als Experimente-/Doku-Sammlung ohne konsumierbare API war sachlich falsch.
  Das saubere kanonische Repository auf `63476d0` enthält einen PEP-621-Paketvertrag (seit
  `5393acd`, 2026-08-13), fünf Konsolen-Einstiegspunkte und wiederverwendbare Python-APIs; aktuell
  bestehen 220/220 Tests sowie Ruff. Ein echter Wheel-Build scheitert noch an widersprüchlichen
  PEP-639-Lizenzmetadaten, daher ist dies kein Paketfreigabe-Claim. D-20260913-003, Frage 2 /
  OC-C = B wird deshalb eng und wahrheitsgemäß umgesetzt: Das vorgeschlagene P8-Paar
  `swarm-ai` ↔ BACH `system/hub/schwarm.py` wird gestrichen, weil weder ein kompatibler Ersatz-Seam
  noch ein zweiter Abnehmer belegt ist. Das eigenständige öffentliche experimentelle Toolkit
  bleibt unverändert erhalten; es wird weder zurückgebaut noch gelöscht oder als reine
  Dokumentation umetikettiert. Eine spätere Integration benötigt einen neuen wertgebundenen
  Vorschlag und Kompatibilitätsbelege.
- [x] (2026-09-02) Gemergt: `gardener` #4 (master ddd3a84), `ellmos-controlcenter-mcp` #9 (main 34cd95d); `policy-registry` #3 zugunsten des Decision-Index-Pfad-Slices geschlossen (https://github.com/ellmos-ai/policy-registry/pull/4). Übernahme (hostlokaler Registry-Seed, ControlCenter-Konfiguration, ccm-0.6.0-npm-Release) bleibt offen. Ursprünglich: Die offenen Governance-PRs mergen und übernehmen (`policy-registry` #3, `gardener` #4,
  `ellmos-controlcenter-mcp` #9) — alle offen, mergefähig, CI grün zum Stand 2026-08-30, keiner
  gemergt. Hostlokale Registry-Initialisierung, Gardener-Systemquellen und
  ControlCenter-Konfiguration werden erst danach relevant.
- [ ] Geräteseitige OS-Konto-Kopplung für die OCEAN-Benutzeridentität prüfen (ein
  Windows-/macOS-Konto je Gerät) statt eines zusätzlichen App-Passworts; Anlass: Die
  `<FRESH-HOST>`-Installation läuft ohne OCEAN-Benutzer, während `/control/` und `/api/health`
  ohne Auth erreichbar bleiben.

Diese Punkte autorisieren keine Sichtbarkeitsänderung. (Das Veröffentlichungsgatter
`PRIVATE.txt` wurde am 2026-09-11 durch den Entscheid D-20260909-003 aufgehoben; die
Sichtbarkeit selbst schaltet weiterhin der Eigentümer.)
