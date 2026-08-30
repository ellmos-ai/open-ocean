# Änderungsprotokoll

*[English](CHANGELOG.md)*

## Unveröffentlicht — 2026-08-30

### Geprüft

- Ein zweiter, unabhängiger Fresh-Install-Host, `WORKSTATION-LG`, erreichte dasselbe Ergebnis:
  Eingangs-Worktrees `open-ocean@243a703c` (Tag `ocean-full-laptop-hafenlicht-20260829`) und
  `ellmos-development-system@1b461c9c`, beide detached und sauber; Suite vor der Installation
  pytest 137/137, unittest 125/125, ruff ohne Befunde, `compileall` Exit 0.
- Der Plan vor dem Apply meldete 28/28 Bundles, 80/80 Skills, aber nur 51/65 Module
  (`full_composition: false`) — drei Pflicht-Provider waren noch nicht lokal vorhanden. Der Apply
  holte `automation-registry@ad40de721615518e409b53b00ed4b2a49840db28` und
  `automation-runtime@c2de7188626510b181c4ecf2708c15f2395e32aa` (beide aus
  `dev-bricks/automation-master.git`) sowie
  `software-endpoint-registry@ec50c92319ba8fc262d695b86818fc85666feff7` (aus
  `ellmos-ai/system-explorer`) als saubere, detached Checkouts.
- Nach dem Apply: 28/28 Bundles, 54/65 Module, 80/80 Skills, keine fehlende Pflichtkomponente,
  `full_composition: true`, unter `http://127.0.0.1:8810/control/`.
- Ein vollständiger `down`/`start`-Lebenszyklus bestand (gestoppt, Port frei, keine verwaisten
  Prozesse, danach erneut laufend ohne Zustandswiederverwendung), gefolgt von denselben
  HTTP-/Browser-/Prozessidentitätsprüfungen.
- Der verborgene Logon-Task mit eingeschränkten Benutzerrechten `EllmosOceanFullUserStart`
  startete den gepinnten Checkout bei der Bedarfsabnahme: `LastTaskResult 267009`
  (`SCHED_S_TASK_RUNNING` — der erwartete Code für einen absichtlich dauerhaft laufenden
  Serverprozess, nicht `0`), genau ein Supervisor (PID 6460) und ein Kind (PID 37676) unter
  `pythonw.exe`, wobei das Kind der einzige Listener auf `8810` ist; `full_composition: true`
  blieb danach bestätigt. Ein physischer Neustart wurde nicht getestet.
- Auf diesem Host lief kein BACH-Session-Sidecar (`service.running: false`, `pid: null`), daher
  wurde keiner gestoppt; BACH-Code, -Datenbanken, -Tasks und -Konfiguration sind unverändert.
- Auf diesem Host wurde kein Benutzer angelegt — eine bewusste Entscheidung (geräteseitige
  OS-Konto-Kopplung statt eines zusätzlichen App-Passworts), keine Installationslücke.

## Unveröffentlicht — 2026-08-29

### Hinzugefügt

- Gekoppelte englische/deutsche Produkt- und Stackgrenzen-Dokumente für OPEN OCEAN, PRIVATE OCEAN,
  FULL OCEAN und den eigenständigen Geschwister-Stack SPEEDBOAT, abgesichert durch Dokumentvertragstests.
- Wurzel-CLI `ocean.py` mit `plan`, `up`, `start`, `status`, `down` und `user add`.
- Fähigkeitsgesteuerte Auswahl genau eines aufgelösten `runtime.host`.
- Lokaler authentifizierter Runtime-Supervisor und Kompatibilitätsprojektionen für den
  ausgewählten Host.
- Passwortsichere delegierte Benutzeranlage; Passwörter erscheinen nicht in Prozessargumenten.
- Aufgelöste Komponentenmetadaten in Transaktionsberichten für Lebenszyklus-Konsumenten.
- Exakte, inhaltsgehashte Full-Dev-Komponentenbindungen für Integrationen zwischen Rezept und
  Anbieter; die erste Bindung ordnet `module:software-endpoint-registry` dem `system-explorer` am
  Commit `ec50c92319ba8fc262d695b86818fc85666feff7` zu.
- Die zweite exakte Bindung ordnet `module:automation-registry` dem `automation-master` am Commit
  `ad40de721615518e409b53b00ed4b2a49840db28` zu und verlangt `automation.registry`.
