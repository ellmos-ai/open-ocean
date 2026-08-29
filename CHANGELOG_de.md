# Änderungsprotokoll

*[English](CHANGELOG.md)*

## Unveröffentlicht — 2026-08-29

### Hinzugefügt

- Wurzel-CLI `ocean.py` mit `plan`, `up`, `start`, `status`, `down` und `user add`.
- Fähigkeitsgesteuerte Auswahl genau eines aufgelösten `runtime.host`.
- Lokaler authentifizierter Runtime-Supervisor und Kompatibilitätsprojektionen für den
  ausgewählten Host.
- Passwortsichere delegierte Benutzeranlage; Passwörter erscheinen nicht in Prozessargumenten.
- Aufgelöste Komponentenmetadaten in Transaktionsberichten für Lebenszyklus-Konsumenten.
- Exakte, inhaltsgehashte Full-Dev-Komponentenbindungen für Integrationen zwischen Rezept und
  Anbieter; die erste Bindung ordnet `module:software-endpoint-registry` dem `system-explorer` am
  Commit `ec50c92319ba8fc262d695b86818fc85666feff7` zu.
- Die zweite exakte Bindung ordnet `module:automation-registry` dem `automation-master` am Commit
  `ad40de721615518e409b53b00ed4b2a49840db28` zu und verlangt `automation.registry`.
- Anbieterprüfung über Repository-Ursprung, exakten Git-HEAD, sauberen Checkout,
  Modulmanifest-Identität und deklarierte Fähigkeit, bevor eine gebundene Komponente als
  aufgelöst gelten kann.
- Fähigkeitsgesteuerter OCEAN-Produkteinstieg: Ein aufgelöster `unified-gui.host` wird unter
  `/control/` eingehängt, erhält den Bereitstellungstitel `OCEAN Full Dev` und läuft standardmäßig
  auf dem eigenen Port `8810` statt auf dem eigenständigen TerminPilot-PWA-Ursprung des
  Laufzeitanbieters.
- OCEAN-eigener Ursprungsadapter für Root-Umleitung, Produktmanifest und -Offline-Identität,
  Entfernung alter Service-Worker/Caches sowie Delegation der Anbieter-API.

### Behoben

- Der Reload-Prozess des Runtime-Hosts ist abgeschaltet; jeder Start erhält einen eigenen lokalen
  Secret-Key, damit ein authentifizierter Stopp keinen Reload-Kindprozess zurücklässt.
- Ein veralteter Stopp-Status der vorherigen Instanz löst beim Neustart keinen Fehlalarm mehr aus.
- Ein installierter Snapshot lässt sich nach dem Verschwinden von Supervisor und Kindprozess aus
  einem veralteten `running`-Status wiederherstellen, ohne eine veränderte Live-Rezeptautorität neu
  anzuwenden; belegte alte oder angeforderte Ports stoppen weiterhin sicher.
- Die falsche Produktadresse am Anbieter-Wurzelpfad wurde durch die aufgelöste
  OCEAN-Operator-Oberfläche ersetzt. Die frühere HTTP-200-Prüfung hatte TerminPilots
  Fachoberfläche akzeptiert, ohne die Produktidentität zu prüfen.
- Die Wurzel-CLI erzwingt UTF-8-Ausgabe, damit deutsche Hilfetexte unter Windows echte Umlaute
  behalten.
- Runtime-Importe schreiben kein Python-Bytecode mehr in externe Modulprojektionen.
- Vorhandene Rollback-Protokolleinträge bleiben über spätere Komponentendurchläufe erhalten;
  fehlerhafte, doppelte oder widersprüchliche Einträge stoppen die Transaktion vor Schreibzugriffen.
- Die Vorprüfung auf eine aktive Laufzeit und einen belegten Zielport liegt jetzt vor der
  Apply-Transaktion. Ein zweites `up --apply` kann nichts mehr holen oder aktivieren, bevor es die
  bereits laufende Sandbox meldet.
- Das verbleibende PWA-Identitätsleck auf Port `8810` ist geschlossen: Der Anbieter hatte am neuen
  OCEAN-Ursprung weiterhin eigenen Root, Manifest und root-weiten Worker ausgeliefert. Die
  Porttrennung allein war daher noch keine vollständige Produktgrenze.

### Geprüft

- 133 Tests sind grün, einschließlich echter HTTP-Akzeptanz für Start, Status, Benutzeranlage,
  Stopp, Neustart, Wiederherstellung veralteter Zustände, Auswahl von Produktoberfläche und
  -ursprung, PWA-Bereinigung sowie schreibfreier Ablehnung einer bereits laufenden Sandbox.
- Der aktuelle private Full-Dev-Integrationskandidat bestätigt 30/30 Bundle-Pins, löst 53 Module
  und 80 Skills auf und ist unter `http://127.0.0.1:8810/control/` gesund.
- Der echte Anbieter für `software-endpoint-registry` wurde am exakten Pin geholt, projizierte zwei
  Software-Endpunkte (CLI und HTTP) und ergänzte einen Rollback-Protokolleintrag, ohne die 62
  vorhandenen Skill-Einträge zu verlieren.
- Der echte Anbieter für `automation-registry` ist ein sauberer abgetrennter Checkout am exakten
  `automation-master`-Pin und -Ursprung; sein Modulmanifest deklariert `automation.registry`.
- Das Therapy-Bundle ergänzt 18 aufgelöste und installierte Skills. Das erhaltende Protokoll
  umfasst jetzt 80 Skill-Einträge und zwei Einträge gebundener Module.
- Die echte private Laufzeit legte einen zufälligen Wegwerfadministrator an, bestätigte dessen
  Passwort-Hash und kehrte nach der Bereinigung zum ursprünglichen Null-Benutzer-Stand zurück.
- 24 Modulreferenzen bleiben unaufgelöst; acht davon sind Pflicht. Der Lauf meldet daher weiterhin
  `full_composition: false`.
- Die früheren drei Rezept-Pin-Abweichungen wurden ohne spontanes Umpinnen auf dem gepushten Branch
  `ellmos-development-system@489b67880b42ba4bd2a1d8052239896f84192269` abgeglichen; seine
  Übernahme in den kanonischen Rezept-Branch `main` bleibt gesonderte Arbeit.
- Der installierte Snapshot wurde unter `http://127.0.0.1:8810/control/` neu gestartet. HTTP und
  ein echter Playwright-Browser zeigten `OCEAN Full Dev`, keine TerminPilot-/
  Terminkoordination-Marker und ein navigierbares Skills-Panel; Port `8800` lauschte nicht mehr.
- In einem persistenten Playwright-Profil wurde der absichtlich angelegte alte Anbieter-Cache
  entfernt, während ein unabhängiger synthetischer künftiger OCEAN-Cache erhalten blieb;
  Service-Worker-Registrierungen lagen bei null, `/` leitete auf die OCEAN-Übersicht um, und der
  UTF-8-Titel behielt Gedankenstrich und deutsches `Ü` ohne Ersatzzeichen.

Ein Integrations-Checkpoint-Tag ist kein öffentliches Release. Dieser Eintrag enthält weder eine
Sichtbarkeitsänderung noch eine Änderung an `PRIVATE.txt`.
