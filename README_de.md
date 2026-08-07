# open-ocean

**Free the ocean.**

Das kostenlose Community-Vollsystem des ellmos-Ökosystems: Rezepte, Bundles und Komposition.

*[English](README.md)*

> **Privater Aufbau.** Dieses Repository entsteht privat und öffnet sich, wenn das Wasser im
> Ozean ankommt. Die Bedingungen dafür stehen geschrieben und sind prüfbar — siehe
> *[Freigabebedingungen](#freigabebedingungen)*.

---

## Zuerst lesen: was v0.x ist und was nicht

**open-ocean v0.x ist eine deklarative Rezept-Schicht für Agenten-CLIs, die Sie ohnehin schon
betreiben. Es ist keine eigenständige Anwendung.**

Dieser Satz ist das Nützlichste auf dieser Seite und steht deshalb vor jeder Werbung. Einen
Installer gibt es noch nicht, und eine eigene Laufzeit gibt es noch nicht: jeder Kandidat dafür
ist entweder privat oder bislang nur deklariert. Was hier liegt, sind **Rezepte** —
maschinenlesbare Manifeste darüber, welche Komponenten eine arbeitsfähige Einheit bilden, welche
Rolle jede füllt, was sie bereitstellt und verbraucht und welche Alternativen abgewogen wurden.
Die Laufzeit bringen Sie mit; das Rezept sagt Ihnen, was hineingehört.

Ein Installer ist geplant und ist genau das, was aus „beschrieben" ein „installiert" macht. Bis
dahin ist dieses Repository Dokumentation, mit der man rechnen kann — keine Software, die man
starten kann.

## Warum ein Rezept überhaupt veröffentlichenswert ist

Ein Bundle-Manifest ist ein **Rezept = Seed + Zutatenliste**.

Die Zutatenliste ist die leichte Hälfte. Jedes Bundle, jeder Stack und jedes System hier löst
sich vollständig in eine flache Liste aus Repositories, Skills und Agentenrollen auf — und jedes
davon ist einzeln öffentlich und auffindbar.

Der **Seed** ist die Hälfte, die sich nicht auflöst: welche Teile zusammengehören, welche Rolle
jedes füllt, welche Alternative unter welchen Kriterien gewählt wurde, in welcher Reihenfolge
gebaut wird. Dieses Wissen lässt sich aus der Zutatenliste nicht rekonstruieren. **Wer alle
Module hat, hat damit noch nicht das System** — und genau deshalb sind die Rezepte das
Interessante an dieser Veröffentlichung und kein Beiwerk.

## Woher der Name kommt

Das Ökosystem benennt seine Ebenen nach Wasser, weil das Bild die Architektur trägt statt sie zu
schmücken:

| Begriff | Was es ist |
|---|---|
| **stream / Wasser** | der Prozess selbst — Daten, Arbeit, Ergebnisse, die durch alles hindurchfließen |
| **Bach / Rinnsal** | die wilden, gewachsenen Läufe: die ursprüngliche persönliche Vollinstanz |
| **water pipes** | dasselbe Wasser, gezähmt und modularisiert — Module und Bundles |
| **ocean** | das Vollsystem; Endpunkt der Linie Bach → Rinnsal → Ozean |
| **open-ocean** | der Teil, der allen gehört: das kostenlose Community-Vollsystem |

Die leitende Regel ist ein Erhaltungssatz: **Extraktion ändert das Bett, nie das Wasser.**
Umbau muss die Funktion erhalten. „Gleiche Wassermenge" heißt Funktionsparität — und ist zugleich
die Messlatte, die dieses Repository für seine Freigabe überspringen muss.

## Was heute darin liegt

13 Bundles in zwei Ringen. Von jedem einzelnen ist jede Komponente heute öffentlich verfügbar,
auch die optionalen — genau das ist das Aufnahmekriterium.

**Ring 1 — der Funktionskern.** Das Minimum, das zusammen ein arbeitsfähiges System ergibt:
Gedächtnis kurz und lang, Zugang zu einem Agenten, Auswahlwissen, Wissensbeschaffung.

| Bundle | Klasse | Säule | Komponenten | Was es trägt |
|---|---|---|---|---|
| `ellmos-working-memory-bundle` | platform | memory | 5 | Sitzungszustand: was erfasst wurde, was offen ist |
| `ellmos-memory-human-context-bundle` | platform | memory | 6 | dauerhaftes Gedächtnis und Nutzermodell |
| `ellmos-agents-bundle` | platform | control | 7 | Zugang zur Laufzeit — der Ersatz für eine eigene |
| `ellmos-coordination-choice-bundle` | choice | control | 2 | Auswahlwissen: der sichtbare Beweis, dass ein Rezept mehr ist als eine Liste |
| `ellmos-knowledge-bundle` | platform | — | 8 | Wissen finden und aufbereiten |

**Ring 2 — Breite ohne Zusatzrisiko.** Ebenso sauber und ab Tag 1 nützlich.

| Bundle | Klasse | Säule | Komponenten |
|---|---|---|---|
| `ellmos-doc-handler-bundle` | domain | domain | 11 |
| `ellmos-media-production-bundle` | domain | — | 7 |
| `ellmos-daily-life-bundle` | domain | uas | 6 |
| `ellmos-voice-media-assist-bundle` | domain | uas | 3 |
| `ellmos-health-assist-bundle` | domain | uas | 2 |
| `ellmos-briefing-bundle` | domain | uas | 1 |
| `ellmos-finance-assist-bundle` | domain | uas | 1 |
| `ellmos-knowledge-search-choice-bundle` | choice | — | 1 |

Zusammen 60 Komponenten-Belegungen. `manifests/bundles.catalog.v1.json` ist das Register.

**Was bewusst fehlt:** Bundles, deren Komponenten noch nicht alle öffentlich sind. Ein Rezept,
dem man die Alternativen wegkürzt, damit es publizierbar wird, verliert genau den Seed, der es
wertvoll macht — solche warten lieber, statt beschnitten zu erscheinen.

## Status: die Ampel

Der Rollout ist inkrementell, kein Big Bang. Ein Bundle geht grün, wenn jede seiner Komponenten
öffentlich und geprüft ist; open-ocean geht grün, wenn alles Referenzierte grün ist.

| | |
|---|---|
| Bundles grün-fähig | **13** |
| Blockiert durch nicht-öffentliche Komponenten | 17 weitere Bundles |
| Größter Einzelhebel | vier private Repositories blockieren zusammen sieben Bundles |

Ob diese vier öffentlich werden, entscheidet der Eigentümer des Ökosystems; kein automatischer
Prozess nimmt das vorweg.

## Freigabebedingungen

Dieses Repository trägt ein bedingtes Publikations-Gate. Es öffnet sich, wenn alle vier
Bedingungen nachweislich erfüllt sind:

1. **Grüne Bestandteile** — jedes referenzierte Bundle ist im Register oben grün.
2. **Schleusen-Test bestanden** — die Gesamtleitung trägt: eine frische Installation aus diesen
   Rezepten erreicht auf einer Maschine, die nicht der Entwicklungsrechner ist, einen
   arbeitsfähigen Zustand.
3. **Parität für den Release-Umfang** — das System leistet, was es zu decken beansprucht.
4. **Publikationsprüfung bestanden** — Recht, Privacy und Lizenz geprüft, keine Blocker.

Das Gate selbst liegt als `PRIVATE.txt` in der lokalen Arbeitskopie und wird bewusst **nicht**
committet: Es ist eine lokale Steuerdatei — ein Bot, der nur das Remote sieht, muss deshalb vor
jeder Sichtbarkeitsänderung in der Arbeitskopie nachsehen.

## Wie diese Dateien hierher kommen

Die Rezepte werden nicht hier gepflegt. Sie werden aus einem privaten Kompositions-Repository
**projiziert**, durch `tools/export_from_source.py`; und was dabei entfernt oder umgeschrieben
wird, steht als Daten in einem Export-Vertrag statt versteckt im Skript:

- Hostnamen, interne Pfade und nicht auflösbare interne Kennungen werden entfernt oder neutralisiert
- Komponenten mit Betriebsdaten einer realen Organisation werden ausgeschlossen — die Quelle
  behält sie, diese Projektion nicht
- das private Quell-Repository wird nirgends benannt

Zwei Eigenschaften machen das Ergebnis prüfbar statt bloß behauptet:

- **Reproduzierbar.** Zweimal gegen denselben Quellstand ausgeführt, erzeugt der zweite Lauf
  keinen Unterschied. `--check` meldet Drift, statt zu schreiben.
- **Verifizierbar.** Jedes Manifest trägt einen `content_hash` über seine exportierte Fassung,
  und `manifests/export-receipt.v1.json` hält fest, aus welchem Quellstand jede Datei stammt. Ein
  Hash, der zum unexportierten Original gehört, ließe eine ehrliche Datei manipuliert aussehen —
  deshalb setzt der Export die Pins neu.

```bash
python tools/export_from_source.py --source <pfad-zur-quelle> --check
```

## Lizenz

Noch nicht entschieden. Sie ist eine der vier Freigabebedingungen und wird geklärt, bevor dieses
Repository sich öffnet.
