# Gemeinsame GUI: Ocean-Verbrauchervertrag

Stand: 2026-10-08. Implementierter Kandidat, keine Produktionsinstallation und
kein Laufzeit-, Browser- oder Geräteabnahmebeleg. Open Ocean bleibt Version 0.1.2.

## Release und Herkunft

Die gemeinsame Astro-GUI wird aus einem veröffentlichten, sauberen Quellencommit
als ZIP konsumiert. Der Verbraucher benötigt den vollständigen 40-stelligen
Quellencommit und den SHA-256 des vollständigen Archivs. Das ZIP enthält
`dist/`, `dist/dist-manifest.json` und `LICENSE`. Das Manifest verwendet
`ellmos-system-gui.dist.v1`, `source_commit` und `files` als Zuordnung von
Dateinamen relativ zu `dist/` zu SHA-256. Es enthält sich nicht selbst.

`tools/gui_release.py` prüft beide Pins, alle Datei-Hashes, die vollständige
Dateimenge, Lizenzdatei, Pfade, Größenbegrenzungen und verbotene Links. API- und
Loginrouten dürfen keine statischen Dateien überdecken. `tools/fetch_place.py`
platziert nach Prüfung ausschließlich nach `<workspace>/modules/ellmos-system-gui`.
Vorhandene oder fremde Verzeichnisse werden nicht überschrieben. Neben den
Release-Dateien werden der lokale Beleg `.ocean-gui-release.json` und das
Originalarchiv `.ocean-gui-release.zip` gespeichert. Beim Readback wird das
Originalarchiv erneut gegen die externen Pins geprüft: ein nachträglich zusammen
mit dem Manifest veränderter Beleg reicht nicht als Herkunftsnachweis.

Die Platzierung verwendet die vorhandene Modulidentität und das vorhandene
Activation-Log. Das bestehende Rollback entfernt genau diese Platzierung.
Es gibt keinen zweiten Fetch-, Journal- oder Rollbackkern.

Der Installer übergibt `--expected-components-json` aus dem tatsächlich gehashten
`plan.components`. Der Ocean-Kern vergleicht nach dem frischen Resolve/Verify und
vor jeder Platzierung oder Aktivierung die vollständige expandierte Refmenge
einschließlich deklarierter Dependencies und des GUI-Releases auf exakte Gleichheit.
Ein erfolgreicher Vorplan ersetzt diese Prüfung beim Apply nicht. Alle Dependencies
müssen explizit im genehmigten Plan stehen; eine Grant-Erweiterung findet nicht statt.
Beim Rollback dürfen nur Logeinträge innerhalb derselben genehmigten Menge entfernt
werden. Standalone-Ocean-Aufrufe ohne Installer-Scope behalten ihren bisherigen
expliziten CLI-Vertrag.

## Installation und Provider

`tools/ocean_dev.py` und `ocean.py plan/up` akzeptieren zusammen:

```text
--gui-archive <release.zip>
--gui-source-commit <vollständiger Commit>
--gui-archive-sha256 <vollständiger SHA-256>
```

Ohne `--apply` ist die Transaktion lesend. Für den Installer werden diese Werte
in den gehashten `ocean`-Block aufgenommen; `module:ellmos-system-gui` muss bereits
durch System Explorer aufgelöst und explizit ausgewählt sein. Der ergänzte
`ellmos-installer.OpenOceanAdapter` delegiert Plan und Installation an denselben
Ocean-Kern. Änderungen benötigen weiterhin explizites Approval und den extern
signierten Capability Grant. Die REST-Brücke bietet keine Apply-Route.

Die Lifecycle-Projektion verwendet nach erneutem Release-Readback den bestehenden
ellmos-core-Laufzeitanbieter und den Ocean-ASGI-Verbraucher. `/control/` liefert
die gemeinsame Startseite; deklarierte Seiten und Assets werden aus dem geprüften
Speicherabbild bedient. Die alte Jinja-Oberfläche bleibt der bestehende Fallback,
wenn keine gemeinsame GUI ausgewählt ist. API-, Session- und Loginrouten bleiben
beim Provider. Der Bridge-Router wird innerhalb dessen Sessionmiddleware montiert.

`ocean.gui-bridge.json` enthält lokale, private Hostkonfiguration. Der Lifecycle
schreibt feste Planpfade; REST-Requests können keine Dateipfade, Befehle, Quellen,
Grants oder Truststores auswählen. Status und Plan geben nur Strukturfelder aus.

## Capability-Vertrag v1

`GET /api/gui/capabilities` antwortet mit `schema=ellmos.gui.capabilities.v1`:

| Feld | Semantik |
| --- | --- |
| `system` | Anbieter-ID und Adapterversion |
| `observed_at` | UTC-Zeitpunkt der Adapterauskunft |
| `gui` | `installed` nur nach vollständigem Hashreadback; Commit und Archivhash |
| `modules` | Objekt je Modul-ID: `adapter_registered`, `available`, `runtime_verified`, `reason_code` |
| `module_sources` | Liste tatsächlicher Herkunftsprüfungen: ID, Version, Commit, `verified`, Prüfumfang |
| `pages` | ID, Pfad, `configured` oder `unavailable`, `requires`, `missing`, `todo` |
| `endpoints` | Methode, Pfad, `kind`, `available`, Provideridentität, Auth, Prüfstatus, Grund |

`kind` unterscheidet `read`, `write` und `action`. `auth` ist `none`,
`provider-session` oder `device-token` (BACH). Ocean verwendet `provider-session`.
Die Capability-Auskunft benötigt eine Providersession; alle Installer- und
Registryrouten zusätzlich die vorhandene Adminrolle. Es werden keine neuen
Geräteschlüssel oder Hostbindungen erzeugt.

`available=true` bedeutet, dass ein Adapter implementiert und konfiguriert ist.
Es ist kein Livenessbeleg. `verification_scope=adapter` und
`runtime_verified=false` machen diese Grenze maschinenlesbar. Eine vorhandene
HTML-Seite ist kein nativer Anbieter. Derzeit ist nur die Übersicht als
`configured` ausgewiesen, wenn der GUI-Release geprüft ist; die übrigen 19 Seiten
haben fehlende Widgetadapter. Native Slots/Tasks und Schreibaktionen bleiben
ausdrücklich nicht verfügbar; ihre Adapterrouten antworten mit HTTP 503.

| Endpunkt | Implementierung |
| --- | --- |
| `GET /api/installer/detect` | Lesende Adapter-/Providerkonfiguration, kein Apply |
| `GET /api/installer/plan` | Bestehender `plan_from_paths`, bei fehlenden festen Quellen HTTP 503 |
| `GET /api/installer/status` | Bestehender `status_for_workspace`, öffentliche Feldliste |
| `GET /api/policies` | Erster begrenzter Moduladapter: native Registry-Metadaten |
| `GET /api/governance/policy-registry` | Dieselbe native Suche mit `scope`, `query`, `consumer`, `kind` |
| `GET /api/decisions` | Dieselbe Registry, ausschließlich Entscheidungsmetadaten |
| `GET /api/governance/effective-policy` | Noch kein freigegebener Ocean-Auflösungsadapter: HTTP 503 |

## Begrenzter Modultransfer: policy-registry

Nur ein bereits durch den Ocean-Kern exakt gebundener und installierter Anbieter
mit `catalog_id=policy-registry` darf verwendet werden. Commit, saubere Quelle,
Repository, Modulmanifest und deklarierte Fähigkeiten prüft der vorhandene
`verify_bound_provider`. Der Python-Import muss aus derselben geprüften Quelle
stammen. Der Leseadapter ruft ausschließlich `PolicyRegistry.load()` oder `search()` auf.
Vor der Importausführung werden Top-Level-Spec, direkt am gebundenen Paketpfad
gesuchter Untermodul-Spec und sämtliche bereits geladenen Paketcaches geprüft.
Ein fremdes Elternpaket wird daher nicht zur Herkunftsermittlung ausgeführt.
Pro Lesezugriff sind lesbare, unveränderte Registry-Vor-/Nachaufnahmen erforderlich;
ein verschwundener oder unlesbarer Speicher ergibt HTTP 503 und keine leere Erfolgsliste.
Er gibt Summen nach Art/Status sowie öffentliche Metadaten und deklarierte Hashes aus.
Der Prüfzustand beschreibt Registry-Metadatenvalidierung, keine Quellenhashprüfung.
Private Titel,
Quellenpfade, Regeltexte, Entscheidungen und referenzierte Quelldateien werden
nicht ausgegeben oder geöffnet. Registrierung, Änderungen und Delegation bleiben
außerhalb dieser Brücke. Ohne explizite lokale `--policy-registry` und exakte
Komponentenbindung bleibt der Anbieter nicht verfügbar.

## Offene Abnahme

Ein sauber gebauter und veröffentlichter GUI-Release mit unveränderlichen Pins,
Installer-Discovery/Audit, externem Approval/Grant und eigener Sandbox ist der
nächste Integrationsschritt. Diese Arbeit veröffentlicht oder installiert nichts
produktiv. Laufzeit, Browser, Mac/Windows, Login und Geräte müssen anschließend
separat abgenommen werden. Die 19 Seiten ohne native Widgetadapter bleiben offen.