- Die dritte exakte Bindung ordnet die getrennte logische Rolle `module:automation-runtime` einer
  eigenen `automation-master`-Platzierung am Commit
  `c2de7188626510b181c4ecf2708c15f2395e32aa` zu und verlangt Runtime-Beobachtung,
  unveränderliche Belege und begrenzte Statistiken.
- Anbieterprüfung über Repository-Ursprung, exakten Git-HEAD, sauberen Checkout,
  Modulmanifest-Identität und deklarierte Fähigkeit, bevor eine gebundene Komponente als
  aufgelöst gelten kann.
- Fähigkeitsgesteuerter OCEAN-Produkteinstieg: Ein aufgelöster `unified-gui.host` wird unter
  `/control/` eingehängt, erhält den Bereitstellungstitel `OCEAN Full Dev` und läuft standardmäßig
  auf dem eigenen Port `8810` statt auf dem eigenständigen TerminPilot-PWA-Ursprung des
  Laufzeitanbieters.
- OCEAN-eigener Ursprungsadapter für Root-Umleitung, Produktmanifest und -Offline-Identität,
  Entfernung alter Service-Worker/Caches sowie Delegation der Anbieter-API.

### Behoben

- Die veraltete Gleichsetzung `ocean-full / open-ocean` wurde aus der aktuellen Produktsprache
  entfernt und im lebenden Plan als überholt markiert: OPEN OCEAN ist öffentlich, PRIVATE OCEAN
  ist privat und nicht proprietär, und FULL OCEAN ist exakt ihre Vereinigung.
- Der Reload-Prozess des Runtime-Hosts ist abgeschaltet; jeder Start erhält einen eigenen lokalen
  Secret-Key, damit ein authentifizierter Stopp keinen Reload-Kindprozess zurücklässt.
- Ein veralteter Stopp-Status der vorherigen Instanz löst beim Neustart keinen Fehlalarm mehr aus.
- Ein installierter Snapshot lässt sich nach dem Verschwinden von Supervisor und Kindprozess aus
  einem veralteten `running`-Status wiederherstellen, ohne eine veränderte Live-Rezeptautorität neu
  anzuwenden; belegte alte oder angeforderte Ports stoppen weiterhin sicher.
- Die falsche Produktadresse am Anbieter-Wurzelpfad wurde durch die aufgelöste
  OCEAN-Operator-Oberfläche ersetzt. Die frühere HTTP-200-Prüfung hatte TerminPilots
  Fachoberfläche akzeptiert, ohne die Produktidentität zu prüfen.
- Die Wurzel-CLI erzwingt UTF-8-Ausgabe, damit deutsche Hilfetexte unter Windows echte Umlaute
  behalten.
- Runtime-Importe schreiben kein Python-Bytecode mehr in externe Modulprojektionen.
- Vorhandene Rollback-Protokolleinträge bleiben über spätere Komponentendurchläufe erhalten;
  fehlerhafte, doppelte oder widersprüchliche Einträge stoppen die Transaktion vor Schreibzugriffen.
- Die Vorprüfung auf eine aktive Laufzeit und einen belegten Zielport liegt jetzt vor der
  Apply-Transaktion. Ein zweites `up --apply` kann nichts mehr holen oder aktivieren, bevor es die
  bereits laufende Sandbox meldet.
- Das verbleibende PWA-Identitätsleck auf Port `8810` ist geschlossen: Der Anbieter hatte am neuen
  OCEAN-Ursprung weiterhin eigenen Root, Manifest und root-weiten Worker ausgeliefert. Die
  Porttrennung allein war daher noch keine vollständige Produktgrenze.
- Vorübergehende Windows-Kollisionen beim atomaren Ersetzen der Supervisor-Statusdatei werden
  begrenzt wiederholt. Ein erfolgreicher Stopp hinterlässt jetzt `stopped`, keine temporäre
  Statusdatei, keinen Prozess und keinen Listener.

### Geprüft

- 137 Tests sind grün, einschließlich echter HTTP-Akzeptanz für Start, Status, Benutzeranlage,
  Stopp, Neustart, Wiederherstellung veralteter Zustände, Auswahl von Produktoberfläche und
  -ursprung, PWA-Bereinigung sowie schreibfreier Ablehnung einer bereits laufenden Sandbox.
- Der aktuelle private Full-Dev-Integrationskandidat bestätigt 28/28 OCEAN-Familien-Bundle-Pins,
  löst 54 von 65 Modulreferenzen und alle 80 Skills auf und ist unter
  `http://127.0.0.1:8810/control/` gesund.
