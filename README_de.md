<img src="assets/banner.png" width="100%" alt="open-ocean Banner">

# open-ocean

**Free the ocean.**

Das kostenlose Community-System des ellmos-Ökosystems.

*[English](README.md)*

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/ellmos-ai/open-ocean/actions/workflows/ci.yml/badge.svg)](https://github.com/ellmos-ai/open-ocean/actions/workflows/ci.yml)
[![Pytest](https://img.shields.io/badge/pytest-180%20bestanden-brightgreen.svg)](tests/)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-informational.svg)](https://github.com/ellmos-ai/open-ocean)
[![Security Policy](https://img.shields.io/badge/security-48h%20SLA-blue.svg)](SECURITY.md)
[![Privacy](https://img.shields.io/badge/privacy-100%25%20Local--First-brightgreen.svg)](SECURITY.md)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![LLM Ready](https://img.shields.io/badge/LLM--Ready-llms.txt-orange.svg)](llms.txt)
[![Changelog](https://img.shields.io/badge/changelog-v0.1.0-orange.svg)](CHANGELOG.md)
[![ellmos](https://img.shields.io/badge/ellmos-community%20full%20system-4b5563.svg)](https://github.com/ellmos-ai)
[![open-bricks](https://img.shields.io/badge/open--bricks-ecosystem-0284c7.svg)](https://github.com/open-bricks)

> [!NOTE]
> Für maschinenlesbare Architekturübersichten und LLM-Kontext siehe [`llms.txt`](llms.txt). Sicherheitsrichtlinien und Invarianten sind in [`SECURITY.md`](SECURITY.md) dokumentiert. Versionsänderungen werden in [`CHANGELOG.md`](CHANGELOG.md) gepflegt.

> **Privater Aufbau, und bewusst früh.** Dieses Repository existiert, bevor das System existiert —
> damit die Architektur einen Ort hat, während sie entschieden wird. Es öffnet sich, wenn das
> Wasser im Ozean ankommt; siehe *[Freigabebedingungen](#freigabebedingungen)*.

---

## Zuerst lesen: dieses Repository ist eine Baustelle

**Das veröffentlichte OPEN-OCEAN-System liegt hier noch nicht.** Die lokale FULL-OCEAN-
Entwicklungskomposition ist auf dem Entwicklungsrechner jetzt lauffähig: Sie kann einen deklarierten
`runtime.host` planen, installieren, starten, prüfen, mit einem Benutzer versehen, stoppen und neu
starten. Das ist der erste nutzbare OCEAN-Produktabschnitt, aber kein Claim auf BACH-Parität oder
OPEN-OCEAN-Veröffentlichungsreife. Die geprüfte 28-Bundle-Komposition löst jetzt jede deklarierte
Pflichtkomponente auf und meldet wahrheitsgemäß `full_composition: true`; ihre elf unaufgelösten
Modulreferenzen sind für diese Komposition optional.

OCEAN konsumiert die Rezepte aus ihrem kanonischen Repository, statt sie hierher zu kopieren. Die
Transaktionsschicht löst auf, prüft, holt, platziert, aktiviert und rollt zurück; die
Lebenszyklusschicht betreibt die ausgewählte Laufzeit in einer ausdrücklichen lokalen Sandbox. Der
aktuelle Full-Dev-Host ist das private `ellmos-core`, über seine Fähigkeit ausgewählt und nicht als
künftige OPEN-OCEAN-Laufzeit fest verdrahtet.
Wenn die aufgelöste Komposition zusätzlich `unified-gui.host` bereitstellt, macht OCEAN diese
Operator-Oberfläche zu seinem Produkteinstieg. Die aktuelle Entwicklungsadresse lautet
`http://127.0.0.1:8810/control/`; der eigene Port trennt OCEAN vom eigenständigen
TerminPilot-PWA-Ursprung des Laufzeitanbieters. Ein OCEAN-eigener Ursprungsadapter leitet zusätzlich
`/` auf diesen Einstieg um, liefert OCEAN-Manifest und -Offline-Identität und entfernt
Anbieter-Service-Worker sowie -Caches, bevor sie die OCEAN-Adresse beanspruchen können.

| Repository | Was es ist | Zustand |
|---|---|---|
| **bundles** | die Rezept-Schicht: Manifeste, Katalog, Export-Werkzeug | privat, Freigabe Welle für Welle |
| **open-ocean** (hier) | der Systembau: Architektur, Installer, das Konsumierende | privat, früh |

## Der Name und die Architektur, die er trägt

Die ratifizierte Produktgrenze ist unter
[Produkt- und Stackgrenzen](architecture/PRODUKT-STACK-GRENZEN.md) dokumentiert:

- **OPEN OCEAN = PUBLIC**
- **PRIVATE OCEAN = PRIVATE, NICHT PROPRIETÄR**
- **FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN**
- **SPEEDBOAT = PROPRIETÄR + ausdrücklich ausgewählte OPEN-/PRIVATE-OCEAN-Teile**

Dieses Repository baut OPEN OCEAN und betreibt FULL OCEAN als private Entwicklungs- und
Testkomposition. SPEEDBOAT ist ein eigenständiger Geschwister-Stack, keine OCEAN-Edition und
kein Overlay.

Das Ökosystem benennt seine Ebenen nach Wasser, weil das Bild die Architektur trägt statt sie zu
schmücken:

| Begriff | Was es ist |
|---|---|
| **stream / Wasser** | der Prozess selbst — Daten, Arbeit, Ergebnisse, die durch alles hindurchfließen |
| **Bach / Rinnsal** | die wilden, gewachsenen Läufe: die ursprüngliche persönliche Vollinstanz |
| **water pipes** | dasselbe Wasser, gezähmt und modularisiert — Module und Bundles |
| **waterfall** | die deklarative Quelle: Baukasten, Rezepte, Kataloge |
| **ocean** | die Nachfolger-Produktfamilie; Endpunkt der Linie Bach → Rinnsal → Ozean |
| **open-ocean** | der Teil, der allen gehört: das kostenlose Community-System |
| **private-ocean** | private, nicht proprietäre OCEAN-Komponenten |
| **full-ocean** | OPEN OCEAN + PRIVATE OCEAN; die vollständige OCEAN-Entwicklungs-/Testkomposition |
| **speedboat** | ein eigenständiger proprietärer Stack, der gemeinsame OCEAN-Teile ausdrücklich auswählt |

Die leitende Regel ist ein Erhaltungssatz: **Extraktion ändert das Bett, nie das Wasser.** Umbau
muss die Funktion erhalten — „gleiche Wassermenge" heißt Funktionsparität. Auch das ist keine
Zierde, sondern die Messlatte, die dieses Repository für seine Freigabe überspringen muss.

Der größte Teil der Extraktion ist bereits erfolgt. Die aktuelle Arbeit macht das bisherige BACH
modularer, indem seine Innereien durch die kanonischen Module und Bundles ersetzt werden, während
OCEAN als Nachfolger fertiggestellt wird. Eine wertvolle BACH-Eigenheit kann ausnahmsweise noch
extrahiert werden, aber nur über ein eigenes Gate. BACH bleibt durch dieselben Module wie OCEAN
versorgt; ein späterer Wechsel in LTS, Stillstand oder Archiv bleibt eine ausdrückliche
Produktentscheidung und folgt niemals automatisch aus diesem Plan.

## Was tatsächlich hier liegt

```
architecture/
  open-ocean.skeleton.v1.json   which recipes the system intends to consume, pinned by hash
  ocean-full-dev.component-bindings.v1.json  exakte, nicht-autoritative Modul-Integrationspins
  INSTALLER-TARGET.md           what the installer has to become, and what it must not do
  OCEAN-DEV-BUILD-PLAN_2026-08-18.md  staged build plan and verified foreign-host integration evidence
  BACH-EXTRACTION-ROADMAP.md    extraction order, parity gates and Cluster 9 kernel map
  bach-parity-baseline.v1.json  machine-readable registry and Cluster 9 coverage baseline
  bach-k9-data-contract.v1.json pinned dbsync/snapshot operation and fixture contract
  bach-k9-dbsync-adapter.v1.json thin lifecycle-adapter specification
  session-checkpoint-capability.v1.json boundary of the correct snapshot carrier
tools/
  audit_bach_handlers.py        side-effect-free source audit against that baseline
  check_k9_data_contract.py     static BACH check plus two synthetic carrier fixtures
  resolve_bundles.py            Resolve+Verify: bundle refs -> flat, hash-checked component plan
  host_adapters.py              vendor-neutral Activate: read-only readiness check plus write-side
                                 activate_skill/rollback_activate_skill (Claude Code as reference)
  fetch_place.py                Fetch+Place for module: components, SHA-pinned, fail-closed (no
                                 silent default-branch fallback)
  ocean_dev.py                  single entry point: Resolve -> Verify -> Fetch/Place -> Activate for
                                 one ring or a complete system manifest; dry-run by default,
                                 --apply for real writes, --rollback
  ocean_lifecycle.py            capability-driven plan/up/status/down/user lifecycle
  runtime_supervisor.py         authenticated loopback supervisor for one runtime instance
  runtime_user.py               password-safe user bootstrap delegated to the runtime
ocean.py                        user-facing OCEAN Full Dev CLI
PRIVATE.txt                     the publication gate, committed on purpose
```

Das Gerüst referenziert 13 Bundles in zwei Ringen — den Funktionskern und die Breite darum herum.
Es **referenziert** sie: Kein Manifest wird hierher kopiert. Kopien würden in dem Moment
auseinanderlaufen, in dem das Rezept-Repository weitergeht, und ließen dieses Repository weiter
erscheinen, als es ist.

### Lokale Kompositionsmodi

- Das Repository-Gerüst bildet den öffentlichen Umfang mit 13 Bundles ab; auswählbar sind Ring
  `1`, `2` oder `all`.
- OCEAN Full Dev konsumiert das vorhandene externe Vollsystemmanifest `ellmos.system.v1` und alle
  28 OCEAN-Familien-Referenzen in `bundle_refs[]`. Proprietäre SPEEDBOAT-Bundles sind
  ausgeschlossen. Manifest und private Rezepte bleiben in ihren kanonischen Ablagen; nichts davon
  wird in dieses Repository kopiert.

```text
python tools/ocean_dev.py --bundles-root <recipe-projection> \
  --system-manifest <ellmos-development-fullsystem/system.v1.json>
```

Ohne `--apply` ist dies ein rein lesender Dry-run. Ein Systemmanifest lässt sich nicht mit einem
nummerierten Ring kombinieren; Teilarbeit wird adaptiv als eigener Bundle-Zyklus ausgewählt und
nicht durch stilles Kürzen der deklarierten Full-Dev-Komposition.

Das standardmäßige `--component-bindings`-Overlay schließt Benennungslücken zwischen Rezept und
Anbieter, ohne das kanonische Rezept oder den Modulkatalog zu verändern. Jede Bindung ist exakt und
schlägt im Zweifel geschlossen fehl: Komponentenreferenz, Repository, vollständiger Commit-SHA,
Platzierung, ID des Anbieter-Manifests und erforderliche Fähigkeiten müssen übereinstimmen und der
Checkout muss sauber sein, bevor OCEAN den Anbieter als aufgelöst wertet. Das ausgelieferte Overlay
bindet derzeit `module:software-endpoint-registry` an `system-explorer` und die getrennten logischen
Rollen `module:automation-registry` und `module:automation-runtime` an unabhängig gepinnte
Platzierungen von `automation-master`.

Der Produktlebenszyklus liegt im Wurzelverzeichnis:

```text
python ocean.py plan <composition arguments>
python ocean.py up <composition arguments> --apply
python ocean.py start --workspace <local-sandbox>
python ocean.py start <rolle> --manifest <ellmos-module.v2.json> [--provider <name>]
python ocean.py status --workspace <local-sandbox>
python ocean.py user add --workspace <local-sandbox> --username <name> --email <address>
python ocean.py down --workspace <local-sandbox>
```

`python ocean.py --help` und die Hilfe des jeweiligen Unterbefehls zeigen alle Argumente. Das
Passwort wird verdeckt abgefragt und nie als Prozessargument übergeben; lokale Automatisierung kann
`--password-stdin` verwenden. `ocean up` verwendet standardmäßig den eigenen OCEAN-Port `8810`.
`ocean start` startet den bereits installierten, geprüften Snapshot ohne erneute Abfrage einer
inzwischen veränderten Live-Rezeptautorität. Nach einem Betriebssystem- oder Prozessverlust kann
der Befehl außerdem einen veralteten `running`-Status wiederherstellen, sofern weder der
authentifizierte Kontrollkanal noch der aufgezeichnete Runtime-Port aktiv ist.
Mit einer positionalen Rolle leitet `ocean start <rolle>` stattdessen an
denselben Einstieg `python -m unified_gui.console start` aus Wheelhouse Lower
Decks weiter. Der Befehl betritt dabei den Runtime-Lifecycle nicht und verändert
den installierten Workspace nicht. Fehlt die optionale Konsole, meldet OCEAN
`[FALLBACK]` und verwendet denselben Manifesteintrag über task-master, COMA oder
den Modulstarter. `--dry-run` belegt die aufgelöste Kette ohne Anbieterstart.
Unter Windows wiederholt der Supervisor außerdem eine vorübergehend blockierte atomare Ersetzung
der Statusdatei innerhalb eines begrenzten Ein-Sekunden-Fensters. Damit kann ein erfolgreicher
Stopp keinen veralteten `running`-Eintrag zurücklassen.
Auf ASUS-GEI startet der verborgene Logon-Task mit eingeschränkten Benutzerrechten
`EllmosOceanFullUserStart` jetzt den exakten Checkout
`ocean-full-laptop-hafenlicht-20260829` und `C:\_Local_DEV\ocean-full`. Seine kontrollierte
Bedarfsstart-Abnahme endete mit Task-Ergebnis `0`, genau einem Supervisor, einem Kind und einem
Listener. Das belegt den konfigurierten Logon-Pfad, aber keinen tatsächlich ausgeführten Neustart.
Anschließend wurde der frühere BACH-Session-Sidecar über BACHs eigene CLI beendet.

## Status

**Dieses Repository:**

| | |
|---|---|
| Architektur-Gerüst | vorhanden, 13 Bundles referenziert |
| BACH-Extraktionsbasis | vorhanden — 114 quellseitige Namen; historische 113er Runtime-Messlatte bleibt erhalten; erneut geprüft am 2026-08-18 (106 Handler-Klassen, +1 gegenüber der 2026-08-08-Basis — zurückverfolgt auf eine hostgebundene Duplikatdatei in BACH, `upgrade-WORKSTATION-LG.py` neben `upgrade.py`; hier NICHT behoben, BACH liegt außerhalb des Änderungsumfangs dieses Repositories). `registered_names` unverändert bei 114. |
| K9-1 Daten-/Checkpoint-Gate | zwei Träger-Fixtures grün; Adapter und BACH-Äquivalenz bleiben offen |
| Installer und Lebenszyklus | **Resolve, Verify, SHA-gepinnte Fetch/Place-Schritte, exakte Anbieterbindungen, isolierte Skill-Aktivierung, erhaltende Aktivierungsprotokollierung, zielvalidiertes Rollback, Wiederherstellung des installierten Snapshots, Runtime-Start/Status/Stopp/Neustart und delegierte Benutzeranlage sind implementiert.** Der abgenommene Windows-Full-Ocean-Workspace ist `C:\_Local_DEV\ocean-full`. Er bestätigt **28/28** OCEAN-Familien-Bundle-Pins, löst **54 von 65 Modulreferenzen und alle 80 Skills** auf, hat keine fehlende Pflichtkomponente, meldet `full_composition: true` und läuft unter `http://127.0.0.1:8810/control/`. Die elf unaufgelösten Modulreferenzen sind optional. Der getrennt platzierte Anbieter für `automation-runtime` bestand am Commit `c2de7188626510b181c4ecf2708c15f2395e32aa` die Abnahme für natives Provider-/Scheduler-Rücklesen, unveränderliche Belege, Bereinigung und begrenzte Statistik. Die Vorprüfung der aktiven Laufzeit stoppt ein zweites `up --apply` vor jedem Fetch/Activate-Schreibzugriff. Der produkteigene Ursprung leitet Root auf OCEAN um und entfernt alte Anbieter-PWA-Worker und -Caches, ohne Cookies oder anderen Browserspeicher zu löschen. Live-HTTP und ein echter Browser bestätigen `307 / → /control/`, die Oberfläche `OCEAN Full Dev` und keine TerminPilot-Produktmarker. Ein echter Stopp-/Start-/Stopp-/Start-Zyklus belegt die Windows-Statusdatei-Reparatur. Die Suite umfasst jetzt **137 grüne Tests**. Dies ist für den deklarierten Pflichtumfang ein kompositionsvollständiger privater Full-Dev-Build, aber weder eine OPEN-OCEAN-Freigabe noch ein BACH-Paritätsclaim. Der Full-Ocean-Auswahlcommit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` ist in den kanonischen Rezept-Branch `main` übernommen; dessen Nachlesestand lautet `b13f1b11626141d6dc6927028dc10008bc406866`. Siehe [gestuften Bauplan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Laufzeit | **für das private Full Dev verfügbar** über den deklarierten `runtime.host`-Anbieter `ellmos-core`, mit dem aufgelösten `unified-gui.host` als OCEAN-Operator-Oberfläche; eine OPEN-OCEAN-Laufzeit wird noch nicht ausgeliefert, und der private Anbieter ist keine öffentliche Abhängigkeit |
| Rezepte | im Rezept-Repository gepflegt, nicht hier |

**Die Ampel** — Freigabebedingung 1 geht grün, wenn jedes referenzierte Bundle grün ist, also jede
seiner Komponenten öffentlich und geprüft. Der Umfang zählt hier: Das Gerüst dieses Repositories
referenziert genau **13** der rund 30 Bundles des Ökosystems (siehe
[das Gerüst](architecture/open-ocean.skeleton.v1.json)); Bedingung 1 betrifft diese 13, nicht den
gesamten Katalog.

| | |
|---|---|
| Von diesem Repository referenzierte Bundles | **13** |
| Davon Komponenten öffentlich verifiziert (2026-08-18) | **13 / 13** |
| Geprüfte Einzelkomponenten | 18 Module, 1 Access-Surface-Repository (`ellmos-homebase-mcp`), 27 Skills (im öffentlichen `ellmos-ai/skills`-Katalog), 1 optionale Software-App (`MediaBrain`) — alle live per `gh repo view`/Katalog-Abgleich bestätigt, NICHT über das `visibility`-Feld der eigenen Modul-Manifeste (das ist eine Zielklassifikation und kann dem tatsächlichen GitHub-Stand hinterherhinken) |
| Nicht anwendbar auf diese Prüfung | 3 `access_surface`-Referenzen auf kommerzielle Agent-Anbieter/Abos/APIs (kein Repository, kein Öffentlich/Privat-Zustand) |

Keines der vier Repositories, die am 2026-08-08 andere Teile des Ökosystems blockierten
(`ellmos-core`, sowie die drei inzwischen öffentlichen `ellmos-scheduler`, `system-explorer`,
`policy-registry`), wird vom 13-Bundle-Gerüst dieses Repositories überhaupt referenziert — sie
sperren Bundles außerhalb dieses Umfangs (`core-discovery`, `prompt-workflow`, `runtime-options`,
`governance-assurance`, `automation-control`). Bedingung 1, streng für das gelesen, was dieses
Repository tatsächlich referenziert, ist zum 2026-08-18 erfüllt. Was die Veröffentlichung noch
blockiert, sind die Bedingungen 2 und 3 unten, nicht Bedingung 1.

### WORKSTATION-LG-Fresh-Install (2026-08-30)

Ein zweiter, unabhängiger Windows-Host hat dieselbe Full-Dev-Komposition am 2026-08-30
durchlaufen: `WORKSTATION-LG`, Workspace `C:\_Local_DEV\ocean-full`, Zielverzeichnis existierte
vorher nicht (ein echter Fresh-Install). Eingangs-Worktrees: `open-ocean` am Tag
`ocean-full-laptop-hafenlicht-20260829` (`243a703c60e295f050a2dc68bdde13ef8e847d29`),
`ellmos-development-system` an `1b461c9cb900ada15b8e104f2586a6b4a1ea5278` — beide detached und
sauber. Tests vor der Installation: pytest 137/137, unittest 125/125, ruff ohne Befunde,
`compileall` Exit 0.

Der Plan vor dem Apply meldete 28/28 Bundles (`all_ok`), 80/80 Skills, aber nur 51/65 Module
(`full_composition: false`) — drei Pflicht-Provider waren noch nicht lokal vorhanden. Der Apply
holte sie per Git-Fetch-at-SHA nach `<workspace>\modules\`:
`automation-registry@ad40de721615518e409b53b00ed4b2a49840db28` und
`automation-runtime@c2de7188626510b181c4ecf2708c15f2395e32aa` (beide aus
`dev-bricks/automation-master.git`) sowie
`software-endpoint-registry@ec50c92319ba8fc262d695b86818fc85666feff7` (aus
`ellmos-ai/system-explorer`) — anschließend alle drei als saubere, detached Checkouts. Nach dem
Apply: 28/28 Bundles, 54/65 Module, 80/80 Skills, keine fehlende Pflichtkomponente,
`full_composition: true`, Laufzeit `ellmos-core` unter `http://127.0.0.1:8810/control/`.

Ein vollständiger `down`/`start`-Lebenszyklus wurde durchlaufen (gestoppt, Port frei, keine
verwaisten Prozesse, danach erneut laufend ohne Zustandswiederverwendung), gefolgt von denselben
HTTP-/Browser-/Prozessprüfungen wie oben.

Der verborgene Logon-Task mit eingeschränkten Benutzerrechten `EllmosOceanFullUserStart` (Trigger
`AtLogOn`, Principal `lukas`, `LogonType Interactive`, `RunLevel Limited`, verborgen) startet
`pythonw.exe` gegen `ocean.py start --workspace "C:\_Local_DEV\ocean-full"` im gepinnten
Eingangs-Worktree. Ein kontrollierter Bedarfsstart am 2026-08-30 lieferte `LastTaskResult 267009`
(`SCHED_S_TASK_RUNNING`, der erwartete Code für einen absichtlich dauerhaft laufenden
Serverprozess, nicht `0`), mit genau einem Supervisor (PID 6460) und einem Kind (PID 37676), beide
unter `pythonw.exe`, wobei das Kind der einzige Listener auf `8810` ist; `full_composition: true`
und die Produktidentität blieben danach bestätigt. Ein tatsächlicher Geräte-Neustart wurde nicht
getestet.

Auf diesem Host lief zu keinem Zeitpunkt ein BACH-Session-Sidecar (`service.running: false`,
`pid: null`), daher wurde keiner gestoppt; BACH-Code, -Datenbanken, -Tasks und -Konfiguration sind
unverändert. Für OCEAN wurde auf diesem Host kein Benutzerkonto angelegt — eine bewusste
Entscheidung, keine Installationslücke; siehe TODO zur geräteseitigen OS-Konto-Kopplung, auf die
das hinauslaufen soll.

## Freigabebedingungen

Dieses Repository trägt ein bedingtes Publikations-Gate (`PRIVATE.txt`, bewusst committet, damit
das Gate dort sichtbar ist, wo Sichtbarkeit geschaltet wird). Es öffnet sich, wenn alle vier
Bedingungen nachweislich erfüllt sind:

1. **Grüne Bestandteile** — jedes referenzierte Bundle ist grün: jede seiner Komponenten
   öffentlich und geprüft. **Erfüllt zum 2026-08-18** für den 13-Bundle-Umfang dieses
   Repositories — siehe Ampel-Tabelle oben.
2. **Schleusen-Test bestanden** — die Gesamtleitung trägt: eine frische Installation aus diesen
   Rezepten erreicht auf einer Maschine, die nicht der Entwicklungsrechner ist, einen
   arbeitsfähigen Zustand. **Noch nicht erfüllt.** Die Installer-Naht bleibt durch den Mac-Studio-
   Lauf vom 2026-08-20 auf einem Fremdrechner integrationsgeprüft. Am 2026-08-29 absolvierte der
   Entwicklungsrechner zusätzlich einen echten Full-Dev-Zyklus aus Plan/Apply/Start/Status/Stopp/
   Neustart. Die erste Abnahme des Wurzelpfads belegte nur den Transport und stellte sich später
   als TerminPilot-Fachoberfläche des Anbieters statt OCEAN heraus. Der korrigierte Zyklus stellt
   nun die aufgelöste Operator-Oberfläche unter `127.0.0.1:8810/control/` bereit und prüft sie im
   echten Browser. Eine spätere Regression mit persistentem Browserprofil übertrug zusätzlich Root,
   Manifest, Offline-Identität und Worker-Bereinigung dieses Ursprungs an OCEAN. Die Komposition
   auf dem Entwicklungsrechner löst nun zusätzlich das getrennte `module:automation-runtime` auf,
   hat keine fehlende Pflichtkomponente und meldet `full_composition: true`. Das bringt OCEAN
   substanziell voran, ist aber weiterhin nicht der geforderte frische
   Fremdrechner-Vollsystembeleg. Der aktuelle Apply-Lauf bestätigt alle 28 Referenzen gegen den
   Full-Ocean-Auswahlcommit `1b461c9cb900ada15b8e104f2586a6b4a1ea5278`. Er ist in den
   kanonischen Rezept-Branch `main` übernommen; dessen Nachlesestand lautet
   `b13f1b11626141d6dc6927028dc10008bc406866`. Die genauen Belege und die verbleibende Breite stehen im
   `architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md`.
3. **Parität für den Release-Umfang** — das System leistet, was es zu decken beansprucht. Ein
   kleinerer installierbarer Kern ist eine Bau-Etappe, kein Release. Der aktuelle Quell-Audit
   erfasst 114 erreichbare Namen und erhält zugleich den historischen 113er Runtime-Snapshot als
   Mindestzusage; siehe [Extraktionsroadmap](architecture/BACH-EXTRAKTIONSROADMAP.md). **Erneut
   gemessen am 2026-08-18** (nur lesend, BACH unangetastet): die 114er-Messlatte ist unverändert
   aktuell; siehe `architecture/bach-parity-baseline.v1.json` → `re_audit_2026-08-18`. Diese
   Bedingung verlangt aber mehr als eine Namenszählung: Die
   [Operationsmatrix für Cluster 9](architecture/BACH-EXTRAKTIONSROADMAP.md#operationsmatrix-für-cluster-9)
   ist der einzige Cluster mit laufender Arbeit (8 von 9 Clustern haben noch nicht begonnen), und
   darin tragen 0 von 30 Kommandonamen den Status `accepted` (funktional äquivalent) — 20 sind
   `candidate-partial`, 9 sind `gap`, 1 ist `alias`. Bedingung 3 ist damit **nicht annähernd
   erfüllt**; sie hängt an derselben Installer-/Laufzeit-Arbeit wie Bedingung 2.
4. **Publikationsprüfung bestanden** — Recht, Privacy und Lizenz geprüft, keine Blocker.
   **Durchgeführt am 2026-08-18** (Skill `repo-publish-check`, 10 Gates) — Verdikt und lokaler
   Bericht: `.GITHUBBOT/workflows/repo-publish-check/reports/ellmos-ai__open-ocean_2026-08-18.md`
   (bleibt lokal gemäß Skill-Regel, wird nicht in diesem Repository ausgeliefert).

Bedingung 2 ist die, nach der dieses Repository benannt ist. Die Schleusen zu öffnen und
zuzusehen, ob das Wasser wirklich ankommt, ist der Test, den keine Menge korrekter Manifeste
ersetzt. Von den vier Bedingungen sind 1 und 4 erledigt. Bedingung 2 besitzt jetzt eine geprüfte
Transaktionsnaht und eine arbeitsfähige Laufzeit auf dem Entwicklungsrechner, aber noch keine
vollständige frische Installation auf einem Fremdrechner; Bedingung 3 hat weiterhin keine
BACH-Funktionsparität. `PRIVATE.txt` bleibt deshalb wirksam.

## Lizenz

MIT, am 2026-08-08 vom Eigentümer gewählt und als [`LICENSE`](LICENSE) committet. Damit ist der
Lizenzteil von Freigabebedingung 4 erledigt; deren Rechts- und Privacy-Teil bleibt offen, bis die
Publikationsprüfung gelaufen ist.
