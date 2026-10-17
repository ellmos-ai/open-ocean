# Belege für den Wiederanlauf der nativen Pipeline, v1

Dieser Vertrag umfasst die gemeinsame Ocean-Ressourcenpipeline für Compute, Builds, Medien, Dienste und modellgestützte Arbeit. Er gilt nicht nur für Übersetzungsaufträge.

## Dauerhafte Belege während eines eigenen Prozesslaufs

Das Writer-Journal bleibt das einzige begrenzte, checksummengesicherte Reservierungsjournal. Solange eine Freigabe aktiv ist, enthält es nun zwei optionale Referenzen:

- `execution_evidence` bindet Freigabe und Ausführungsidentität an den Fingerabdruck des gepinnten Befehls, das hostlokale Laufverzeichnis, die PID des Eigentümerprozesses, die PID des Kindes, optionale Prozessstart- und Bootzeiten sowie die Art der Prozessbegrenzung.
- `checkpoint_evidence` bindet dieselbe Ausführung an den Hash der angenommenen Checkpoint-Datei und den Payload-Hash. Der Checkpoint-Payload bleibt im vom Anwendungsprozess verwalteten Laufverzeichnis; das Journal kopiert oder veröffentlicht ihn nicht.

Bevor Anwendungscode laufen kann, werden das zugewiesene Kind und sein geschlossener Anwendungsschalter im Journal festgehalten und mit `fsync` gesichert. Nach erfolgreicher abschließender Quellen- und Kapazitätsprüfung wechselt das Journal zu `gate_state=may-open` und wird erneut gesichert, bevor das Freigabebyte gesendet wird. Scheitert eine der Journal-Schreiboperationen, wird das noch gesperrte Kind bereinigt und die Ressourcenfreigabe bleibt gehalten.

Nach der Anwendungsvalidierung wird der Inhalt der angenommenen Checkpoint-Datei geschrieben und mit `fsync` gesichert, dann wird die Datei an ihren endgültigen Ort umbenannt. Danach werden Datei- und Payload-Hashes protokolliert, bevor der Stopp angefordert wird. Der Stopp liest das checksummengesicherte Writer-Journal erneut und verlangt genau diese Bindung. Scheitert das Schreiben oder Sichern des Journals, wird der Stopp verhindert und die Reservierung bleibt bestehen. Das Writer-Journal nimmt keine Einträge über 64 KiB an.

## Verhalten und Grenzen beim Neustart

Die Haltbarkeitsaussage gilt für einen Absturz des Worker- oder Eigentümerprozesses, solange Host und Dateisystem weiterlaufen. Sie umfasst keinen Stromausfall, Kernelabsturz oder Speicher-Rollback: Der Inhalt der Checkpoint-Datei wird vor dem Umbenennen mit `fsync` gesichert, aber das Elternverzeichnis danach nicht. Diese Einträge dienen der Diagnose und als Eingabe für spätere Recovery, sie beweisen jedoch nicht, dass ein Prozess aktuell beendet ist. PID, Prozessgruppe, Laufverzeichnis, Startzeit oder Kill-on-close-Einstellung reichen allein nicht aus, um eine Freigabe aufzulösen. Ein neuer Writer hält eine ungelöste Reservierung weiterhin fest. Er übernimmt, signalisiert, setzt oder requeued den alten Prozess nicht. Eine unabhängige Prüfung des Betriebssystem-Prozessbaums und eine erneute Validierung des ursprünglichen Task-Claims bleiben erforderlich.

`gate_state=closed` belegt, dass der Anwendungsschalter nicht dauerhaft als möglicherweise geöffnet markiert wurde. `gate_state=may-open` ist bewusst konservativ: Das Freigabebyte könnte bereits gesendet worden sein oder auch nicht. Keiner dieser Zustände entscheidet über die Freigabe beim Neustart.

Der Checkpoint-Verweis bleibt nur so lange dauerhaft verfügbar, wie die ungelöste Freigabe im Journal steht. Das getrennte Crashfenster nach bestätigter Freigabe, wenn das Journal bereits gelöscht wurde, aber Queue und Checkpoint noch nicht vollständig aus ihrem In-Memory-Zustand übernommen wurden, ist weiterhin offen. Dauerhafte Task-Wiedervorlage, Checkpoint-Erhalt nach abgeschlossenen Grants und automatischer Resume sind hier nicht implementiert.

Externe Modell- und GPU-Residenz liegt weiterhin außerhalb des qualifizierten CPU-Prozesspfads. Diese Änderung aktiviert keine produktive Pipeline, migriert keine Queues und ändert keine Task-Zuständigkeit.
