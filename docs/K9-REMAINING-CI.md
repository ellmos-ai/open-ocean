# K9 – permanenter CI-Nachweis der sechs offenen Operationen

Der Job `K9 remaining operation evidence` führt die bestehende, unabhängig abgenommene 146er-Beobachtungssuite auf Windows, Linux und macOS unter Python 3.12 aus. Der bisherige allgemeine CI-Workflow bleibt erhalten. Dieses Delta erweitert die Ausführung; es verändert weder die vier Sourcearme noch Engine, Adapter, Vergleichsfixtures oder Paritätsregister.

## Unveränderliche Quellen

Vier separate, vollständig ausgecheckte Quellen sind ausdrücklich auf die Commitpins des bestehenden Vertrags gebunden: BACH historisch e619345, BACH aktuell d5ca8a2f, Ocean-Adapter 7127a0f5 und Carrier 7648a20. Der Vorbereiter liest den abgelösten HEAD und alle 14 erforderlichen Dateien. Symbolische HEADs, Worktree-Gitdateien, falsche Pins, abweichende Datei-LF-Hashes, Links und Hardlinks werden verweigert. Erst nach vollständiger Prüfung entsteht ein neuer expliziter Source-Manifestpfad. Produktmodule werden bei dieser Vorbereitung nicht ausgeführt.

Die anschließende Suite setzt `OCEAN_REQUIRE_K9_REMAINING=1` und `OCEAN_K9_SOURCE_MANIFEST`. Fehlende Quellen erzeugen Fehler. Der zweite Gateaufruf verlangt mindestens die vorhandenen 146 Fälle, konsistente JUnit-Zählungen und keine Fehler, Fehlschläge oder übersprungenen Fälle. Neue Fälle dürfen hinzukommen. JUnit und die rohen synthetischen Receiptdateien werden je Betriebssystem als GitHub-Artefakt gespeichert.

## Abnahmegrenze

Ein grüner Job bestätigt die vollständige Ausführung dieser Beobachtungsfälle auf seinem jeweiligen Runner. Erfolgreich beobachtete Produktverweigerungen bleiben Verweigerungen; native Schema0-/FTS- und weitere Credential-, Marker-, IO-, Publikations- sowie Cleanup-Produktlücken sind dadurch nicht geschlossen. Das Paritätsregister bleibt 3/9. Der gesamte Auftrag mit 87 Fällen, 28 Bundles und 50 ursprünglichen Anforderungen bleibt unverändert.

Ein angelegter Workflow ist noch kein ausgeführter CI-Beleg. Veröffentlichte Runs und ihre tatsächlichen Ergebnisse müssen nach unabhängig abgenommenem Source-Delta separat nachgelesen werden. Lokale Windows-Evidenz ersetzt keinen Linux-/Mac-Job und keine Host-, Startup-, Dienst-, Konfigurations- oder Liveabnahme. Repository-Branchschutz muss den konkreten Job erst separat als erforderlichen Mergecheck festlegen; diese Sourceänderung beansprucht keine administrativen Regeln.

## English scope

The separate three-platform job requires all four immutable checkouts and validates the complete fourteen-file source closure before writing its manifest. It runs the existing suite with required sources and rejects incomplete, skipped or unsuccessful JUnit evidence. Green observation jobs do not promote operation parity, resolve observed product refusals or authorize deployment.
