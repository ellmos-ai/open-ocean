---
name: doc-reality-loop
version: 0.1.0
type: workflow
category: docs
status: draft
language: de
description: >
  Empirischer Doku-Regelkreis: erfassen, was die Dokumentation behauptet, die tatsächliche Wirkung auf
  Host, Instanz, Version, CLI, API und GUI messen, jede Differenz belegen, beschreibenden Text an die
  Realität angleichen, unabhängig zurücklesen und das Ergebnis in den Zuständen von ocean-doc-loop.v1
  festhalten.
contract: architecture/ocean-doc-loop.v1.json
variants: [help, root, requirements, freshness]
---

# Workflow: doc-reality-loop

Englische Fassung: `SKILL.md` (gleicher Aufbau, gleiche Überschriften).

## Anspruchsgrenze

Dies ist Workflowtext. Er startet nichts, besitzt weder Scheduler noch Task noch Worker und behauptet
nicht, dass irgendein Host ihn derzeit ausführt. Jeder genannte Zustand und jedes Belegfeld ist in
`architecture/ocean-doc-loop.v1.json` definiert und wird von `tools/check_doc_loop_contract.py`
geprüft. Intervalle, Worker-Bindung, Archivrichtlinie sowie Quell- und Leserwurzeln sind Konfiguration
des nutzenden Systems (`interval_ref`, `worker_binding`, `archive_policy`, `source_roots`,
`reader_roots`); dieser Text nennt kein Modell, keinen Pfad, keine Fanout-Zahl, keine Zeitspanne und
keinen Archivprozentsatz, und das nutzende System darf keinen einschleusen.

## Grundsätze

1. **Beschreibende Dokumentation folgt der Realität.** Text, der sagt, was ein System tut, wird auf das
   korrigiert, was es messbar tut. Text, der sagt, was ein System tun soll, ist eine Anforderung; er
   wird nie gelöscht, nur weil sie unerfüllt ist (siehe Schritt 5).
2. **Beweisrang, der höchste gewinnt bei Widerspruch:** gemessene Wirkung auf dem echten Host, der
   Instanz und der Version; dann Code, Schema und Dateisystem; dann geprüfte Dokumentation; dann ältere
   Notizen und Zusammenfassungen. Eine Aussage aus einem niedrigeren Rang bleibt Hypothese, bis ein
   höherer Rang sie bestätigt.
3. **Unbekannt ist ein Ergebnis.** Was nicht messbar ist, wird als `unknown` festgehalten. Ein
   Last-Run-Marker, ein Dispatch-Marker oder ein Taskstatus wie `done` ist nie Beleg für Ausführung
   oder Erfolg.
4. **Generierte Dateien werden neu erzeugt, nicht von Hand bearbeitet.** Ist eine Aussage falsch, weil
   Vorlage, Export oder Generator falsch sind, geht der Befund an den Eigentümer des Generators; die
   generierte Ausgabe wird danach neu erzeugt.
5. **Der Autor nimmt die eigene Arbeit nicht ab.** Das Zurücklesen übernimmt eine andere Identität und
   eine andere Instanz, aus den Dateien und nicht aus dem Bericht des Autors.

## Varianten

Ein Regelkreis, vier Varianten. Sie unterscheiden sich nur darin, was erfasst wird und was als
Realität gilt.

| Variante | Aussagen stammen aus | Realität wird gemessen durch | Typische Leser |
|---|---|---|---|
| `help` | Hilfethemen und ihre Sprachvarianten (eine Themenfamilie, nicht ein Eintrag je Sprache) | die dokumentierten Befehle ausführen, Handler oder API lesen, referenzierte Pfade und Tabellen prüfen | der Help-Handler, Verweise anderer Themen, Tests |
| `root` | Einstiegsdokumente des Repositorys, Vorlagen und ihre generierten Ausgaben | dieselben Messungen gegen die Einstiegspunkte, dazu generierte Dateien neu erzeugen und vergleichen | Paketmetadaten, Verweise, Boot-Dateien, Menschen |
| `requirements` | Anforderungs- und Plandokumente | jede extrahierte Anforderung gegen Code, Schema, API und CLI prüfen | Roadmaps, Tasklisten, Verweise |
| `freshness` | Changelogs und Datums- oder Versionsangaben | behauptete Versionen, Daten und Zahlen mit Repository und laufender Instanz vergleichen | Release-Werkzeuge, Verweise |

## Schritte

Jeder Schritt nennt den Vertragszustand, den er erzeugt, und die exakten Belegfelder aus
`architecture/ocean-doc-loop.v1.json`. Jeder Ketteneintrag trägt zusätzlich sein eigenes
`observed_at` (UTC); jeder Ereigniszeitstempel liegt nicht später als dieses `observed_at` und ist
entlang der Kette geordnet. Ein Schritt darf erst beginnen, wenn die Belege aller früheren Zustände
vorliegen. Beim ersten fehlgeschlagenen Schritt wird gestoppt.

