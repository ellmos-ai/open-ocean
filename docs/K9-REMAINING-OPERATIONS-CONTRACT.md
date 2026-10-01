# K9 – Vergleich der sechs offenen Operationen

Dieser Sourceclaim stellt einen ausführbaren Beobachtungsrunner bereit. Er ersetzt keine Engine und erteilt keine Runtime-, Host-, Release- oder Paritätsabnahme. Das vollständige Ziel bleibt bei 87 Fällen, 28 Bundles und 50 ursprünglichen historischen Anforderungen; das Paritätsregister bleibt 3/9.

## Quellen und Messung

Vier unveränderte Arme: historischer Native-BACH @e619345, heutiger Native-BACH @d5ca8a2f, dessen ausdrücklich ausgewählte Shared-Schnittstelle mit Ocean @7127a0f5 und direkter Ocean @7127a0f5. Carrier @7648a20 bleibt unverändert. Der feste JSON-Vertrag bindet sämtliche geladenen Sourceabhängigkeiten einschließlich Schema/Core/Carrier. Ein explizites Quellmanifest liefert nur deren absolute Orte; veränderte Pins, Dateien und Links werden verweigert.

Der Runner erzeugt ausschließlich synthetische Fixtures in einem frischen eigenen Arbeitsverzeichnis. Die synthetischen DB-Zeiten sind ausdrücklich 2026-01-01 00:00:00; Dateisystemzeiten werden ausschließlich während der Fixturevorbereitung auf 2000-01-01 UTC gebunden. Gleiche Anfangsinventare und DB-Bilder aller vier Arme werden direkt verglichen. Nach Produktbeginn werden Zeiten und Wirkungen unverändert gemessen. Inventar und logischer DB-Fingerprint beginnen vor dem ersten Produktimport, Konstruktor und Aufruf. Historische mkdir-/Preview-/Erstkopieeffekte werden als tatsächliche Unterschiede erhalten. Die ausgeführte ursprüngliche Handler-/Konstruktorlogik erhält ausdrücklich gebundene Fixturepfade, Node-ID und Zustandsorte. Eine konfigurierte bach_paths-Namespace und ein beobachtender Konstruktorwrapper binden diese Eingaben; sie sind keine echte Defaults-, App-, Startup- oder Hostkonfigurationsabnahme. Native-/Carrier-Uhr bleiben ihre echten Source-Systemuhren; der Adapter erhält die im Receipt genannte UTC-Uhr.

Nur eigene Fixturedateien dürfen geschrieben oder als SQLite geöffnet werden. Die sourcegebundene Native-Readiness darf ihre erwartete Schemaform in :memory: aufbauen. Prozess- und Netzwerkstarts werden nach der Messgrenze verweigert. Ein permanenter Prozessguard erfordert einen neuen Prozess pro Fall. No-op bedeutet gleiches vollständiges Inventar inklusive Metadaten, kein allgemeines Verbot eines mkdir(exist_ok=True)-Syscalls.

## Sechs Operationen

| Operation | Zu erhalten und zu unterscheiden |
|---|---|
| backup | Quelle und Secrets erhalten; Snapshot redigiert; Preview ohne Publikation. Teilwirkung nach Publikation ist kein Rollback. |
| status | Fehlende Verzeichnisse nicht präparieren; korrupt, unbekannt und fehlend getrennt. Ein alter erfolgreicher Textstatus ist keine verifizierte Snapshotabnahme. |
| enable | Gewählter Marker, Preview und Apply; keine Job-/Dienstaktivierung. |
| disable | Gewählter Marker, fehlend idempotent, fremder Inhalt ausdrücklich verweigert. |
| cleanup | Expliziter local-node/all-nodes-Umfang; UTC-Manifestzeit und alte mtime-Policy getrennt; Retention/Preview/Fehler/Nichtzielnode erhalten. |
| init | Historische Erstkopie, native Schema0-Readiness und Shared-Validierung getrennt; keine Migration oder stille Umstempelung. |

minimal7 ist eine begrenzte synthetische positive Shared-Fixture. Sie ersetzt weder den legitimen Native-Schema0-Vertrag noch dessen FTS-Struktur. native0 benutzt die genaue sourcegebundene Schemaform mit user_version=0 und bleibt ein offener positiver Shared-backup/init-Rest. native7-fts isoliert den weiteren FTS-/Hidden-/Virtual-Rest bei positivem Versionswert. Solche Refusals sind Daten, keine verdeckte Paritätsannahme.

## Ausführung und Pflichtgate

OCEAN_K9_SOURCE_MANIFEST zeigt auf eine vollständige, separat aus den genannten unveränderlichen Gitobjekten gesicherte Sourceclosure. OCEAN_REQUIRE_K9_REMAINING=1 macht fehlende Quellen zu einem Fehler. Ohne Pflichtgate werden nicht verfügbare Integrationsfälle ausdrücklich übersprungen und tragen keine Abnahme. Für jeden Abnahmebeleg muss das Gate gesetzt sein, alle Sourcefälle ausgeführt werden und die rohe Ergebnisklassifikation samt Nichtwirkungen gelesen werden. Ein späterer Pflicht-CI-Job braucht seinen eigenen Workflowclaim; dieser vierteilige Sourceclaim ändert keine Workflow- oder Registerdatei.

Der CLI-Aufruf benötigt --manifest, --workdir, --receipt, --mode und --operation. Preview ist Standard; --apply ist eine ausdrücklich gewählte reine Fixtureaktion. Setup-/Sourcefehler liefern RC2; RC0 bedeutet nur, dass ein tatsächlicher Ausgang beobachtet wurde. Ein beobachteter Refusal wird dadurch nicht zum erfolgreichen Produktfall.

## English contract

The runner observes the same six operations through four immutable source arms and records filesystem/database state before product imports and constructors. It reuses the original handler, adapter and carrier code, with explicitly declared fixture input bindings. It does not claim real startup/default configuration or whole-host authority. Missing sources fail under the mandatory gate. Observed refusals, historical side effects, schema0/FTS gaps and post-publication partial effects remain visible. No result promotes the 3/9 parity register or narrows the original 87-case/28-bundle/50-requirement goal.
