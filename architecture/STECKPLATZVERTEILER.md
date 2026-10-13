# Hybrid-Steckplatzverteiler: erste Strecke

*[English](RESOURCE-ARBITER.md)*

Status: Offline-Kern mit injizierten Adapterverträgen. Live-BACH-IN, produktive Ressourcenzulassung, neue Queue, Taskmigration und Release sind nicht abgenommen. Der Nutzer hat die Hybrid-Architektur am 13.10.2026 gewählt; Konfiguration und Rollout sind eigene Schritte.

## Verträge und Zuständigkeit

Ein **ResourceSocket / Steckplatz** ist ein großer RAM-/CPU-Verbraucher. Ein **SlotRequest / Slot** ist dessen Nutzer oder Job. Die **Fackel** umfasst genau einen aktiven Steckplatz mit einem aktiven Slot je Host. Kleine Jobs und Betriebssystemprozesse liegen außerhalb dieser ersten Strecke. Eine feste Großverbraucherschwelle wird nicht aus Schätzungen abgeleitet.

`ocean_resources.HostLocalArbiter` besitzt den Zulassungszustand. Alle beteiligten Clients eines Hosts müssen dieselbe konfigurierte Hostidentität und denselben lokalen Zustandsordner verwenden. `HostWriterAuthority` verlangt einen ausdrücklich gewählten, bestehenden absoluten Ordner, weist OneDrive/UNC und verlinkte Pfade ab und verwendet eine nicht blockierende OS-Sperre. Das ist eine kooperative Schreibergrenze, keine Sicherheits-Sandbox gegen Prozesse, die den Ordner austauschen oder eine andere Konfiguration wählen können. Das Journal ist von BACHs Polarstern-Taskschreiber-Lease (`resource_lease.py` / Migration 053) getrennt. Diese Lease und BACH-Datenbanken werden nicht verändert.

Generation und neue Writer-Sitzungsidentität binden Rückmeldungen an die Zuteilung. Eine aktive Reservierung wird mit Prüfsumme und fsync im gesperrten Inode festgehalten. Ein ungeklärtes oder beschädigtes Journal verweigert nach einem Neustart einen neuen Arbiter. Automatische Wiederherstellung oder Freigabe durch Ablauf ist nicht implementiert. Anfragen, Ereignisse und Checkpointverweise liegen während der Sitzung im Arbeitsspeicher; die Anwendung besitzt die dauerhafte Job-/Checkpointablage. Produktive Wiederherstellung bleibt ein Gate.

`CapacityReadback` braucht den richtigen Host, frische endliche monotone Zeit, eine strikt neuere Sequenz, positive verfügbare RAM-/CPU-Mengen nach **geprüfter Systemreserve** und eine bestätigte Speicherdruckprüfung. Unbekannte Werte führen zu HOLD. Nur ausdrücklich genannte **Fixture**-Profile werden zugelassen. Reale OS-/Modellprofile samt Autorisierung sind noch nicht implementiert.

## Übergabe und Kompatibilität

1. Eine unveränderliche Anfrage einstellen; identische Wiederholungen eines Idempotenzschlüssels liefern die ursprüngliche Anfrage. Abweichende Dubletten führen zu HOLD.
2. Zulassung reserviert die einzige Fackel. Vor dem Start wird eine stabile Ausführungsidentität gebunden; ein Startfehler erhält die Reservierung.
3. Eine Rückgabeanforderung verhindert neue Inferenz-Turns und Heartbeatverlängerung. Sie beendet keinen bereits laufenden Inferenzaufruf.
4. Die Anwendung liefert einen kanonischen, generationsgebundenen Checkpoint mit höchstens 1 MiB. Ungültige Checkpoints erlauben keinen Stopp.
5. Der injizierte Executor beendet seine eigene Arbeit. Ein getrenntes Readback bestätigt die passende beendete Ausführung und null Prozessresidenz.
6. Ein neueres Hostkapazitäts-Readback muss nach dem Exit liegen, bevor die Fackel frei wird. Unzureichende Kapazität kann die *nächste* Anfrage weiterhin sperren.
7. Der alte Job darf erneut warten und vom geprüften Anwendungscheckpoint fortfahren. SIGSTOP beweist keine RAM-Freigabe.