### 0. Auslöser (`trigger_planned`)

`routine`, `interval_ref` (eine Referenz der Form `config:`, `routine:` oder `policy:` plus Kennung,
nie eine Anzahl Tage), `marker_source` (`config`, `state_file` oder `scheduler_receipt`) und
`next_due_at` festhalten, dazu das `observed_at` des Eintrags. Das ist ein Plan, kein Lauf.

### 1. Task (`task_created`)

Genau einen begrenzten Analyse-Task für ein Scope-Element anlegen (eine Hilfethemenfamilie, ein
Root-Dokument, ein Anforderungsdokument, ein Changelog). Den Task aus seiner Quelle zurücklesen und
`task_id`, `title_sha256`, `worker_binding`, `readback_ref`, `readback_sha256` und `created_at`
festhalten; `readback_verified` ist erst nach diesem Zurücklesen wahr. Das `observed_at` des Eintrags
ergänzen. Das Scope-Element stammt aus der Konfiguration oder aus einer Nutzeranfrage.

### 2. Erfassen

Das Dokument vollständig lesen. Jede prüfbare Aussage auflisten: Befehle und Flags, Funktionen, Datei-
und Verzeichnisverweise, Tabellen- und Endpunktnamen, Versionen, Zahlen, Daten, Querverweise. Je
Aussage notieren, wo sie steht und wer sie liest. Leser stammen aus dem Dokumentregister
(`document_id`, `readers[]`); ein Dokument ohne Registereintrag bekommt keine geratenen Leser, seine
Leser werden als `unknown` festgehalten. Aussagen, die einen Wunsch oder Plan ausdrücken, als
Anforderungen markieren und nicht als Behauptung über die Gegenwart.

### 3. Messen (`executed`)

Für jede Behauptung die tatsächliche Wirkung auf dem betreffenden Host und der Instanz messen und
`host`, `instance` und `product_version` festhalten. Die passende Oberfläche nutzen: CLI (Befehl mit
harmlosem Argument ausführen, Exitcode und Ausgabe festhalten), API (Endpunkt aufrufen), GUI (Seite
öffnen), Dateisystem (existiert der Pfad), Schema (existiert Tabelle oder Spalte), Code (existiert
Handler oder Option). Befehl und Ausgabe bleiben als Belegreferenz erhalten. Zerstörende Operationen
werden nicht gemessen; sie werden mit Begründung als `unknown` markiert. Am Laufende `run_id`,
`started_at`, `finished_at`, `result_id`, `exit_state` (`succeeded`, `failed` oder `unknown`),
`exit_code`, `author_id` und `author_instance` festhalten, dazu das `observed_at` des Eintrags.

**Schranke:** Nur `exit_state` `succeeded` zusammen mit `exit_code` 0 darf zu `corrected` weiterführen.
Ein Zustand `failed` oder `unknown` oder jeder andere Exitcode beendet die Kette bei `executed`.

### 4. Differenzen

Für jede Behauptung mit abweichender Messung eine Zeile mit den Vertragsfeldern `statement`, `source`
(Dokument und Stelle), `observed`, `evidence_ref` und `scope` (`host`, `instance`, `version`,
`surface` als `cli`, `api`, `gui` oder `doc`) schreiben. Die Zeile im Bericht klassifizieren (der
Vertrag friert die Klassen nicht ein):

- `better`: die Realität bietet mehr, als der Text sagt. Text anpassen.
- `partial`: teilweise umgesetzt. Text auf den umgesetzten Teil anpassen und den Rest als Anforderung
  mit Task behalten.
- `target-missing`: das dokumentierte Merkmal existiert nicht. Ist es gewünscht, als Anforderung mit
  Task behalten und als noch nicht umgesetzt kennzeichnen; wurde es absichtlich entfernt, aus dem Text
  entfernen.
- `wrong`: ein Pfad, Flag, Name, eine Zahl oder ein Verweis ist schlicht falsch. Korrigieren.
- `unknown`: hier nicht messbar. Text belassen, Grund notieren.

Ist die Ursache unklar, zuerst den Kontext suchen: Roadmap, Taskliste, Logs, Changelog, Memory-Notizen.
Ein geplantes und vergessenes Merkmal und ein absichtlich entferntes brauchen unterschiedliche
Handlungen.

### 5. Korrigieren (`corrected`)

Nur beschreibenden Text ändern, und nur die Aussagen mit bestätigter Differenz. `files` (je mit
`path`, `before_sha256` und `after_sha256`, die sich unterscheiden müssen), die `differences`,
`diff_ref`, `corrected_at`, `archival`, `open_requirements` und das `observed_at` des Eintrags
festhalten. Regeln:

