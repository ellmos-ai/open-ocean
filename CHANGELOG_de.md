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
- Exakte, inhaltsgehashte Full-Dev-Komponentenbindungen für Integrationen zwischen Rezept und
  Anbieter; die erste Bindung ordnet `module:software-endpoint-registry` dem `system-explorer` am
  Commit `ec50c92319ba8fc262d695b86818fc85666feff7` zu.
- Anbieterprüfung über Repository-Ursprung, exakten Git-HEAD, sauberen Checkout,
  Modulmanifest-Identität und deklarierte Fähigkeit, bevor eine gebundene Komponente als
  aufgelöst gelten kann.

### Behoben

- Der Reload-Prozess des Runtime-Hosts ist abgeschaltet; jeder Start erhält einen eigenen lokalen
  Secret-Key, damit ein authentifizierter Stopp keinen Reload-Kindprozess zurücklässt.
- Ein veralteter Stopp-Status der vorherigen Instanz löst beim Neustart keinen Fehlalarm mehr aus.
- Die Wurzel-CLI erzwingt UTF-8-Ausgabe, damit deutsche Hilfetexte unter Windows echte Umlaute
  behalten.
- Runtime-Importe schreiben kein Python-Bytecode mehr in externe Modulprojektionen.
- Vorhandene Rollback-Protokolleinträge bleiben über spätere Komponentendurchläufe erhalten;
  fehlerhafte, doppelte oder widersprüchliche Einträge stoppen die Transaktion vor Schreibzugriffen.

### Geprüft

- 126 Tests sind grün, einschließlich echter HTTP-Akzeptanz für Start, Status, Benutzeranlage,
  Stopp und Neustart.
- Eine echte private Full-Dev-Sandbox bestätigte 29 Bundle-Pins, löste 52 Module und 62 Skills auf
  und erreichte eine gesunde Web-Anmeldeoberfläche auf `127.0.0.1`.
- Der echte Anbieter für `software-endpoint-registry` wurde am exakten Pin geholt, projizierte zwei
  Software-Endpunkte (CLI und HTTP) und ergänzte einen Rollback-Protokolleintrag, ohne die 62
  vorhandenen Skill-Einträge zu verlieren.
- Die echte private Laufzeit legte einen zufälligen Wegwerfadministrator an, bestätigte dessen
  Passwort-Hash und kehrte nach der Bereinigung zum ursprünglichen Null-Benutzer-Stand zurück.
- 25 Modulreferenzen bleiben unaufgelöst; neun davon sind Pflicht. Der Lauf meldet daher weiterhin
  `full_composition: false`.
- Nach dem Neustart von OneDrive rückte die aktuelle Full-Dev-Autorität von 29 auf 30
  Bundle-Referenzen vor. Ein frischer rein lesender Plan stoppte sicher bei drei
  Rezept-Pin-Abweichungen; kein neuer Apply-Lauf ersetzte den gesunden Installations-Snapshot.

Dieser Eintrag enthält weder Release, Tag, Sichtbarkeitsänderung noch eine Änderung an
`PRIVATE.txt`.
