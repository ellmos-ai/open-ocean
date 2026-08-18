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

**Hier liegt noch kein System.** Kein Installer, keine eigene Laufzeit — und bewusst keine Kopien
der Rezepte. Was hier liegt, ist die Architektur dessen, was gebaut wird: welche Rezepte das
System konsumieren soll, wo sie leben und was der Installer werden muss.

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
  open-ocean.skeleton.v1.json   welche Rezepte das System konsumieren soll, per Hash gepinnt
  INSTALLER-TARGET.md           was der Installer werden muss — und was er nicht tun darf
  BACH-EXTRAKTIONSROADMAP.md    Reihenfolge, Paritäts-Gates und Cluster-9-Kernelkarte
  bach-parity-baseline.v1.json  maschinenlesbare Registry- und Cluster-9-Basis
  bach-k9-data-contract.v1.json gepinnter Operations- und Fixture-Vertrag für dbsync/snapshot
  bach-k9-dbsync-adapter.v1.json Spezifikation des dünnen Lebenszyklus-Adapters
  session-checkpoint-capability.v1.json Grenze des korrekten Snapshot-Trägers
tools/
  audit_bach_handlers.py        nebenwirkungsfreier Quell-Audit gegen diese Basis
  check_k9_data_contract.py     statische BACH-Prüfung plus zwei synthetische Träger-Fixtures
PRIVATE.txt                     das Publikations-Gate, bewusst committet
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
| Installer | **nicht gebaut** — im Grundsatz entschieden, zurückgestellt, jetzt wieder fällig |
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
   arbeitsfähigen Zustand. **Nicht erfüllt, und noch nicht versuchbar.** Es gibt nichts zu
   installieren: die Zeilen „nicht gebaut"/„nicht verfügbar" oben sind wörtlich gemeint — weder
   Installer noch Laufzeit existieren in diesem Repository bislang, also gibt es kein Artefakt,
   gegen das ein Schleusen-Test laufen könnte. Kein Mac-Studio-Problem: der vorgesehene
   Fremdrechner wurde am 2026-08-18 als erreichbar und bereit verifiziert (SSH, `~/compute/`,
   `~/.venvs/science` allesamt vorhanden) — der Blocker ist, dass der Installer, nach dem diese
   Bedingung benannt ist, noch nicht gebaut wurde. Ihn zu bauen ist ein eigenes, umfangreiches
   Vorhaben, außerhalb des Rahmens eines einzelnen Tickets.
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
ersetzt. Von den vier Bedingungen sind 1 und 4 erledigt; 2 und 3 warten beide auf dasselbe
fehlende Stück — einen Installer und eine Laufzeit, die es hier noch nicht gibt.

## Lizenz

MIT, am 2026-08-08 vom Eigentümer gewählt und als [`LICENSE`](LICENSE) committet. Damit ist der
Lizenzteil von Freigabebedingung 4 erledigt; deren Rechts- und Privacy-Teil bleibt offen, bis die
Publikationsprüfung gelaufen ist.
