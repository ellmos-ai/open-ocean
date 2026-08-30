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
- [x] `--host`-Argument bei `ocean.py up` korrigiert (7d4de09): `up` traegt jetzt
  dieselben `choices=["127.0.0.1", "localhost"]` wie `start`, ein falscher Wert scheitert
  sofort am Parser statt tief im Lifecycle. Folgeschritt erledigt:
  das gleichnamige `--host` in `tools/ocean_dev.py` (dort Skill-Host-Adapter,
  nicht Netzwerk-Bind) heißt jetzt `--skill-host`; `--host` bleibt als Legacy-Alias gültig, kein Aufrufer bricht.
  Ursprungsbeschreibung: `--host`-Argument bei `ocean.py up` korrigieren: `ocean.py` und `tools/ocean_dev.py`
  besitzen jeweils einen eigenen, gleichnamigen `--host`-Parameter; `ocean.py` reicht sein
  `--host` nie an den `ocean_dev.py`-Subprozess weiter, der stattdessen immer seinen eigenen
  Default `"claude-code"` verwendet. Ein vorgegebenes `--host claude-code` bei `up` bricht
  deshalb deterministisch mit `LifecycleError` ab; `--host` bei `up` weglassen (Default
  `127.0.0.1`), so wie es jeder erfolgreiche Lauf im Bauplan tut.
- [x] Readiness-Gate für `up --apply` ergänzt (7d4de09): neues
  `_assert_composition_complete` in `ocean_lifecycle.py` haelt die Laufzeit zurueck und nennt
  die fehlenden Pflichtkomponenten. Komposition und Installationsstand werden bewusst VORHER
  geschrieben, damit Artefakte und Bericht zur Diagnose bleiben. Ursprungsbeschreibung:
  Readiness-Gate für `up --apply` ergänzen: Es prüft die Provider-Vollständigkeit nicht vor
  dem Start der Laufzeit — ein fehlgeschlagener Provider-Fetch startet trotzdem eine
  unvollständige Komposition (`ocean_lifecycle.py:546-596`; Readiness wird nur berichtet, nie
  durchgesetzt).
- [ ] (Stand 2026-08-30 nicht mehr reproduzierbar — vor dem Bearbeiten neu messen:
  `resolve_bundles.py` setzt `DEFAULT_SKILLS_REGISTRY` bereits auf `components.json` und
  erklaert die fehlende Crosswalk-Datei im Text. Eintrag bleibt stehen, bis jemand die
  Contract-Referenz selbst geprueft hat.)
  Die Referenz `manifests/skills.registry.crosswalk.v1.json` im
  component-registry-bindings-Contract korrigieren: Sie liegt im Bundles-Checkout nicht mit
  nutzbarem `components`-Array vor; die tatsächlich nutzbare Quelle ist `components.json` aus der
  Skills-Registry. Bereits als bekannte Lücke im Tool-Kommentar vermerkt.

## Freigabebreite

- [ ] Eine vollständige frische Full-Ocean-Installation auf einem anderen Rechner ausführen.
- [ ] Die standardmäßig geschlossene öffentliche OPEN-OCEAN-Allowlist unabhängig von FULL OCEAN
  ableiten und testen.
- [ ] Die funktionale BACH-Parität weiterführen; neu entdeckte BACH-Eigenheiten nur ausnahmsweise
  und wertgebunden in einem eigenen Modulzyklus extrahieren.
- [ ] Die offenen Governance-PRs mergen und übernehmen (`policy-registry` #3, `gardener` #4,
  `ellmos-controlcenter-mcp` #9) — alle offen, mergefähig, CI grün zum Stand 2026-08-30, keiner
  gemergt. Hostlokale Registry-Initialisierung, Gardener-Systemquellen und
  ControlCenter-Konfiguration werden erst danach relevant.
- [ ] Geräteseitige OS-Konto-Kopplung für die OCEAN-Benutzeridentität prüfen (ein
  Windows-/macOS-Konto je Gerät) statt eines zusätzlichen App-Passworts; Anlass: Die
  WORKSTATION-LG-Installation läuft ohne OCEAN-Benutzer, während `/control/` und `/api/health`
  ohne Auth erreichbar bleiben.

Diese Punkte autorisieren weder eine Veröffentlichung noch eine Sichtbarkeitsänderung oder die
Entfernung von `PRIVATE.txt`.
