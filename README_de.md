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
| BACH-Extraktionsbasis | vorhanden — 114 quellseitige Namen; historische 113er Runtime-Messlatte bleibt erhalten |
| K9-1 Daten-/Checkpoint-Gate | zwei Träger-Fixtures grün; Adapter und BACH-Äquivalenz bleiben offen |
| Installer | **nicht gebaut** — im Grundsatz entschieden, zurückgestellt, jetzt wieder fällig |
| Eigene Laufzeit | **nicht verfügbar** — jeder Kandidat ist privat oder nur deklariert |
| Rezepte | im Rezept-Repository gepflegt, nicht hier |

**Die Ampel** — Freigabebedingung 1 geht grün, wenn jedes referenzierte Bundle grün ist, also jede
seiner Komponenten öffentlich und geprüft:

| | |
|---|---|
| Bundles grün-fähig | **13** — die, die dieses Gerüst referenziert |
| Blockiert durch nicht-öffentliche Komponenten | 17 weitere Bundles |
| Größter Einzelhebel | am 2026-08-08 weitgehend aufgelöst — drei der vier Repositories sind öffentlich; allein `ellmos-core` blockiert noch drei Bundles |

Drei dieser vier wurden am 2026-08-08 durch Entscheidung des Eigentümers öffentlich —
`ellmos-scheduler`, `system-explorer` und `policy-registry`. Damit entfällt die Repo-Sperre für
`system-knowledge` und `personal-ops` auf der Ebene der erforderlichen Komponenten. Das vierte,
`ellmos-core`, bleibt privat: seine eigene `RELEASE_GATE.md` untersagt jede Sichtbarkeitsänderung,
bis die Lizenzwahl und mehrere Sicherheitspunkte geklärt sind — dieses Gate hebt der Eigentümer,
kein Agent. Es blockiert weiterhin `core-discovery`, `prompt-workflow` und `runtime-options`;
`governance-assurance` und `automation-control` hängen an Komponenten, die nie privat waren,
sondern öffentlich schlicht noch nicht existieren. Solange das offen ist, kann dieses Repository
den Umfang, den sein Name verspricht, nicht erreichen — das ist der ehrliche Grund, warum es privat
ist und nicht bloß unfertig.

## Freigabebedingungen

Dieses Repository trägt ein bedingtes Publikations-Gate (`PRIVATE.txt`, bewusst committet, damit
das Gate dort sichtbar ist, wo Sichtbarkeit geschaltet wird). Es öffnet sich, wenn alle vier
Bedingungen nachweislich erfüllt sind:

1. **Grüne Bestandteile** — jedes referenzierte Bundle ist grün: jede seiner Komponenten
   öffentlich und geprüft.
2. **Schleusen-Test bestanden** — die Gesamtleitung trägt: eine frische Installation aus diesen
   Rezepten erreicht auf einer Maschine, die nicht der Entwicklungsrechner ist, einen
   arbeitsfähigen Zustand.
3. **Parität für den Release-Umfang** — das System leistet, was es zu decken beansprucht. Ein
   kleinerer installierbarer Kern ist eine Bau-Etappe, kein Release. Der aktuelle Quell-Audit
   erfasst 114 erreichbare Namen und erhält zugleich den historischen 113er Runtime-Snapshot als
   Mindestzusage; siehe [Extraktionsroadmap](architecture/BACH-EXTRAKTIONSROADMAP.md).
4. **Publikationsprüfung bestanden** — Recht, Privacy und Lizenz geprüft, keine Blocker.

Bedingung 2 ist die, nach der dieses Repository benannt ist. Die Schleusen zu öffnen und
zuzusehen, ob das Wasser wirklich ankommt, ist der Test, den keine Menge korrekter Manifeste
ersetzt.

## Lizenz

MIT, am 2026-08-08 vom Eigentümer gewählt und als [`LICENSE`](LICENSE) committet. Damit ist der
Lizenzteil von Freigabebedingung 4 erledigt; deren Rechts- und Privacy-Teil bleibt offen, bis die
Publikationsprüfung gelaufen ist.