Fairness erlaubt bei wartender Hintergrundarbeit höchstens drei interaktive Zuteilungen hintereinander und bedient danach einen Hintergrundslot; innerhalb beider Klassen gelten Priorität und FIFO. Das begrenzt die Reihenfolge, **keine Chatlatenz in Sekunden**: Der aktive Executor muss seinen sicheren Checkpoint erreichen. Zeitparameter sind konfigurierbar; der Kern installiert keinen Pollingdienst. Ein Nutzer-Override wählt eine wartende Anfrage mit Begründung und begrenztem Ablauf und wird protokolliert. Authentifizierung/Oberfläche und automatische Leerlaufsteuerung bleiben eigene Gates.

`BACHFacade` besitzt eine unveränderliche injizierte Executormap und importiert keinen BACH-Livebetrieb. `request_from_task` erhält `required_model` und `assigned_slot`, prüft einen exakten `HybridPlannerPointer` und claimt oder verändert keinen echten Task. `ComputeExecutorAdapter` stellt Start-/Checkpoint-/Stopp-/Readback-Callbacks bereit und entdeckt keine Queue. Bestehende Jobs werden nicht kopiert.

`ModelSocketInferenceAdapter` erhält die fünf bisherigen `model_target`-Felder (`socket_id`, `binding_id`, `agent_id`, `backend`, `model`) und die asynchrone `HostInferenceGate.turn`-API. Er prüft die Ressourcen-Zuteilung vor und innerhalb des nativen Gates. Er ersetzt das Gate nicht und lädt oder entlädt kein Modell. Modellresidenz, Wiederverwendung desselben Modells und native BACH-Verkabelung sind noch nicht abgenommene Liveadapter.

## API, Manifest und CLI

```text
python -m ocean_resources                  # JSON-Manifest; nur lesend
python -m ocean_resources manifest         # dasselbe Manifest
python -m ocean_resources fixture-demo     # synthetischer Compute → Chat → Resume; nur eigener temporärer Zustand
python -m pytest tests/test_resource_arbiter.py tests/test_resource_cli.py -q
```

Das mitgelieferte `ocean_resources/manifest.json` beschreibt API, Kompatibilität, Zuständigkeit und Restgates. Eine native GUI-Erweiterung liegt an dieser Schnittstelle noch nicht vor. Der bestehende Task-Union-Vertrag bleibt `union-schema-specified-fixtures-green-no-live-cutover`; kein Paritätsclaim wird hochgestuft. Die Pipelinezählung bleibt offen.

Tests verwenden auch ein echtes eigenes 1-MiB-Dummy-Kind mit dauerhaftem Checkpoint-Readback, bestätigtem Exit und fortgesetztem Fortschritt. Die Kapazitätswerte dieses Szenarios sind synthetisch. Sie belegen kein RAM-Budget in Modellgröße, keine systemweite Freispeicherdifferenz und keine produktive Buddha-Chatabnahme.

## Restgates

Unabhängiger Review; profilierte und zugelassene reale Adapter; gemessene Kapazität/Systemreserve; anwendungssicherer Checkpoint und bestätigtes Modellentladen/Prozessbaumende; BACH-IN und Routingfixtures; Neustart-Reconciliation; authentifizierter Override und Leerlauf-/Deadline-Steuerung; gegebenenfalls native GUI; gepinnte Rezept-/Consumer-Projektion; kontrollierte Liveabnahme. Dienstinstallation, produktive Queuewrites, Modellaufrufe, Release und Cutover sind nicht enthalten.

Primärquellen der OS-Sperren: [Python fcntl](https://docs.python.org/3/library/fcntl.html#fcntl.flock), [Python msvcrt](https://docs.python.org/3/library/msvcrt.html#msvcrt.locking). Diese dokumentieren die Sperrprimitive, keine unabhängige Host-Sicherheitsgarantie.
