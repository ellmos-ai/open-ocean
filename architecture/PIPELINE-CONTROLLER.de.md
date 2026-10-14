# Host-Fokussteuerung

*[English](PIPELINE-CONTROLLER.md)*

`HostController` steuert den vorhandenen `HostLocalArbiter` und die `BACHFacade`.
Es entsteht keine zweite dauerhafte Jobqueue. Research/Compute, modellgestützte
Services, Video, Blender und Builds verwenden dasselbe Steckplatz-/Slotprotokoll;
die nativen Executoren verantworten weiterhin ihre Jobs, Eingabegrenzen und
fachlich sicheren Checkpoints.

## Konfiguration und Polling

Zuerst werden vorhandene Hostautorität, Arbiter, Sensor und geprüfte native
Adapter eingerichtet. Der Controller erhält ein unveränderliches Tupel aus
`ControllerClient`-Einträgen. Je Client werden Steckplätze, höchste erlaubte
Priorität und Zulässigkeit interaktiver Anfragen festgelegt. Nur ein Operator
darf die Auswahl übersteuern. Standardmäßig wird ein zufälliges privates Token
erzeugt; es erscheint weder in repr noch im Status oder Audit. Die Anwendung
verteilt es vertraulich. Dieser Ausbau installiert keinen Dienst, erzeugt keine
Credentialdatei und startet weder Netzwerktransport noch Pollingthread. Die
lokale Berechtigung isoliert nicht vor beliebigem Python-Code im selben Prozess.

```python
from ocean_resources import ControllerClient, FocusPolicy, HostController

worker = ControllerClient("compute-worker", frozenset({"compute"}), priority_floor=3)
chat = ControllerClient("chat", frozenset({"local-model"}), allow_interactive=True)
operator = ControllerClient("operator", frozenset({"compute", "local-model"}),
                            operator=True, allow_interactive=True)
controller = HostController(existing_facade, (worker, chat, operator),
                            FocusPolicy(idle_seconds=30, interactive_slice_seconds=120,
                                        background_min_seconds=10))
result = controller.tick(operator.client_id, operator.token)
```

Der bestehende ausdrückliche Hostloop ruft tick häufiger als die Heartbeat-TTL
auf. Das Audit wird standardmäßig im lokalen Writerverzeichnis nach
`<host>.focus-audit.jsonl` geschrieben und mit fsync gesichert. Die Hostautorität
muss weiter gehalten werden. Verknüpfte oder ersetzte Dateien, Schreibfehler und
die Archivierungsschwelle von 16 MiB halten die Aktion an. Ein eingesetzter
Auditcallback muss vertrauenswürdig und kurz sein und darf nicht rückrufen.
Tokens werden nicht protokolliert. Statusabfragen und Heartbeats gelten nicht
als Nutzeraktivität.

## Übergabe, Inaktivität und Fairness

1. submit delegiert an den unveränderlichen idempotenten Requestvertrag des
   Arbiters. Ursprüngliche Planner-/Executorverweise bleiben erhalten.
2. Wartet ein interaktiver oder höher priorisierter Auftrag, fordert tick die
   sichere Rückgabe des Hintergrundgrants an. Ausschließlich die vorhandene
   Fassade prüft Checkpoint, eigenes Stop/Unload, Exit und Speicherfreigabe sowie
   eine neuere unabhängige Kapazitätsmessung.
3. Modellaufrufe werden mit begin_turn und end_turn samt Grant und Turn-ID
   eingerahmt. Eine Rückgabeanforderung verhindert neue Turns; laufende Inferenz
   darf enden. Der native Adapter muss weiterhin den sicheren fachlichen
   Unterbrechungspunkt bestätigen, bevor Speicher freigegeben wird.
4. Ein inaktiver Chat endet ohne erneute Queueaufnahme. Erst echte neue Eingabe
   erhält eine neue native Request-/Idempotenz-ID. Gesprächszustand bleibt bei
   der Anwendung. Auch die begrenzte interaktive Laufzeit fordert Rückgabe an,
   wenn andere Arbeit wartet.
5. Nach der maximalen Chatfolge des Arbiters bekommt der ausgewählte Hintergrund-
   grant eine konfigurierbare Mindestlaufzeit, bevor neuer Chat ihn verdrängt.
   Ein Operator kann die Fokusauswahl übersteuern. Die Fristen begrenzen
   Vergabemöglichkeiten, nicht die Laufzeit eines unbegrenzten Modellaufrufs.

Lifecyclecallbacks laufen außerhalb des Controllermutex. Gleichzeitige Polls
sehen den Übergang und duplizieren weder Checkpoint noch Start. Eine gescheiterte
Übergabe behält Grant und Queueentscheidung für den Wiederholungsversuch. Ein
gescheiterter Start hält die Arbiterreservierung; sie wird nicht aus Status- oder
PID-Dateien übernommen. Ein ungeklärtes Neustartjournal bleibt bis zur
unabhängigen Reconciliation HOLD.

## Nutzer-Override

override verlangt Operatorberechtigung und einen OverrideCommand mit Host,
aktueller Writersitzung, bestehendem wartendem Request, Grund, eindeutiger
Befehls-ID und künftiger Frist innerhalb des Arbiterlimits. Eine exakte
Wiederholung verlängert die Frist nicht und führt einen verbrauchten Befehl
nicht erneut aus. Abweichender Inhalt unter derselben ID wird abgewiesen.
request_id=None nimmt die Auswahlübersteuerung zurück. Die protokollierte
Anweisung verändert nur die Reihenfolge; Lastprofil, physische Reserve, Budget,
Taskclaim, Checkpoint und Publikationsfreigabe gelten weiter.

finish darf nur der zugehörige native Client oder ein Operator ausführen. Auch
dieser Weg muss die Speicherübergabe belegen. Eine laufende Wiederholung kann
nicht von erneuter Queueaufnahme auf Abschluss umgestellt werden. Eine
abgelaufene Heartbeatfrist räumt Speicher nicht von selbst frei.

## Abnahmegrenze

Verhaltenstests prüfen Compute → Chat → Inaktivität → Compute, tatsächliche
Hintergrundzeit trotz Chatdruck, Berechtigungen, Replay, Parallelzugriff,
Rückrufe, Kapazitätsfehler mit Retry und gehaltene Fehlstartreservierungen.
Ein eigener kleiner echter Prozess liefert Checkpoint 7 und Resume 14. Seine
Kapazitäts-/Profilwerte sind Fixtures; das ist keine Großmodell- oder produktive
Buddha-Abnahme. Produktive Lastprofile, native Clients, Transport/GUI,
Neustart-Reconciliation und kontrollierte Umschaltung bleiben weitere Abnahmen.
