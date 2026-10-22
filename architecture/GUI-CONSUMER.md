# Gemeinsame GUI: Ocean-Verbrauchervertrag

Stand: 2026-10-22. Implementierter Kandidat, keine Produktionsinstallation und
kein Laufzeit-, Browser- oder Geräteabnahmebeleg. Open Ocean bleibt Version 0.1.2.

## Release und Herkunft

`architecture/gui-consumer.v1.json` bindet den veröffentlichten
[GUI-Release 0.2.28](https://github.com/ellmos-ai/ellmos-system-gui/releases/tag/v0.2.28)
an Quellencommit `1d6c0f985834f10ae9e5e051205a33b83efaaa54` und Archiv-SHA-256
`5b79f083ed58cdbc59b09a250efa715780e7c8074f45bca93b16682af18072f4`.
Das Originalarchiv enthält 26 HTML-Seiten und 360 im Distmanifest deklarierte
Dateien. Der Pin behält `status=pinned_artifact_only` und `activation_ready=false`:
Archivprüfung, Platzierung, Backendadapter und Geräteabnahme benötigen jeweils
ihren eigenen Beleg. Die vorhandenen Consumer prüfen das veröffentlichte Artefakt;
hier wird keine zweite GUI-Quelle angelegt.

Die gemeinsame Astro-GUI wird aus einem veröffentlichten, sauberen Quellencommit
als ZIP konsumiert. Der Verbraucher benötigt den vollständigen 40-stelligen
Quellencommit und den SHA-256 des vollständigen Archivs. Das ZIP enthält
`dist/`, `dist/dist-manifest.json` und `LICENSE`. Das Manifest verwendet
`ellmos-system-gui.dist.v1`, `source_commit` und `files` als Zuordnung von
Dateinamen relativ zu `dist/` zu SHA-256. Es enthält sich nicht selbst.

`tools/gui_consumer.py` prüft beide Pins, alle Datei-Hashes, die vollständige
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

tools/gui_release.py ist ausschließlich ein Importadapter für den nativen Consumer.
tools/gui_server.py bedient die verifizierten Seiten für den CLI-Verbraucher und
die Lifecycle-Origin-Brücke; es gibt keinen zweiten Archivprüfer oder Static-Server.

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

### Gemeinsame Metadaten im Provider-Origin

Die Lifecycle-Brücke stellt wie der eigenständige GUI-Verbraucher
`GET /api/gui/brand` und `GET /api/gui/backend-origin` bereit. Im Provider-Origin
gelten die vorhandene Providersession, Authentifizierung vor Methodenablehnung
auch für die Slashvarianten und `Cache-Control: no-store`. Branding und
unverifizierter Herkunftsvertrag stammen gemeinsam aus `tools/gui_metadata.py`.
Die Capability-Auskunft beschreibt diese Metadatenrouten als verfügbare Adapter;
`runtime_verified` bleibt `false`.

Die Backend-Herkunft bleibt ausdrücklich `unknown`: Verbindung, Schema, Instanz
und Adapterbindung sind nicht verifiziert; Claimautorität und Cacheaktivität
werden nicht behauptet. Ein erfolgreicher Metadatenabruf, die Providersession
oder eine Loopback-Adresse ersetzt keinen Nachweis des nativen Task-Backends.
Die Bereitstellung dieser Routen ist noch keine Geräte- oder Laufzeitabnahme.

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
`provider-session` oder `device-token` (BACH). Die Lifecycle-Brücke verwendet provider-session; der eigenständige, lesende
Ocean-GUI-Verbraucher stellt ausschließlich die drei GUI-Metadatenrouten öffentlich
bereit (auth=none, public_metadata=true). Seine übrigen API-Routen bleiben 503.
Die Capability-Auskunft benötigt eine Providersession; alle Installer- und
Registryrouten zusätzlich die vorhandene Adminrolle. Es werden keine neuen
Geräteschlüssel oder Hostbindungen erzeugt.

`available=true` bedeutet, dass ein Adapter implementiert und konfiguriert ist.
Es ist kein Livenessbeleg. `verification_scope=adapter` und
`runtime_verified=false` machen diese Grenze maschinenlesbar. Eine vorhandene
HTML-Seite ist kein nativer Anbieter. Der Seitenstatus wird aus dem vorhandenen
Seitenlesemanifest und den tatsächlich gebundenen Moduladaptern ermittelt.
Die 26 HTML-Seiten im Release belegen keine vollständige Adapterabdeckung.
Native Slots/Tasks und Schreibaktionen bleiben
ausdrücklich nicht verfügbar; ihre Adapterrouten antworten mit HTTP 503.

| Endpunkt | Implementierung |
| --- | --- |
| `GET /api/installer/detect` | Lesende Adapter-/Providerkonfiguration, kein Apply |
| `GET /api/installer/plan` | Bestehender `plan_from_paths`, bei fehlenden festen Quellen HTTP 503 |
| `GET /api/installer/status` | Bestehender `status_for_workspace`, öffentliche Feldliste |
| `GET /api/policies` | Erster begrenzter Moduladapter: native Registry-Metadaten |
| `GET /api/governance/policy-registry`, `/decisions`, `/policies` | Dieselbe native Suche im Schema `bach.policy-registry.v1` (nur `privacy: public`, Standardvorgabe); ohne gebundene Registry HTTP 503 `policy_provider_not_configured` |
| `GET /api/decisions` | Dieselbe Registry, ausschließlich Entscheidungsmetadaten |
| `GET /api/governance/effective-policy?scope=` | Auflösung über dieselbe gebundene Registry (`scope` Pflicht), sonst HTTP 503 |
| `GET /api/governance/locks`, `/status` | Nur aus dem in `ocean.gui-bridge.json` (`lock_cache`) gebundenen Host-Lock-Cache; sonst 200 `unavailable` (`lock_cache_missing`/`_stale`/`_invalid`) |
| `GET /api/governance/audit`, `GET /api/usecases` | Keine Quelle in der Komposition: `task_history_unavailable` bzw. HTTP 503 `source-not-in-composition` |

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
separat abgenommen werden. Seiten mit fehlenden nativen Widgetadaptern bleiben
offen, auch wenn ihre HTML-Dateien bereits im Release enthalten sind.