- Der echte Anbieter für `software-endpoint-registry` wurde am exakten Pin geholt, projizierte zwei
  Software-Endpunkte (CLI und HTTP) und ergänzte einen Rollback-Protokolleintrag, ohne die 62
  vorhandenen Skill-Einträge zu verlieren.
- Der echte Anbieter für `automation-registry` ist ein sauberer abgetrennter Checkout am exakten
  `automation-master`-Pin und -Ursprung; sein Modulmanifest deklariert `automation.registry`.
- Der echte Anbieter für `automation-runtime` liegt als getrennte, saubere Platzierung am exakten
  `automation-master`-Pin und -Ursprung vor. Die Abnahme am installierten Anbieter bestätigte
  natives Provider- und Scheduler-Rücklesen, einen unveränderlichen inhaltsgehashten Beleg,
  begrenzte Statistiken und die Nichtausgabe roher Provider-/Scheduler-Inhalte.
- Das Therapy-Bundle ergänzt 18 aufgelöste und installierte Skills. Das erhaltende Protokoll
  umfasst jetzt 80 Skill-Einträge und drei Einträge gebundener Module.
- Die echte private Laufzeit legte einen zufälligen Wegwerfadministrator an, bestätigte dessen
  Passwort-Hash und kehrte nach der Bereinigung zum ursprünglichen Null-Benutzer-Stand zurück.
- Elf optionale Modulreferenzen bleiben unaufgelöst. Keine Pflichtkomponente fehlt; deshalb meldet
  die angewandte 28-Bundle-Entwicklungskomposition `full_composition: true`. Das ist weder ein
  öffentlicher Release- noch ein BACH-Paritäts- oder Fremdrechner-Vollsystemclaim.
- Der Full-Ocean-Auswahlcommit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` ist in den kanonischen
  Rezept-Branch `main` übernommen; dessen Nachlesestand lautet
  `b13f1b11626141d6dc6927028dc10008bc406866`.
- Ein frischer lokaler Blue-Green-Apply nach `C:\_Local_DEV\ocean-full` erhielt den vorherigen
  Workspace als Rücksprungpunkt, holte alle drei exakten Anbieterpins, erreichte
  `full_composition: true` und bestand nach der Windows-Statusdatei-Reparatur einen echten
  Stopp-/Start-/Stopp-/Start-Zyklus.
- Ein kontrollierter Stopp-/Apply-/Start-Abgleich behielt die gesunde OCEAN-Identität bei: Root
  liefert `307` auf `/control/`, das UTF-8-Manifest heißt `OCEAN Full Dev`, und kein
  TerminPilot-Produktmarker erscheint.
- Der installierte Snapshot wurde unter `http://127.0.0.1:8810/control/` neu gestartet. HTTP und
  ein echter Playwright-Browser zeigten `OCEAN Full Dev`, keine TerminPilot-/
  Terminkoordination-Marker und ein navigierbares Skills-Panel; Port `8800` lauschte nicht mehr.
- In einem persistenten Playwright-Profil wurde der absichtlich angelegte alte Anbieter-Cache
  entfernt, während ein unabhängiger synthetischer künftiger OCEAN-Cache erhalten blieb;
  Service-Worker-Registrierungen lagen bei null, `/` leitete auf die OCEAN-Übersicht um, und der
  UTF-8-Titel behielt Gedankenstrich und deutsches `Ü` ohne Ersatzzeichen.
- Der verborgene Logon-Task mit eingeschränkten Benutzerrechten
  `EllmosOceanFullUserStart` startete den gepinnten Laufzeit-Checkout bei der Bedarfsabnahme mit
  Task-Ergebnis `0`, genau einem Supervisor-/Kind-/Listener-Tupel und gesundem Full-Ocean-Status.
  `StartWhenAvailable` ist bewusst aus, damit die Registrierung nicht mit einem manuellen Beleglauf
  kollidiert. Das bestätigt den Task-Pfad, aber keinen physischen Neustart.
- BACHs früherer Session-Sidecar wurde nach der OCEAN- und Logon-Task-Abnahme sauber über seine
  native CLI beendet. Die operative Task-Race-Lektion liegt als USMC-Lektion `62` vor.

Ein Integrations-Checkpoint-Tag ist kein öffentliches Release. Dieser Eintrag enthält weder eine
Sichtbarkeitsänderung noch eine Änderung an `PRIVATE.txt`.
