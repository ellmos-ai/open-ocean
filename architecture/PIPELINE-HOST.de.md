# Allgemeine Pipelines und Hostressourcen

*[English](PIPELINE-HOST.md)*

Hybrid C führt Planung und Sichtbarkeit in Ocean/BACH und erhält den Ausführungszustand beim
bestehenden Executor. Compute, Repositorypflege, Outreach, Redaktion, Veröffentlichung,
Stores, Übersetzung, Gamedesign, Video und Softwarebuilds verwenden denselben Referenzvertrag.
Der mitgelieferte Katalog ist eine Beispielzuordnung der ursprünglichen Gruppen, kein zweiter
Aufgabenspeicher, installierter Publisher oder Auftrag zur Kontenanlage. Gruppe 4 enthält mehrere
Buildziele; aus der bisherigen Darstellungsfrage 15 Gruppen/16 Zeilen entsteht keine neue Pipeline.

## Bestehender Kern und neue Beobachtung

Der [Steckplatzverteiler](STECKPLATZVERTEILER.md) besitzt einen aktiven Steckplatz und darin einen
Slot je konfiguriertem Host. Er lässt weiterhin nur ausdrückliche Fixture-Profile zu. Ein Katalog
oder JSON-Flag ersetzt weder Publikationsfreigabe, Budget, echtes CPU-Profil, Modell-Lifecycle
noch nativen Taskclaim.

`BACHFacade.request_from_pipeline` und `slot_request` erhalten für jede Pipeline den ursprünglichen
Planungstask, Executorjob und Quellhash. Sie benötigen keine Modellbindung, claimen keine Aufgabe
und kopieren keinen Queueeintrag. Die bestehenden Modellzielfelder, Inferenzgates und
`request_from_task` bleiben kompatibel.

`host` misst den lokalen Rechner ohne Zustandsdateien oder Dienststarts. Windows verwendet
GlobalMemoryStatusEx, macOS vm_stat und den nativen Speicherdruck, Linux MemAvailable. Die Summe
freier, inaktiver und spekulativer Mac-Seiten ist eine Rückgewinnungsschätzung, keine Garantie;
komprimierte Seiten werden nicht nochmals addiert. Windows-/Linux-Druck wird ausdrücklich aus
dem verfügbaren Speicheranteil konservativ eingeschätzt, nicht nativ zertifiziert. CPU-Anzahl
und Lastmittel sind keine autoritative freie CPU-Kapazität. Plattenplatz wird getrennt gemessen.

Messungen tragen UTC-Unixsekunden; monotone Laufzeiten verschiedener Rechner sind nicht
vergleichbar. Unbekannte, alte, zukünftige oder unvollständige Messwerte bleiben HOLD.
Reserven sind ausdrückliche Vorgaben des Aufrufers und kein gemessenes Modellprofil. Der native
Zulassungstakt des bestehenden Kerns bleibt davon getrennt monoton.

`shadow_plan` prüft ausdrücklich übergebene Jobprojektionen, Plattform, Bedarfsschätzung,
RAM-/Plattenreserve und gemeldete Gates. Auch passende Kandidaten haben `start_authorized: false`.
Die aktuelle Fackel bleibt bis zur nativen Anbindung unbekannt; die Beobachtung behauptet keinen
Leerlauf. `route_job` bevorzugt zentral für schwere oder wiederkehrende Arbeit und lokal für kleine
Einzelläufe. Fähigkeiten und Ressourcen gehen vor dieser Präferenz. Ein Fallback ist ein Vorschlag
für den Planer und ändert keinen bereits geclaimten Lauf.

## API und CLI

```text
python -m ocean_resources                 # unverändertes lesendes Manifest
python -m ocean_resources catalog         # mitgelieferter Beispielkatalog
python -m ocean_resources host            # native lesende Messung
python -m ocean_resources shadow --jobs ausdrueckliche-projektion.json \
  --reserve-ram-bytes 4294967296 --reserve-disk-bytes 8589934592
```

Die Beispielreserven sind illustrative Betreiberwerte, keine zertifizierten Vorgaben.
`--catalog eigener-katalog.json` gehört ausschließlich zum Shadow-Befehl. Jobprojektionen sind
begrenzte JSON-Arrays mit genau diesen Feldern: job_id, pipeline_id, host_id, priority, interactive,
size_class, ram_bytes, cpu_units, disk_bytes, gates, planner, task_id, executor_job_id, source_sha256.
Unbekannter Bedarf darf null sein und führt zu HOLD; size_class ist small, large oder unknown.
Gemeldete Gates beweisen keine Autorisierung. Fehlerhaftes JSON, doppelte Schlüssel, unbekannte
Pipelines, doppelte Jobkennungen und ungültige Werte werden abgewiesen. Die CLI scannt keine
Produktivqueues und schreibt keine Aufgaben.

## Reihenfolge der Anbindung

1. Tatsächliche Hosts beobachten; Queue-, Claim- und Publikationszuständigkeit erhalten.
2. Einen echten Executor samt CPU/RAM/Plattenbedarf und Checkpoint-/Exitvertrag profilieren.
3. Bestehenden Planer und Executor über den Pointer und genau einen Hostverteiler verbinden.
4. Compute → Checkpoint/Exit → interaktive Anfrage → Rückgabe → Resume ohne Verlust prüfen.
5. Medien, Builds und Services über denselben Port ergänzen. Übersetzung ist ein Verbraucher.

Diese Änderung verschiebt keine Zeitpläne oder laufenden Jobs. Authentifizierter Nutzer-Override,
produktive Neustart-Reconciliation, zugelassene echte Adapter und native BACH-Dienstanbindung
bleiben ausdrückliche Deployschritte. Modellstarts, Veröffentlichung, Storeeinreichung und
Dienststarts werden daraus nicht abgeleitet.

Die POSIX-Schreiberregression wird mit echtem fork geprüft: Das Schließen des geerbten Handles
im Kind darf die Dateisperre des Elternprozesses nicht lösen. Ein dritter Schreiber bleibt bis
zur normalen Freigabe des Elternprozesses ausgeschlossen.
