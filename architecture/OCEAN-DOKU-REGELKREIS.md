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
| `trigger_planned` | ein Trigger ist fällig oder geplant (Plan, kein Lauf) | routine, interval_days, marker_source, next_due_at |
| `task_created` | eine begrenzte Analyseaufgabe existiert und wurde rückgelesen | task_id, title_sha256, worker_binding, readback_verified, created_at |
| `executed` | ein realer Lauf ist beendet, evtl. fehlgeschlagen | run_id, host, instance, product_version, exit_state, exit_code, started_at, finished_at, result_id, author_id, author_instance |
| `corrected` | beschreibende Doku wurde geändert | files (SHA-256 vorher/nachher), differences, diff_ref |
| `reviewed` | ein unabhängiger Rücklesereview hat jede Differenz beurteilt | reviewer_id, reviewer_instance, verdicts, accepted_at |
| `repaired` | eine Nachmessung zeigt Übereinstimmung von Doku und Realität | repair_success_at, remeasure, regression |

## Regeln

- Eine Kette enthält jeden Zustand höchstens einmal, in dieser Reihenfolge, mit nicht abnehmendem
  `observed_at`. Ein späterer Zustand ersetzt nie den Beleg eines früheren.
- Ein Zustand darf nur erscheinen, wenn alle früheren erscheinen. Das Kettenfeld `unknown` nennt
  genau die Zustände ohne Beleg. Fehlender Beleg ist `unknown`, nie Erfolg.
- Ein Last-Run- oder Dispatchmarker ist nur Trigger-/Dedupmarker. Auch ein Taskstatus wie `done`
  ist kein Beleg. Ausführung braucht `run_id`, `finished_at` und `result_id`.
- `exit_state` `failed` oder `unknown` beendet die Kette bei `executed`. Nur `succeeded` mit
  `exit_code` 0 darf von `corrected` gefolgt werden.
- `reviewer_id` und `reviewer_instance` müssen sich von `author_id` und `author_instance`
  unterscheiden.
- Jede korrigierte Datei trägt zwei verschiedene SHA-256-Werte. Jede Differenz nennt Aussage,
  Quelle, beobachteten Wert, Belegverweis und Geltungsbereich (Host, Instanz, Version, Fläche).
- `repaired` braucht `reviewed`, `remeasure.equal` wahr und `regression` falsch.

Intervalle, Worker-Bindungen, Archivregeln und Quell-/Leserwurzeln sind Konfiguration des
nutzenden Systems. Der Vertrag friert kein Modell, keinen Pfad, keinen Fanout, keine Zeit und
keinen Archivprozentwert ein; der Checker weist solche Werte im Vertragstext zurück.

## Prüfer

```
python tools/check_doc_loop_contract.py            # Vertrag + alle Fixtures
python tools/check_doc_loop_contract.py --chain <kette.json>
```

Positive Fixtures müssen akzeptiert, jede negative Fixture (Marker ohne Lauf, `done` ohne Bericht,
fehlgeschlagener Lauf mit Korrektur, Review aus derselben Instanz, Korrektur ohne Hashes u. a.) mit
den aufgeführten Problemcodes abgelehnt werden. Exitcode 0 heißt: Vertrag und Fixtures stimmen; der
Statusstring lautet `not-live-evidence`.
