# open-ocean Kerndokumentation

## 1. Konzept

`open-ocean` ist der lokale, verifizierbare Installer- und Laufzeitkern des ellmos-Ökosystems.
Aus deklarativen Rezepten (`bundles`, `catalog`) löst er Abhängigkeiten auf, prüft SHA-256-Pins,
platziert Komponenten isoliert, stellt die gepinnte System-GUI-Brücke sowie die 3-Stufen-Autoritätsprüfung bereit
und startet überwachte Laufzeiten über `ocean.py` (vollständige Referenz aller `16` Haupt- und `16` Unterbefehle: [`api/cli-reference.md`](api/cli-reference.md)).

## 2. Installation & Lebenszyklus

- **Planung & Stack-Diagnose:** `python ocean.py plan <komposition>` / `python ocean.py stack-status --json`
- **Bereitstellung & GUI-Kit:** `python ocean.py up <komposition> --apply` / `python ocean.py gui --archive <zip> --workspace <pfad>`
- **Autoritätsprüfung (Folgeschritt-Regel):** `python ocean.py authority check|feedback ...`
- **Betrieb, Agenten, Nutzer & Konsole:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user --workspace <pfad>`
- **Taskkern (`taskplan`):** `python ocean.py task list|take|renew|submit|return|block|reclaim`
- **Inspektion & Stopp:** `python ocean.py inspect --workspace <pfad> ... --json` / `python ocean.py down --workspace <pfad>`

## 3. GUI-Hilfe-Projektion & Dokumentations-Rangfolge

Die GUI-Hilfeseite (`/help`) projiziert ihre Moduldokumentation direkt aus den `ellmos.module.v2`-Manifesten
der installierten Module (`docs`- und `languages`-Feld mit Einstiegsdatei und verfügbaren Sprachfassungen im 11-Sprachen-World-Set `de, en, es, fr, pt, ru, zh, ja, ar, hi, bn`).

Bei Abweichungen gilt verbindlich folgende Rangfolge:
1. **Jüngere Nutzerentscheidung** vor Dokumentation
2. **Umbauplan** für aktive Transformationsbereiche
3. **Moduldokumentation** für Modulfunktionen
4. **Kerndokumentation** des installierten Kerns für Kernfunktionen
