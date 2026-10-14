# Geprüfte Lastprofile

*[English](PIPELINE-PROFILES.md)*

Hostkapazität und Lastbedarf sind getrennte Nachweise. `ReviewedProfileGate`
akzeptiert ein ausdrücklich konfiguriertes CPU-Prozessprofil nur, wenn gepinnte
Policy und Messdatei, nativer Host, Plattform, Architektur, Zeitfenster,
Befehlsfingerprint und genaue Steckplatzzuteilung übereinstimmen. Standardmäßig
bleibt die Zulassung geschlossen. Es werden weder Dateien gesucht oder freigegeben
noch Dienste installiert oder Queues verändert.

Windows verwendet die native Architektur aus der Betriebssystemantwort
[IsWow64Process2](https://learn.microsoft.com/en-us/windows/win32/api/wow64apiset/nf-wow64apiset-iswow64process2),
auch bei emulierten Prozessen. Fehlende API, fehlgeschlagener Aufruf und unbekannte
Architektur bleiben gesperrt. Für dieses Freigabefeld gibt es keinen WMI- oder
Umgebungsvariablen-Fallback. Andere Plattformen verwenden ihre nichtleere
gemeldete Architektur. Zwei leere Beobachtungen gelten niemals als Übereinstimmung.

## Freigabe und Messbeleg

Die vertrauenswürdige Hostkonfiguration wählt `ProfileSource(profile_path,
profile_sha256, evidence_path)`. Die vollständigen Policybytes müssen zum
konfigurierten SHA-256 passen; die Policy pinnt sämtliche Messbytes. Beide Dateien
müssen lokal, vorhanden und unverknüpft außerhalb von OneDrive/UNC liegen.
Jede Prüfung liest sie erneut. Doppelte JSON-Schlüssel, nichtendliche Werte,
boolesche Zahlen, zusätzliche Felder, geänderte Bytes und Übergröße werden
abgewiesen. Ein JSON-Feld reviewed=true erteilt keine Freigabe. Die Konfiguration
ist eine privilegierte Operatorentscheidung und kommt nicht aus einem Job oder
Modell. Sie isoliert nicht vor beliebigem Python-Code im selben Prozess.

Die Policy verwendet Schema `ocean-reviewed-workload-profile.v1` mit exakt:
kind=cpu-owned-process, profile_id, socket_id, host_id, platform, architecture,
workload_sha256, den positiven Ganzzahlen ram_bytes, cpu_units, ram_margin_bytes,
evidence_sha256, approved_by, approved_at und expires_at. Die letzten beiden
Werte sind UTC-Epochsekunden; monotone Grantfristen bleiben eine eigene Zeitdomäne.

Der Messbeleg `ocean-workload-measurement.v1` verlangt scope=cpu-process-tree,
method=sampled-rss-and-cumulative-cpu-v1, passende Host-/Plattform-/Architektur-
und Befehlsidentität, peak_rss_bytes, peak_cpu_units, eine geprüfte ganzzahlige
CPU-Nebenläufigkeitsgrenze cpu_concurrency_units, sample_count,
sample_interval_seconds, UTC-Zeiten started_at/finished_at sowie unabhängig
bestätigten Checkpoint und Exit. unmeasured_external_residency muss false sein.
Diese Bestätigungen dürfen nicht erfunden werden; der Operator prüft tatsächliche
Last, Eingangsdaten und Messumfang.

Die RAM-Zuteilung deckt gemessenen RSS und eine ausdrücklich positive RAM-Marge.
CPU-Zuteilung deckt die geprüfte maximale Nebenläufigkeit des Befehls und die
gemessenen CPU-Werte. **Gemittelte Auslastung beweist keine Obergrenze für Lastspitzen.**
Messfenster, Stichprobenzahl und Abstand müssen zusammenpassen. Die Messung endet
vor der Freigabe, bleibt innerhalb des ausdrücklich konfigurierten Höchstalters
und geht dem Profilablauf voraus.

Diskrete RSS-Stichproben können kurzlebige oder umgehängte Kinder, kurze Spitzen,
GPU- und externe Daemonbelegung verpassen; gemeinsame Speicherseiten können
mehrfach zählen. Das Profil ist ein geprüfter Bedarfsrahmen, keine vom System
erzwungene Grenze und kein mathematischer Worst-Case-Beweis. Modell-/GPU-/Daemon-
Scopes bleiben deshalb hier geschlossen. Sie benötigen eigene Residenz-,
Eingabe-/Kontext- und Unloadnachweise. Dateigrößen sind keine RAM-Bedarfsprofile.

## Befehl und Lifecycle

ProcessCommand.fingerprint bindet unveränderliche Argumente, Arbeitsordner,
deklarierte Quellpins und ausdrückliche Umgebung. Die Prüfung muss alle
maßgeblichen Eingabe-/Abhängigkeitspins und Nebenläufigkeitsgrenzen einschließen.
OCEAN_RESOURCE_RUN_DIR ist eine gesonderte dynamische Protokollvariable und kann
nicht überschrieben werden. Der ResourceSocket verwendet denselben
workload_sha256 und genau den geprüften RAM-/CPU-Rahmen.

```python
from ocean_resources import ProfileSource, ReviewedProfileGate

source = ProfileSource(local_policy, operator_configured_policy_sha256, local_evidence)
gate = ReviewedProfileGate((source,), max_age_seconds=86400)
```

Der vorhandene HostLocalArbiter erhält profile_gate=gate ohne Fixturenamen. Er
prüft vor der Vergabe; die Fassade prüft Adapterart und Fingerprint, der
OwnedProcessExecutor nach der Quellenprüfung nochmals vor Aktivierung des
Programms. Seine optionale Methode measure_usage(grant, execution_identity)
beobachtet nur den bereits eigenen lebenden Prozessbaum und begrenzte
Prozesszähler. Sie übernimmt, signalisiert oder genehmigt keinen Prozess.
psutil kommt aus der vorhandenen optionalen resources-Abhängigkeit.

Ablauf oder Dateiersetzung verhindert neue Turns und Heartbeats. Checkpoint,
Stop, Exitmessung und verifizierte Rückgabe bleiben möglich. Das vorhandene
Neustartjournal bleibt bis zur eigenen Abnahme gesperrt; eine Profilfreigabe
räumt es nicht auf.

Der erste geprüfte Executorpfad verlangt ausdrücklich
`ProcessCommand(..., source_mode="frozen-python")`: den aktuell vertrauten
Python-Interpreter und genau ein gepinntes Anwendungsskript mit höchstens 8192
Bytes sowie ausdrückliche Anwendungsargumente. Seine geprüften Bytes werden vor
dem Kindstart in ein isoliertes `-I -S -c`-Programm übernommen. Der Skriptpfad
wird zum Ausführen nicht erneut geöffnet. POSIX führt die Bytes im bereits
abgesicherten isolierten Bootstrap aus; Windows übergibt sie dem suspendierten
Interpreter. Direkt vor Aktivierung werden die tatsächlichen Quellpins erneut
geprüft und die Kapazität neu gemessen. Auch eine spätere Pfadersetzung tauscht
die eingefrorenen Codebytes nicht aus. Der Fingerprint bindet source_mode.
Herkömmliche Pfadstarts bleiben bis zu einem eigens geprüften Artefaktadapter
auf ausdrückliche Fixture-Zulassung begrenzt. Dies ist kein allgemeiner Snapshot
mehrerer Dateien. Isolierte Imports, Laufzeitdateizugriffe, sämtliche wesentlichen
Eingaben und Nebenläufigkeit müssen zum Operatorreview gehören. Installierte
Python-Laufzeit, Standardbibliothek und Betriebssystem sind vertraute Hostbasis;
bösartige Hoständerungen mit denselben Rechten sind nicht Teil dieser
Konsistenzgarantie. `-I/-S` bilden keine Sandbox. Der Referenztest zertifiziert
keine produktive Pipelinefamilie. Messzahlen liegen zwischen 2 und 10.000.000;
die Intervallrechnung muss endlich bleiben. Ungültige Zahlen liefern HOLD statt
eines Tracebacks.

## Lesender CLI-Zugang

```sh
python -m ocean_resources profiles --profile /absolut/lokal/profile.json \
  --profile-sha256 CONFIGURED_SHA256 --evidence /absolut/lokal/evidence.json \
  --profile-max-age-seconds 86400
```

Unter Windows eine Zeile verwenden. VALIDATED bestätigt die momentane Prüfung
der ausdrücklich vorgelegten Dateien; start_authorized bleibt false. Ungültige
Eingaben liefern HOLD und Exit 2. Der Befehl genehmigt oder speichert keine
Allowlist. Das Beispielalter ist keine universelle Policy. Native Kapazität und
Systemreserven, Claims, Budget, Hostautorität, Checkpoint und Publikationsregeln
müssen weiterhin gesondert passen.
