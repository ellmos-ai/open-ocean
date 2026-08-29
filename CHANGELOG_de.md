# Änderungsprotokoll

*[English](CHANGELOG.md)*

## Unveröffentlicht — 2026-08-29

### Hinzugefügt

- Wurzel-CLI `ocean.py` mit `plan`, `up`, `status`, `down` und `user add`.
- Fähigkeitsgesteuerte Auswahl genau eines aufgelösten `runtime.host`.
- Lokaler authentifizierter Runtime-Supervisor und Kompatibilitätsprojektionen für den
  ausgewählten Host.
- Passwortsichere delegierte Benutzeranlage; Passwörter erscheinen nicht in Prozessargumenten.
- Aufgelöste Komponentenmetadaten in Transaktionsberichten für Lebenszyklus-Konsumenten.

### Behoben

- Der Reload-Prozess des Runtime-Hosts ist abgeschaltet; jeder Start erhält einen eigenen lokalen
  Secret-Key, damit ein authentifizierter Stopp keinen Reload-Kindprozess zurücklässt.
- Ein veralteter Stopp-Status der vorherigen Instanz löst beim Neustart keinen Fehlalarm mehr aus.
- Die Wurzel-CLI erzwingt UTF-8-Ausgabe, damit deutsche Hilfetexte unter Windows echte Umlaute
  behalten.
- Runtime-Importe schreiben kein Python-Bytecode mehr in externe Modulprojektionen.

### Geprüft

- 114 Tests sind grün, einschließlich echter HTTP-Akzeptanz für Start, Status, Benutzeranlage,
  Stopp und Neustart.
- Eine echte private Full-Dev-Sandbox bestätigte 29 Bundle-Pins, löste 51 Module und 62 Skills auf
  und erreichte eine gesunde Web-Anmeldeoberfläche auf `127.0.0.1`.
- Die echte private Laufzeit legte einen zufälligen Wegwerfadministrator an, bestätigte dessen
  Passwort-Hash und kehrte nach der Bereinigung zum ursprünglichen Null-Benutzer-Stand zurück.
- Zehn Pflichtmodule bleiben unaufgelöst; der Lauf meldet daher `full_composition: false`.

Dieser Eintrag enthält weder Release, Tag, Sichtbarkeitsänderung noch eine Änderung an
`PRIVATE.txt`.
