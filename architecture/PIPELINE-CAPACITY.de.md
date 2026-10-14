# Native Hostkapazität und Systemreserve

*[English](PIPELINE-CAPACITY.md)*

`ocean_resources.capacity.NativeCapacitySensor` bedient den vorhandenen
`CapacityReadback`-Port mit echten Hostmessungen. Messung, Ressourcenprofil,
Taskclaim, Modellaufruf und Publikationsrecht sind getrennte Nachweise.
Die standardmäßig geschlossene Profilzulassung des Arbiters bleibt bestehen.

Der optionale Zusatz `resources` benötigt `psutil>=5.9.6,<8`. Manifest, Katalog,
Hostbeobachtung und Fixturebefehle importieren psutil nicht. Zur Laufzeit werden
weder Abhängigkeiten installiert noch Dienste gestartet.

## CPU und Reserven

Zwei kumulative Messungen je logischer CPU mit einem ausdrücklich festgelegten
Abstand von 0,1–1 Sekunde bestimmen beobachtete Leerlaufanteile. Jeder Zähler muss
endlich, nicht negativ und monoton sein; Topologie und CPU-Zuordnung müssen
übereinstimmen. Linux-Gastzähler sind bereits in user/nice enthalten und zählen
nicht doppelt. Wartezeit auf Ein-/Ausgaben und andere Nicht-Leerlaufzähler gelten
konservativ als beschäftigt. Überlappende Interruptzähler können die freie
Kapazität unterschätzen, aber keinen zusätzlichen Leerlauf erzeugen.

Es zählen nur tatsächlich zugeordnete CPUs. Nach Abzug der positiven CPU-Reserve
wird die Summe der gemessenen Leerlaufanteile abgerundet. Windows-Konfigurationen
mit mehr als 64 logischen CPUs bleiben bis zur Prüfung ihrer Prozessorgruppenbudgets
HOLD. macOS verwendet die sichtbaren Host-CPUs. Unter Linux werden Zähler gemessen;
die effektiven cgroup-Grenzen für RAM und CPU sind durch diesen Adapter noch nicht
abgenommen. Deshalb bleibt dort reserve_verified immer false.

RAM und Disk werden vor und nach dem CPU-Intervall geprüft. Vom niedrigeren
beobachteten RAM-Wert wird die ausdrückliche RAM-Reserve abgezogen, mindestens
bleiben null Bytes. Beide Druckmessungen müssen normal sein, beide Diskmessungen
die Diskreserve erhalten. Der älteste monotone Zeitstempel bleibt maßgeblich:
Eine langsame Folgemessung macht alte Eingangswerte nicht wieder frisch.
Fehlende, widersprüchliche, rückläufige oder veraltete Messungen ergeben HOLD.

Das ist eine konservative Momentaufnahme, keine vom Betriebssystem erzwungene
CPU-/RAM-Grenze und keine Vorhersage künftiger Fremdlast. Ein logischer CPU-Anteil
verspricht auf unterschiedlichen Kerntypen keine identische Geschwindigkeit.
Anwendungsprofile, native Taskclaims, Lifecycleadapter und die gemeinsame
Hostautorität müssen weiterhin geprüft werden. Ein angehaltener Prozess gibt
seinen RAM durch das Anhalten nicht nachweislich frei.

Zähler- und Zuordnungssemantik: [psutil API](https://psutil.io/api/).

## Ausdrücklicher lesender CLI-Aufruf

```sh
python -m ocean_resources capacity \
  --reserve-ram-bytes 4294967296 \
  --reserve-cpu-units 1 \
  --reserve-disk-bytes 10737418240 \
  --capacity-directory /absoluter/lokaler/arbeitsordner
```

Unter Windows den Befehl in einer Zeile ausführen. Alle drei Reserven und der
vorhandene absolute Dateisystemordner sind Pflicht. Die Zahlen zeigen die
Konfiguration; sie sind kein gemessenes Profil für einen beliebigen Host.
Eine gültige Beobachtung liefert JSON und Exit 0 auch bei Ergebnis HOLD.
Ungültige Konfiguration endet mit Exit 2. Verbraucher müssen Status und gesamten
Readback prüfen, nicht allein den Exitcode. start_authorized bleibt immer false.
CANDIDATE bezeichnet ausschließlich beobachteten Spielraum.

## Anbindung

```python
from ocean_resources.capacity import CapacityPolicy, NativeCapacitySensor

policy = CapacityPolicy(ram_reserve, cpu_reserve, disk_reserve, local_directory)
sensor = NativeCapacitySensor(policy)
reading = sensor()
```

Erst nach gesonderter Profil-, Zuständigkeits- und Rechteabnahme wird sensor an
den einen vorhandenen HostLocalArbiter übergeben. Aufrufe sind serialisiert;
auch fehlgeschlagene Messungen erhalten eine neuere Sequenz. Ein anderer Host
oder ein geforkter Prozess darf den Sensor nicht übernehmen. Dieser Ausbau
liefert native Messung; gemeinsamer Hostdienst, produktive Profile und der echte
Buddha-/Compute-Wechsel bleiben weitere Abnahmen.
