# Open-Ocean-Aufgaben

*[English](TODO.md)*

## Unmittelbare Zuverlässigkeitsaufgaben

- [ ] Eine workspacegebundene Interprozess-Startsperre ergänzen. Zwei direkte
  Lebenszyklusaufrufe können derzeit die Leerer-Zustand-Vorprüfung passieren, bevor einer der
  Supervisoren den Laufzeitstatus schreibt. Der ASUS-GEI-Logon-Task vermeidet das durch
  deaktiviertes `StartWhenAvailable` und genau einen Trigger; der Lebenszyklus selbst muss bei
  gleichzeitigen Starts jedoch geschlossen fehlschlagen.
- [ ] Ein OCEAN-Favicon ausliefern oder die Favicon-Anforderung entfernen. Die aktuelle
  Browserabnahme ist gesund, protokolliert aber einen nicht funktionalen `/favicon.ico`-404.
- [ ] ASUS-GEI tatsächlich neu starten und danach den unveränderten Task
  `EllmosOceanFullUserStart`, den exakten Tag-Checkout, das Prozess-Tupel, die Portbelegung, die
  HTTP-Identität und die Full-Ocean-Bereitschaft nachlesen.

## Freigabebreite

- [ ] Eine vollständige frische Full-Ocean-Installation auf einem anderen Rechner ausführen.
- [ ] Die standardmäßig geschlossene öffentliche OPEN-OCEAN-Allowlist unabhängig von FULL OCEAN
  ableiten und testen.
- [ ] Die funktionale BACH-Parität weiterführen; neu entdeckte BACH-Eigenheiten nur ausnahmsweise
  und wertgebunden in einem eigenen Modulzyklus extrahieren.

Diese Punkte autorisieren weder eine Veröffentlichung noch eine Sichtbarkeitsänderung oder die
Entfernung von `PRIVATE.txt`.
