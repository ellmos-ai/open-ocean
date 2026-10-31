# open-ocean Kerndokumentation

## 1. Konzept

`open-ocean` ist der lokale, verifizierbare Installer- und Laufzeitkern des ellmos-Ökosystems.
Aus deklarativen Rezepten (`bundles`, `catalog`) löst er Abhängigkeiten auf, prüft SHA-256-Pins,
platziert Komponenten isoliert und startet überwachte Laufzeiten über `ocean.py`.

## 2. Installation & Lebenszyklus

- **Planung:** `python ocean.py plan <komposition>`
- **Bereitstellung:** `python ocean.py up <komposition> --apply`
- **Betrieb:** `python ocean.py start --workspace <pfad>` / `python ocean.py status --workspace <pfad>`
- **Inspektion:** `python ocean.py inspect --workspace <pfad> --json`
- **Stopp:** `python ocean.py down --workspace <pfad>`

## 3. GUI-Hilfe-Projektion & Dokumentations-Rangfolge

Die GUI-Hilfeseite (`/help`) projiziert ihre Moduldokumentation direkt aus den `ellmos.module.v2`-Manifesten
der installierten Module (`docs`-Feld mit Einstiegsdatei und verfügbaren Sprachfassungen).

Bei Abweichungen gilt verbindlich folgende Rangfolge:
1. **Jüngere Nutzerentscheidung** vor Dokumentation
2. **Umbauplan** für aktive Transformationsbereiche
3. **Moduldokumentation** für Modulfunktionen
4. **Kerndokumentation** des installierten Kerns für Kernfunktionen
