# Ocean als Verbraucher der System GUI

Der Pin in `architecture/gui-consumer.v1.json` bindet das gemeinsame Release v0.2.3 an einen Quellcommit und den SHA-256 des ZIP-Archivs. `python ocean.py gui --archive <release.zip> --json` prüft das ZIP, dessen `dist-manifest.json`, alle Dist-Dateien und die Lizenz rein lesend. Der Befehl installiert nichts. Ein falscher Hash oder ein unsicherer ZIP-Pfad wird abgewiesen.

`python ocean.py gui --archive <release.zip> --serve` stellt das geprüfte Kit ausschließlich auf 127.0.0.1 bereit (Standardport 8811). Für diesen ausdrücklichen lokalen Start ist das optionale Paket `uvicorn` erforderlich; es wird nicht automatisch installiert. Statische Antworten kommen nur aus Dateien, die das geprüfte Dist-Manifest nennt. Jede Datei wird beim Abruf erneut gegen ihren Hash geprüft. Das Backend liefert `/api/gui/brand`, `/api/gui/backend-origin` und `/api/gui/capabilities`. Die Marke ist Ocean; ein Backend ohne gebundenen Ocean-Adapter bleibt `mode=unknown`. Ungebundene Fach-APIs antworten mit 503 und `ocean_api_adapter_unbound`; es gibt weder eine BACH-Datenbank noch erfundene Ocean-Daten.

Ein Archiv belegt keine Installation. `--dist-root` zusammen mit `--receipt` ermöglicht einen rein lesenden Abgleich eines vorhandenen Installationsbelegs (`ellmos.open-ocean.gui-install-receipt.v1`) und aller lokalen Dist-Dateien mit dem geprüften Archiv. Ohne beide Angaben ist `kit.installed=false`; mit abweichenden Hashes ebenso. Dieser Patch erzeugt keinen Installationsbeleg und führt keinen Installationsschritt aus. Ein späterer Installer muss den Beleg nach einer autorisierten, atomaren Installation schreiben. Der Beleg enthält `schema`, `kit_id`, `version`, `source_commit`, `archive_sha256`, `manifest_sha256` und `file_count`.

Die Fähigkeitenantwort hat `schema_version=1`, `kit`, `brand`, `modules` und `observed_at`. Für das statische Kit ist nur `ellmos-system-gui` als geprüfte Oberfläche eingetragen. Eine Ocean-Fachfunktion erscheint erst nach einer registrierten Route und einer tatsächlichen Providerprobe. Fehlende Adapter bleiben `unavailable`; eine aufgelöste Bundle-Referenz oder ein Dateiname gelten nicht als laufende Funktion.

Offene Integration: Geräteauthentisierung und Berechtigung der Fach-APIs, genaue Ocean-Modulrouten, Laufzeitproben pro Modul, Installationsschritt mit CapabilityGrant und ApprovalReceipt. Bis dahin dient der Serve-Befehl der lokalen Ansicht und einem nachprüfbaren Integrationspunkt, nicht einer vollständigen Ocean-Oberfläche.

## Gemeinsame Installer- und Laufzeitintegration

Der Pin ist auf das tatsächliche GUI-Artefakt 0.2.3 aktualisiert. Ein Archivnachweis
bleibt von einer Installation und einer Geräte-/Browserabnahme getrennt.
tools/gui_consumer.py ist der gemeinsame Prüfpfad für Inspektion, Platzierung und
Readback. tools/gui_server.py bedient ein geprüftes Speicherabbild; Änderungen
an der Archivdatei nach der Prüfung ersetzen dieses nicht.

Der additive Vertrag ellmos.gui.capabilities.v1 erhält kit, brand und das
modules-Objekt. Öffentliche GUI-Metadaten bedeuten keinen konfigurierten nativen
Backendanbieter. Details zur Session-Brücke, externen Installer-Approval-Kette,
exakten Komponentenmenge und dem begrenzten Registry-Leseadapter stehen in
[architecture/GUI-CONSUMER.md](../architecture/GUI-CONSUMER.md).
