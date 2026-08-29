<img src="assets/banner.png" width="100%" alt="open-ocean Banner">

# open-ocean

**Free the ocean.**

Das kostenlose Community-Vollsystem des ellmos-Ökosystems.

*[English](README.md)*

> **Privater Aufbau, und bewusst früh.** Dieses Repository existiert, bevor das System existiert —
> damit die Architektur einen Ort hat, während sie entschieden wird. Es öffnet sich, wenn das
> Wasser im Ozean ankommt; siehe *[Freigabebedingungen](#freigabebedingungen)*.

---

## Zuerst lesen: dieses Repository ist eine Baustelle

**Das veröffentlichte öffentliche Vollsystem liegt hier noch nicht.** Die private OCEAN-Full-Dev-
Komposition ist auf dem Entwicklungsrechner jetzt lauffähig: Sie kann einen deklarierten
`runtime.host` planen, installieren, starten, prüfen, mit einem Benutzer versehen, stoppen und neu
starten. Das ist der erste nutzbare OCEAN-Produktabschnitt, aber kein Claim auf BACH-Parität oder
Veröffentlichungsreife. Die geprüfte Komposition weist weiterhin zehn fehlende Pflichtmodule aus
und markiert sich deshalb selbst mit `full_composition: false`.

OCEAN konsumiert die Rezepte aus ihrem kanonischen Repository, statt sie hierher zu kopieren. Die
Transaktionsschicht löst auf, prüft, holt, platziert, aktiviert und rollt zurück; die
Lebenszyklusschicht betreibt die ausgewählte Laufzeit in einer ausdrücklichen lokalen Sandbox. Der
aktuelle Full-Dev-Host ist das private `ellmos-core`, über seine Fähigkeit ausgewählt und nicht als
künftige öffentliche OCEAN-Laufzeit fest verdrahtet.

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
  darin deklarierten `bundle_refs[]`. Manifest und private Rezepte bleiben in ihren kanonischen
  Ablagen; nichts davon wird in dieses Repository kopiert.

```text
python tools/ocean_dev.py --bundles-root <recipe-projection> \
  --system-manifest <ellmos-development-fullsystem/system.v1.json>
```

Ohne `--apply` ist dies ein rein lesender Dry-run. Ein Systemmanifest lässt sich nicht mit einem
nummerierten Ring kombinieren; Teilarbeit wird adaptiv als eigener Bundle-Zyklus ausgewählt und
nicht durch stilles Kürzen der deklarierten Full-Dev-Komposition.

Der Produktlebenszyklus liegt im Wurzelverzeichnis:

```text
python ocean.py plan <composition arguments>
python ocean.py up <composition arguments> --apply
python ocean.py status --workspace <local-sandbox>
python ocean.py user add --workspace <local-sandbox> --username <name> --email <address>
python ocean.py down --workspace <local-sandbox>
```

`python ocean.py --help` und die Hilfe des jeweiligen Unterbefehls zeigen alle Argumente. Das
Passwort wird verdeckt abgefragt und nie als Prozessargument übergeben; lokale Automatisierung kann
`--password-stdin` verwenden.

## Status

**Dieses Repository:**

| | |
|---|---|
| Architektur-Gerüst | vorhanden, 13 Bundles referenziert |
| BACH-Extraktionsbasis | vorhanden — 114 quellseitige Namen; historische 113er Runtime-Messlatte bleibt erhalten; erneut geprüft am 2026-08-18 (106 Handler-Klassen, +1 gegenüber der 2026-08-08-Basis — zurückverfolgt auf eine hostgebundene Duplikatdatei in BACH, `upgrade-WORKSTATION-LG.py` neben `upgrade.py`; hier NICHT behoben, BACH liegt außerhalb des Änderungsumfangs dieses Repositories). `registered_names` unverändert bei 114. |
| K9-1 Daten-/Checkpoint-Gate | zwei Träger-Fixtures grün; Adapter und BACH-Äquivalenz bleiben offen |
| Installer und Lebenszyklus | **Resolve, Verify, SHA-gepinnte Fetch/Place-Schritte, sandboxiertes Skill-Activate, Aktivierungsprotokollierung, zielvalidiertes Rollback, Runtime-Start/Status/Stopp/Neustart und delegierte Benutzeranlage sind implementiert.** Ein echter Windows-Full-Dev-Lauf am 2026-08-29 bestätigte alle 29 gepinnten Bundles, löste 51 Module und 62 Skills auf, installierte die Skills in eine ausdrückliche Sandbox und erreichte eine gesunde Web-Anmeldeoberfläche. Start → Stopp → Neustart wurde unabhängig geprüft. Die Suite umfasst jetzt 114 grüne Tests. 26 Modulreferenzen bleiben unaufgelöst; zehn davon sind im aktuellen Full-Dev-Manifest Pflicht. Siehe [gestuften Bauplan](architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md). |
| Laufzeit | **für das private Full Dev verfügbar** über den deklarierten `runtime.host`-Anbieter `ellmos-core`; eine öffentliche OCEAN-Laufzeit wird noch nicht ausgeliefert, und der private Anbieter ist keine öffentliche Abhängigkeit |
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
   arbeitsfähigen Zustand. **Noch nicht erfüllt.** Die Installer-Naht bleibt durch den Mac-Studio-
   Lauf vom 2026-08-20 auf einem Fremdrechner integrationsgeprüft. Am 2026-08-29 absolvierte der
   Entwicklungsrechner zusätzlich einen echten Full-Dev-Zyklus aus Plan/Apply/Start/Status/Stopp/
   Neustart und erreichte eine gesunde Web-Anmeldeoberfläche. Das bringt OCEAN substanziell voran,
   ist aber weder ein frischer Fremdrechner-Vollsystembeleg noch eine vollständige Komposition:
   Zehn Pflichtmodule fehlen weiterhin. Die genauen Belege und die verbleibende Breite stehen im
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
