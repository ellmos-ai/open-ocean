# Gemeinsamer Hosttransport

*[English](PIPELINE-TRANSPORT.md)*

`ocean_resources.service.HostService` verbindet getrennte native Prozesse mit
einem bereits konfigurierten HostController. Der ausdrücklich gestartete lokale
HTTP-Zugang ist keine dauerhafte Jobqueue oder Executorregistrierung. Compute,
Dienste, Medien und Builds verwenden dieselben Steckplatz-/Slot-/Grantverträge;
fachlicher Jobzustand und Publikationsgates bleiben in den nativen Pipelines.

## Eigentum und Start

Die integrierende Hostanwendung erzeugt vorhandenen Writer, nativen Sensor,
geprüfte Lastprofile, feste Executoradapter und Controller. Sie legt anschließend
ausdrücklich `HostService(controller, configured_operator, port=0)` an und führt
serve_forever im eigenen Vordergrund-Dienstlebenszyklus aus. Der Zugang bindet
ausschließlich an 127.0.0.1; Port 0 lässt das Betriebssystem einen Port wählen.
Es werden weder Daemons installiert, launchd/Tasks geändert, Jobs gesucht,
Konfigurationen gescannt noch BACH-Datenbanken geöffnet. Die Hostschleife ruft
den vorhandenen Controller alle ausdrücklich gewählten 0,05 bis 1 Sekunden auf.
Native Lifecycleaufrufe können länger dauern.

stop beendet Annahme und Polling. close wartet auf die eigene Schleife und die
begrenzten Anfragearbeiter. Beide geben keine Fackel frei, entladen kein Modell,
stoppen keinen Executor und löschen keine dauerhafte Reservierung. Der Aufrufer
behält Writer und Executor bis zum nativen Abschluss oder zur ausdrücklichen
Abgleichprüfung. Unbeendete Schleifen oder Anfragen liefern HOLD; dies beweist
keine RAM-Freigabe. Nach einem Absturz gilt das vorhandene Neustartjournal-Gate.
Stop setzt eine Zulassungsschranke für neue Anfragen und Ticks. Bereits zuvor
angenommene Operationen dürfen während des Abwartens abschließen; ein schon
begonnener nativer Vorgang wird durch Transportende nicht zurückgerollt.

## Berechtigungen und Sessionbindung

Jede Anfrage verwendet die vorhandene eingeschränkte Clientkennung und ein
privates Token im Header. Tokens stehen weder in URL, repr, Audit noch HTTP-Log.
HostClient verwendet direkte Loopbackverbindungen ohne Proxyerkennung oder
Weiterleitungen. Die Hostanwendung verteilt Zugangsdaten und Endpunkt privat;
Konfiguration ist privilegiert und kommt nicht aus Jobdaten. Browser-Origin,
falscher Hostheader, doppelte Framing-/Authheader, Chunked-Anfragen, ungültiges
JSON, doppelte Schlüssel und nichtendliche Werte werden abgewiesen. Höchstens
acht Anfragearbeiter, zwei Sekunden Socket-Lesezeit und ein MiB je Nachricht
begrenzen den Transport. Es gibt weder CORS noch öffentlichen Statuszugang.

Jede Nachricht bindet konfigurierten Host und aktuelle Writerautorität. Ein
Writerwechsel verlangt eine ausdrückliche Neukonfiguration des Clients; alte
Clients können die neue Sitzung nicht steuern. Der Controller prüft weiterhin
Steckplatzrechte, Prioritätsgrenzen, interaktive Rechte, Eigentum am Job sowie
Overrideablauf und Replay-Schutz. Ein ausdrücklicher Tick und Overrides verlangen
Operatorrechte; der konfigurierte Hostoperator betreibt das automatische Polling.

POST /v1/focus/{operation} erwartet exakt schema=ocean-host-transport.v1,
host_id, authority_id und payload. Operationen: status, submit, begin_turn,
end_turn, finish, override, tick. Vertragspayloads enthalten die genauen
Dataclassfelder einschließlich optionaler null-Felder. Antworten enthalten
JSON OK/result oder einen bereinigten HOLD. Ein Timeout nach einer schreibenden
Anfrage beweist keinen Fehlschlag: dieselbe native Jobidentität erneut lesen,
bevor wiederholt wird. Unveränderliche Submit-/Overrideidentitäten behalten ihre
vorhandene Wiederholungssemantik.
Eine sichtbare Fackel während TRANSITION ist eine Reservierung und bestätigt
keine Executorbereitschaft. Vor einem Turn auf einen einzigen Statussnapshot
mit RUNNING und der gewünschten Jobidentität warten. Writerwechsel oder
Rückgabe verlangen weiterhin die erneute Prüfung beim eigentlichen Vorgang.

```python
from ocean_resources.client import HostClient

client = HostClient(configured_port, configured_host, current_writer_authority,
                    configured_client_id, privately_delivered_token)
state = client.status()
```

CLI-Konfiguration, GUI-Panel, Produktdienstinstallation, Umschaltung nativer
Queues/Modelle und produktive Familienabnahme sind weitere Integrationsschritte.
Sie müssen dieselbe Autorität nutzen, statt einen zweiten Schiedsrichter zu
erzeugen. Die Tests verwenden echte HTTP-Verbindungen und einen separaten
Pythonclient mit injizierten Fixture-Executoren. Das ist kein Nachweis für den
lebenden Buddha oder die produktive Ressourcenfreigabe.
