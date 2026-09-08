<img src="assets/banner.png" width="100%" alt="open-ocean Banner">

# open-ocean

**Free the ocean.**

Das kostenlose Community-Vollsystem des ellmos-Ökosystems.

*[English](README.md)*

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](pyproject.toml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/ellmos-ai/open-ocean/actions/workflows/ci.yml/badge.svg)](https://github.com/ellmos-ai/open-ocean/actions/workflows/ci.yml)
[![Pytest](https://img.shields.io/badge/pytest-107%20bestanden-brightgreen.svg)](tests/)
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

**Das veröffentlichte Vollsystem liegt hier noch nicht.** Ein transaktionaler Installer-Kern ist
inzwischen vorhanden und unter Windows und macOS erprobt, aber es gibt weiterhin keine eigene
Laufzeit mit BACH-Parität — und bewusst keine Kopien der Rezepte. Was hier liegt, ist die
Architektur und die erste ausführbare Systembau-Schicht: welche Rezepte das System konsumiert, wo
sie leben und wie sie aufgelöst, geprüft, geholt, platziert, aktiviert und zurückgerollt werden.

Wer etwas heute Nutzbares sucht, findet es in der Rezept-Schicht — einem eigenen Repository mit
den Bundle-Manifesten, das Welle für Welle freigegeben wird. Die Rezepte sind Monate vor dem
System fertig, das sie konsumiert, und genau deshalb liegen sie nicht hier: Ein Repository, das
Rezepte unter dem Namen des Systems ausliefert, sähe fertig aus, während das System es nicht ist.

| Repository | Was es ist | Zustand |
|---|---|---|
| **bundles** | die Rezept-Schicht: Manifeste, Katalog, Export-Werkzeug | privat, Freigabe Welle für Welle |
| **open-ocean** (hier) | der Systembau: Architektur, Installer, das Konsumierende | privat, früh |

## Der Name und die Architektur, die er trägt

Das Ökosystem benennt seine Ebenen nach Wasser, weil das Bild die Architektur trägt statt sie zu
schmücken:

| Begriff | Was es ist |
|---|---|
| **stream / Wasser** | der Prozess selbst — Daten, Arbeit, Ergebnisse, die durch alles hindurchfließen |
| **Bach / Rinnsal** | die wilden, gewachsenen Läufe: die ursprüngliche persönliche Vollinstanz |
| **water pipes** | dasselbe Wasser, gezähmt und modularisiert — Module und Bundles |
| **waterfall** | die deklarative Quelle: Baukasten, Rezepte, Kataloge |
| **ocean** | das Vollsystem; Endpunkt der Linie Bach → Rinnsal → Ozean |
| **open-ocean** | der Teil, der allen gehört: das kostenlose Community-Vollsystem |

Die leitende Regel ist ein Erhaltungssatz: **Extraktion ändert das Bett, nie das Wasser.** Umbau
muss die Funktion erhalten — „gleiche Wassermenge" heißt Funktionsparität. Auch das ist keine
Zierde, sondern die Messlatte, die dieses Repository für seine Freigabe überspringen muss.

Das System wird nicht neben der ursprünglichen Instanz neu geschrieben, und die Ursprungsinstanz
wird nicht umgebaut. Es entsteht durch fortgesetzte **Extraktion**: Module fließen heraus, und die
Ursprungsinstanz baut sie anschließend selbst wieder ein und ersetzt damit ihre eigenen Innereien.
Sie wird kein Museumsstück. Sie lebt weiter als begradigter Fluss — nicht mehr ganz natürlich,
aber ans Wasser angeschlossen und weiter versorgt.

## Was tatsächlich hier liegt

```
architecture/
  open-ocean.skeleton.v1.json   which recipes the system intends to consume, pinned by hash
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
                                 one ring; dry-run by default, --apply for real writes, --rollback
PRIVATE.txt                     the publication gate, committed on purpose
```

Das Gerüst referenziert 13 Bundles in zwei Ringen — den Funktionskern und die Breite darum herum.
Es **referenziert** sie: Kein Manifest wird hierher kopiert. Kopien würden in dem Moment
auseinanderlaufen, in dem das Rezept-Repository weitergeht, und ließen dieses Repository weiter
erscheinen, als es ist.

## Status

**Dieses Repository:**

| | |
|---|---|
| Architektur-Gerüst | vorhanden, 13 Bundles referenziert |
| BACH-Extraktionsbasis | vorhanden — 114 quellseitige Namen; historische 113er Runtime-Messlatte bleibt erhalten; erneut geprüft am 2026-08-18 (106 Handler-Klassen, +1 gegenüber der 2026-08-08-Basis — zurückverfolgt auf eine hostgebundene Duplikatdatei in BACH, `upgrade-WORKSTATION-LG.py` neben `upgrade.py`; hier NICHT behoben, BACH liegt außerhalb des Änderungsumfangs dieses Repositories). `registered_names` unverändert bei 114. |
| K9-1 Daten-/Checkpoint-Gate | zwei Träger-Fixtures grün; Adapter und BACH-Äquivalenz bleiben offen |
| Installer | **Resolve, Verify, SHA-gepinnte Fetch/Place-Schritte, sandboxiertes Skill-Activate, Aktivierungsprotokollierung und zielvalidiertes Rollback sind für den derzeit unterstützten Komponentenpfad implementiert; dieser pinnbare Ring-1-Ausschnitt ist auf einem Fremdrechner integrationsgeprüft.** Am 2026-08-20 verifizierte ein einzelner `--apply`-Aufruf auf einem Mac Studio alle 5 Ring-1-Bundles, holte `WikiStub-Seed` am katalogisierten SHA `3476ba2…12458af4` und aktivierte alle 9 Ring-1-Skills in einer ausdrücklichen Sandbox. Das einzige Aktivierungsprotokoll mit 10 Einträgen rollte danach das Modul und alle Skills zurück; der Snapshot des produktiven Mac-Pfads `~/.claude/skills` blieb vor, nach Apply und nach Rollback identisch. Die portable Suite umfasst nun 100 Tests, einschließlich Real-Git-Transaktionsabdeckung sowie Fail-Closed-Regressionen für die Wiedergabe eines Protokolls gegen ein anderes Ziel, für einen Löschvorgang, der sein Ziel zurücklässt, und für Katalog-IDs, deren Groß-/Kleinschreibung vom Bundle-Ref abweicht. Das ist kein Vollsystem-Installationsclaim: Zwei Ring-1-Git-Module sind weiterhin ungepinnt, zehn Modulreferenzen sind lokale Verzeichnisquellen statt Fetch-Ziele und eine Katalogreferenz trägt weiterhin die bekannte Namensdrift `memory-hooker`/`memoryhooker`. Siehe [gestuften Bauplan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Eigene Laufzeit | **nicht verfügbar** — jeder Kandidat ist privat oder nur deklariert |
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

## Freigabebedingungen

Dieses Repository trägt ein bedingtes Publikations-Gate (`PRIVATE.txt`, bewusst committet, damit
das Gate dort sichtbar ist, wo Sichtbarkeit geschaltet wird). Es öffnet sich, wenn alle vier
Bedingungen nachweislich erfüllt sind:

1. **Grüne Bestandteile** — jedes referenzierte Bundle ist grün: jede seiner Komponenten
   öffentlich und geprüft. **Erfüllt zum 2026-08-18** für den 13-Bundle-Umfang dieses
   Repositories — siehe Ampel-Tabelle oben.
2. **Schleusen-Test bestanden** — die Gesamtleitung trägt: eine frische Installation aus diesen
   Rezepten erreicht auf einer Maschine, die nicht der Entwicklungsrechner ist, einen
   arbeitsfähigen Zustand. **Nicht erfüllt; die Installer-Naht selbst ist jetzt aber auf einem
   Fremdrechner integrationsgeprüft.** Ein Mac-Studio-Durchlauf am 2026-08-20 führte Resolve,
   Verify, einen echten SHA-gepinnten Fetch/Place und alle neun Ring-1-Skill-Aktivierungen in einem
   `--apply`-Aufruf aus und entfernte danach alle zehn Schreibvorgänge über dasselbe
   Aktivierungsprotokoll. Damit ist der zuvor unerprobte kombinierte Mechanismus geschlossen, nicht
   die Freigabebedingung: Ziel war eine ausdrückliche Sandbox, nur ein Ring-1-Git-Modul besitzt
   derzeit einen sicheren Katalog-Pin, und der Lauf erzeugte kein vollständiges arbeitsfähiges
   Ocean-System aus allen erforderlichen Bestandteilen. Belege und verbleibende Breite stehen in
   Stage 2 des `architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md`.
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
ersetzt. Von den vier Bedingungen sind 1 und 4 erledigt. Bedingung 2 hat jetzt eine verifizierte
transaktionale Installer-Naht, aber noch keine vollständige frische Installation eines
arbeitsfähigen Systems; Bedingung 3 hat weiterhin keine BACH-Funktionsparität. Der
Sandbox-Integrationsbeleg stuft keine der beiden Bedingungen hoch.

## Lizenz

MIT, am 2026-08-08 vom Eigentümer gewählt und als [`LICENSE`](LICENSE) committet. Damit ist der
Lizenzteil von Freigabebedingung 4 erledigt; deren Rechts- und Privacy-Teil bleibt offen, bis die
Publikationsprüfung gelaufen ist.