- Sichere, kleine Korrekturen (Pfad, Flag, Zahl, Version) können direkt angewendet werden.
- Größere oder strukturelle Umschreibungen und alles mit unklarer Absicht werden ein Task oder eine
  Frage an den Eigentümer statt einer Vermutung.
- Gewünschte, noch unerfüllte Anforderungen bleiben als Zielzustand erhalten und stehen in
  `open_requirements`, je mit `statement`, `source` und `task_id`.
- **Archivierung nur über das Dokumentregister.** Ein Element darf nur archiviert werden, wenn es einen
  Registereintrag hat (`document_id`, als `item` festgehalten), die `archive_policy` des nutzenden
  Systems es erlaubt (alle Anforderungen erfüllt oder abgelöst) und die folgenden Prüfungen
  festgehalten sind. Ohne belegbaren Registereintrag lautet die Aktion `keep`. `action` (`keep` oder
  `archive`) festhalten und bei `archive` `archived_at` in UTC. Jeder Eintrag in `reader_checks` hat
  genau `ref`, `kind` (`reader` oder `link`), `active` und `checked_at`. Abbildung der `readers[]` des
  Registers (je mit `kind`, `ref`, `active`, `last_checked_at`): ein Leser mit `kind` `link` wird zur
  `link`-Prüfung; ein Leser mit `kind` `boot`, `test`, `tool` oder `human` wird zur `reader`-Prüfung;
  `ref` und `active` werden übernommen, `last_checked_at` wird zu `checked_at`. Zusätzlich die
  versionierten Dateien nach weiteren Verweisen auf das Element durchsuchen und jeden als
  `link`-Prüfung festhalten. Von jeder Art ist mindestens eine Prüfung nötig, keine darf aktiv sein,
  und jede muss jung genug für `archive_policy.reader_audit_not_before` des Registers sein. Jeder
  aktive Leser oder Verweis bedeutet `keep`.
- **`archive` ist der Registerstatus `archived`.** Er braucht zusätzlich einen `replacement_ref` im
  Registereintrag oder einen Evidenzeintrag vom Typ `archival`; fehlt beides, lautet die Aktion `keep`.
- Generierte Dateien: nicht bearbeiten; den Befund für den Eigentümer des Generators festhalten
  (Grundsatz 4).

### 6. Zurücklesen (`reviewed`)

Eine andere Identität und eine andere Instanz lesen die geänderten Dateien und die Differenztabelle,
prüfen jede Differenz selbst erneut und halten `reviewer_id`, `reviewer_instance`, `verdicts` und
`accepted_at` fest (dazu das `observed_at` des Eintrags). Jedes Urteil hat genau `difference_index`
(eindeutig, jede Differenz genau einmal abdeckend) und `verdict` (`confirmed` oder `rejected`). Eine
abgelehnte Differenz geht zurück zu Schritt 5; der Regelkreis geht nicht auf das Wort des Autors weiter.

### 7. Nachmessen (`repaired`)

Das, was der korrigierte Text jetzt behauptet, im selben Geltungsbereich erneut messen. `remeasure`
(`equal`, `measured_at`, `measurement_ref`, `measurement_sha256`, `scope` mit `host`, `instance`,
`version`, `surface`), `repair_success_at` und
`regression` festhalten (dazu das `observed_at` des Eintrags). `repaired` braucht `reviewed`, `equal`
wahr und `regression` falsch. Eine Nachmessung, die eine Regression zeigt, wird als solche gemeldet und
ist kein Erfolg.

## Bericht

Ein Bericht je Lauf, neben den übrigen Laufergebnissen des nutzenden Systems abgelegt, mit diesen Teilen:

1. Scope-Element, Variante, Host, Instanz, Produktversion, Lauf-ID und erreichter Vertragszustand.
2. Differenztabelle (Aussage, Quelle, beobachtet, Belegreferenz, Geltungsbereich, Klassifikation).
3. Geänderte Dateien mit Hashes vorher und nachher sowie die Diff-Referenz.
4. Offene Anforderungen mit Task-IDs; behaltene Elemente mit den Leser- und Verweisprüfungen, die sie
   gehalten haben.
5. Urteile des Zurücklesens und die Nachmessung.
6. `unknown`-Liste: jeder Zustand und jede Aussage ohne Beleg, mit Begründung.

## Was dieser Regelkreis nie tut

- Einen Last-Run-Marker, einen Dispatch-Marker oder einen `done`-Status als Beweis werten.
- Ein Anforderungsdokument so ändern, dass ein unerfüllter Wunsch verschwindet.
- Archivieren, ohne Leser und Verweise zu prüfen.
- Eine generierte Datei von Hand bearbeiten.
- Reparieren, was er nicht messen kann; er hält stattdessen `unknown` fest.
- Modelle, Intervalle, Pfade, Fanout, Zeitspannen oder Archivschwellen festlegen; das ist Konfiguration.
