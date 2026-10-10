# OCEAN-Doku-Regelkreis-Vertrag

`architecture/ocean-doc-loop.v1.json` legt Zustände und Pflichtbelege eines empirischen
Doku-Regelkreises fest. Es ist ein Vertrag mit fixturegeprüftem Schema. Er startet keinen Workflow,
besitzt keinen Scheduler, keine Task und keinen Worker und behauptet nicht, dass ein Host den
Regelkreis derzeit ausführt.

## Der Regelkreis

Aussagen und ihre Leser oder Quellen erfassen, die tatsächliche Wirkung auf Host, Instanz, Version,
CLI, API und GUI prüfen, jede Differenz belegen, die beschreibende Dokumentation an die Realität
anpassen und unabhängig rücklesen. Die vier Varianten sind `help`, `root`, `requirements` und
`freshness`.

## Zustände

| Zustand | Bedeutung | Pflichtbelege |
|---|---|---|
| `trigger_planned` | ein Trigger ist fällig oder geplant (Plan, kein Lauf) | routine, interval_ref (Form `config:`/`routine:`/`policy:` + Kennung), marker_source, next_due_at |
| `task_created` | eine begrenzte Analyseaufgabe existiert und wurde rückgelesen | task_id, title_sha256, worker_binding, readback_verified (wahr), readback_ref, readback_sha256, created_at |
| `executed` | ein realer Lauf ist beendet, evtl. fehlgeschlagen | run_id, host, instance, product_version, exit_state, exit_code, started_at, finished_at, result_id, author_id, author_instance |
| `corrected` | beschreibende Doku wurde geändert | files (SHA-256 vorher/nachher), differences, diff_ref, corrected_at, archival (archived_at in UTC plus Leser- und Linkprüfungen), open_requirements (je mit task_id) |
| `reviewed` | ein unabhängiger Rücklesereview hat jede Differenz beurteilt | reviewer_id, reviewer_instance, verdicts (eines je Differenzindex), accepted_at |
| `repaired` | eine prüfbare Nachmessung zeigt Übereinstimmung von Doku und Realität | repair_success_at, remeasure (equal, measured_at, measurement_ref, measurement_sha256, scope), regression |

## Regeln

- Eine Kette enthält jeden Zustand höchstens einmal, in dieser Reihenfolge, mit nicht abnehmendem
  `observed_at`. Ein späterer Zustand ersetzt nie den Beleg eines früheren.
- Ein Zustand darf nur erscheinen, wenn alle früheren erscheinen. Das Kettenfeld `unknown` nennt
  genau die Zustände ohne Beleg. Fehlender Beleg ist `unknown`, nie Erfolg.
- Ein Last-Run- oder Dispatchmarker ist nur Trigger-/Dedupmarker. Auch ein Taskstatus wie `done`
  ist kein Beleg. Ausführung braucht `run_id`, `finished_at` und `result_id`.
- `task_created` braucht `readback_verified` wahr sowie Rückleseverweis und SHA-256.
- Alle Ereigniszeitstempel haben genau eine Form, `JJJJ-MM-TTTHH:MM:SS[.fff|.ffffff]` gefolgt von `Z`
  oder `±HH:MM` (auf jeder unterstützten Python-Version gleich), und liegen nicht später als der `observed_at` des
  Eintrags und entlang der Kette geordnet: Taskanlage, Laufstart, Laufende, Korrektur,
  Review-Annahme, Messung, Reparatur.
- `exit_state` `failed` oder `unknown` beendet die Kette bei `executed`. Nur `succeeded` mit
  `exit_code` 0 darf von `corrected` gefolgt werden.
- `reviewer_id` und `reviewer_instance` müssen sich von `author_id` und `author_instance`
  unterscheiden. Die Verdicts tragen eindeutige, gültige `difference_index`-Werte, die alle
  Differenzen genau abdecken.
- Jede korrigierte Datei trägt zwei verschiedene SHA-256-Werte. Jede Differenz nennt Aussage,
  Quelle, beobachteten Wert, Belegverweis und Geltungsbereich (Host, Instanz, Version, Fläche).
- Eine Aktion `archive` ist nur gültig mit einem `archived_at`-Zeitstempel in UTC sowie mindestens
  einer Leser- und einer Linkprüfung, von denen keine mehr aktiv ist. Jedes `checked_at` liegt nicht
  vor dem `observed_at` des Eintrags `executed`, nicht nach `archived_at` und nicht nach dem
  `observed_at` des Eintrags `corrected`; Prüfungen beibehaltener Einträge sind gleich geordnet.
  Einträge mit aktiven Lesern bleiben erhalten. Jede offene gewünschte Anforderung bleibt als Soll
  mit `task_id` erhalten.
- `repaired` braucht `reviewed`, einen prüfbaren `remeasure`-Beleg (Verweis, SHA-256, Geltungsbereich,
  geordneter Zeitstempel), `remeasure.equal` wahr und `regression` falsch.
- `trigger_planned` nennt das Intervall nur als Verweis (`interval_ref`) auf die Konfiguration des
  nutzenden Systems, in der Form `^(config|routine|policy):[A-Za-z0-9._/-]+$` (zum Beispiel
  `routine:2035`). Ein rein numerischer Wert, eine Anzahl Tage oder eine Dauer ist kein Verweis;
  ein Vertrag, der diese Form abschwächt, wird abgelehnt.
- Jede Pflichtsammlung und jedes Pflichtobjekt hat seinen genauen Typ (Liste oder Objekt, auch die
  Objekte in Listen). Ein Wert anderen Typs ist ein eigener Fehler und wird nie als leere Liste
  gedeutet oder übersprungen.

Intervalle, Worker-Bindungen, Archivregeln und Quell-/Leserwurzeln sind Konfiguration des
nutzenden Systems. Der Vertrag friert kein Modell, keinen Pfad, keinen Fanout, keine Zeit und
keinen Archivprozentwert ein. Der Prüfer weist solche Werte im Vertragstext zurück (Modellnamen,
Archivprozente, feste Pfade, Fanout-Zahlen, Intervalle wie „every N days“/„alle N Tage“,
Dauern wie „N Tage“ und ISO-8601-Dauern) sowie in `interval_ref`. Außerdem hält er die
Pflichtbelegmengen selbst: ein Vertrag darf Felder ergänzen, ein Vertrag mit entferntem Feld wird
abgelehnt, und ein abgeschwächter Vertrag rettet keine Kette.

## Prüfer

```
python tools/check_doc_loop_contract.py            # Vertrag + alle Fixtures
python tools/check_doc_loop_contract.py --chain <kette.json>
```

Positive Fixtures müssen akzeptiert, jede negative Fixture (je Regel eine: Marker ohne Lauf, `done`
ohne Bericht, nicht verifizierter Rücklesebeleg, fehlgeschlagener Lauf mit Korrektur, ungültige oder
falsch geordnete Zeitstempel, doppelte Review-Indizes, Archivierung mit aktiven Lesern, offene
Anforderung ohne Task, eingefrorenes Intervall, ungemessene Reparatur u. a.) mit den aufgeführten
Problemcodes abgelehnt werden. Exitcode 0 heißt: Vertrag und Fixtures stimmen; der Statusstring
lautet `not-live-evidence`.
