# Executor für eigene Prozesse

*[English](PIPELINE-EXECUTOR.md)*

Der allgemeine Hybrid-C-Port kann mit `ocean_resources.process.OwnedProcessExecutor` einen
**neuen ausdrücklich konfigurierten Kindprozess** führen. Er verwendet Oceans bestehende
Prozessgruppenaufsicht unter POSIX und suspendierten Start mit Kill-on-close-Jobobjekten unter
Windows. Er übernimmt keine PID aus Queue-Dateien und beendet keine bestehenden Dienste.
Job, fachliche Regeln, Ein-/Ausgaben und Checkpointbedeutung bleiben bei der jeweiligen Pipeline.

## Grenzen

- Der vorhandene Arbiter muss die Zuteilung besitzen und diese Ausführungsidentität gebunden
  haben. Der Adapter ersetzt keine Autorisierung, Ressourcenprofile, Budgetprüfung oder Taskclaims.
- `ProcessCommand` beschreibt unveränderliche Argumente, absoluten lokalen Arbeitsordner,
  exakte Quellpins einschließlich Programmdatei und eine ausdrückliche Umgebung. Quellhashes
  werden vor dem Start geprüft. Das ist kooperative Herkunftssicherung und keine Sandbox gegen
  andere Prozesse desselben Nutzers, die Dateien austauschen können.
- Der Worker muss das folgende Protokoll unterstützen. Bestehende Jobs ohne Checkpoint bleiben
  ausgeschlossen. Ein anwendungsspezifischer Prüfer muss den tatsächlichen Checkpoint bestätigen.
- Produktive Ressourcenzulassung bleibt im aktuellen Arbiter geschlossen. Eigene kleine Prozesse
  mit Fixture-Kapazität zertifizieren weder Modell-RAM noch freie CPU oder die Systemreserve.
- Prozessausgabe wird nicht ins Terminal kopiert; normale Logs und Ergebnisse gehören zur
  Anwendung. Elternseitiger Lifecycle-Zustand liegt ausschließlich im gewählten lokalen Ordner.
- Die Prozess-/Jobgrenze umfasst kooperierende Kinder. Externe Daemons, Modellserver, entkommene
  Prozesssitzungen und entfernte Worker benötigen eigene Lifecycle-/Residenzadapter.

## Workerprotokoll v1

`OCEAN_RESOURCE_RUN_DIR` zeigt auf einen neuen privaten Ordner je Ausführung. Der Elternprozess
schreibt `start.json` mit Schema `ocean-owned-process.v1`, grant, execution_identity und resume
(null oder vorherige verifizierte Anwendungsdaten). Der Worker bestätigt über `ready.json`
dasselbe Schema, dieselbe Zuteilung und dieselbe Ausführungsidentität.

Bei `checkpoint.request.json` erreicht der Worker einen fachlich sicheren Punkt, sichert seinen
eigenen Zustand dauerhaft und schreibt atomar `checkpoint.json` mit denselben Kennungen,
payload als JSON-Objekt und `quiescent: true`. Danach bleibt er bis zum Stopp untätig.
Fremde Kennungen, unklare Ruhe, fehlendes/ungültiges JSON, doppelte Schlüssel, NaN und zu große
Nachrichten werden abgewiesen. Die Wartezeit ist begrenzt; der Elternprozess prüft den Inhalt,
versiegelt und synchronisiert `accepted.checkpoint.json`. Vor jedem Stopp muss diese Datei
weiterhin zum akzeptierten Checkpoint passen.

Erst danach wird die eigene Prozessgruppe beziehungsweise der eigene Job beendet. Windows
misst ActiveProcesses bis null; POSIX verlangt die leere eigene Prozessgruppe. Null Residenz
im ExitReadback bezieht sich auf diesen beendeten Prozessbaum und beweist keinen global freien
RAM. Vor Freigabe verlangt der Arbiter weiterhin eine neuere unabhängige Kapazitätsmessung.
Die nächste passende Ausführung erhält genau die bestätigten Anwendungsdaten.

Ungültiger oder fehlender Checkpoint lässt laufenden Worker und Reservierung bestehen.
`close()` räumt ausschließlich eigene Prozesse im Notfall auf; es veröffentlicht kein Ergebnis,
gibt den Arbiter nicht frei und erfindet keinen Checkpoint. Scheitert eine Windows-Jobzuweisung,
wird das eigene suspendierte Kind direkt aufgeräumt; allein den leeren Job zu beenden genügt
nicht. Startfehler erhalten die Reservierung bis zur verifizierten Reconciliation.

## Python-Anbindung

```python
from ocean_resources import BACHFacade
from ocean_resources.process import OwnedProcessExecutor, ProcessCommand

# command = ProcessCommand(unveraenderliche_argumente, lokaler_ordner, quellpins, umgebung)
# Arbiter und Profile müssen für die tatsächliche Last gesondert abgenommen sein.
with OwnedProcessExecutor(arbiter, command, lokaler_zustand, checkpoint_pruefer) as executor:
    facade = BACHFacade(arbiter, {socket_id: executor.adapter()})
    # Bestehender Pipelinepointer -> arbiter.submit(...), start_next(), sichere Übergabe/Resume.
```

Der Import installiert keine Dienste, migriert keine Queues und startet weder Publikation,
Modell noch Zeitplan. Produktivanbindung folgt nach nativen Profilen/Adaptern, Neustartprüfung,
Nutzer-Override und fachlicher Abnahme.

## Abnahme

`tests/test_pipeline_process.py` verwendet einen eigenen 1-MiB-Pythonworker und temporäre Daten.
Geprüft werden Checkpoint 7, bestätigtes Ende, ein separater interaktiver Worker und exakter
Resume 14. Mitgestartete eigene Kinder müssen ebenfalls enden. Negative Fälle prüfen geänderte
Quellen, fremde Identität, ungültigen Checkpoint, Timeout, beschädigten akzeptierten Zustand und
fehlerhafte Windows-Jobzuweisung. Das sind echte Prozessprüfungen mit synthetischem Zulassungsbudget,
keine produktive Buddha-/Modellvorführung.
