---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: de
category: infrastructure
description: "Lokaler, verifizierbarer Kompositions- und Laufzeitkern des ellmos-Ökosystems mit drei Zugriffsmodi (Bibliothek & Autoritätsprüfung, Aktive Komposition & GUI-Brücke, Überwachter Laufzeit- & Agenten-Service)."
---

# open-ocean — System-Skill & Zugriffsmodi

**Sprachen (World Set 11):** **Deutsch** · [English](docs/SKILL.en.md) · [Español](docs/SKILL.es.md) · [Français](docs/SKILL.fr.md) · [Português](docs/SKILL.pt.md) · [Русский](docs/SKILL.ru.md) · [中文](docs/SKILL.zh.md) · [日本語](docs/SKILL.ja.md) · [العربية](docs/SKILL.ar.md) · [हिन्दी](docs/SKILL.hi.md) · [বাংলা](docs/SKILL.bn.md)

`open-ocean` bildet nach Entscheidung **D-20261012-002** das gemeinsame Fundament für deklarative Systemkompositionen, Ressourcensteuerung, 3-Stufen-Autoritätsprüfung (`ocean authority`), gemeinsame System-GUI-Anbindung (`ocean gui`) und überwachte Laufzeiten (worauf Manifestationen wie **BACH** aufsetzen). Vollständige Befehlsreferenz (`16` Hauptbefehle, `16` Unterbefehle): [`docs/api/cli-reference.md`](docs/api/cli-reference.md).

## Die 3 Zugriffsmodi

| Modus | Name | Einstiegspunkt | Charakter | Empfohlen für |
|---|---|---|---|---|
| **A** | **Bibliothek & Diagnose (Read-Only)** | `ocean_resources.client` / `tools.ocean_inspect` / `tools.governance_bridge` / `python ocean.py stack-status\|authority` | Rein lesend, kein Daemon-Start, keine Zustandsänderung | Modul-/Katalogprüfung, Folgeschritt-Autoritätsprüfung (`check`/`feedback`), Ressourcen-Reads |
| **B** | **Aktive Komposition, Tasks & GUI-Brücke** | `python ocean.py plan\|up\|inspect\|gui\|task` + `tools.gui_bridge` / `tools.gui_server` | Deklarative Auflösung, SHA-gepinnte Bereitstellung, gepinntes System-GUI-Kit & Taskkern | Kompositionsbau, Modul-Integration, `taskplan`-Lifecycle, GUI-/Operator-Abfragen |
| **C** | **Laufzeit-Supervisor, Agenten & Konsole** | `python ocean.py start\|status\|agents\|sessions\|tasks\|chat\|console\|user\|down` + `tools.runtime_supervisor` | Überwachter Daemon-Lebenszyklus mit Prozesshygiene, Worker-Steuerung & Restart-Reconciliation | Produktiver Dauerbetrieb, interaktive Agentenkonsole, Multi-Provider-Sessions |

---

### Modus A: Bibliothek & Autoritätsdiagnose (Read-Only)

Lesender Zugriff auf Kompositionsstatus, die 11 kanonischen Plattform-Modulbindungen (`ocean stack-status`), die deterministische 3-Stufen-Autoritätsprüfung (`ocean authority check|feedback`), Governance-Projektionen (`bach.policy-registry.v1`, `lock_scan_cache`) und Hilfe-Projektionen ohne Start eines Supervisors:

```python
from pathlib import Path
from tools.governance_bridge import lock_cache_snapshot, policy_registry_snapshot
from tools.help_projection import project_installed_module_help

locks = lock_cache_snapshot(Path("LOCK-CACHE.md"))
help_index = project_installed_module_help(Path("."))
```

```bash
python ocean.py stack-status --json
python ocean.py authority check --action-class internal_delivery --strict-followup \
  --goal-id G1 --goal-quote "Update docs" --follows-from-goal --no-new-tradeoff --json
```

### Modus B: Aktive Komposition, Tasks & GUI-Brücke

Auflösen, Verifizieren und Aktivieren deklarativer Rezepte, Bereitstellen des gepinnten System-GUI-Kits (`ocean gui`) sowie Task-Steuerung über `taskplan` (`ocean task`):

```bash
python ocean.py plan <composition-args>
python ocean.py up <composition-args> --apply
python ocean.py inspect --workspace <local-sandbox> --resolution <resolution.json> \
  --trust-store <receipt-trust.json> --trust-store-sha256 <sha256> \
  --expected-instance-id <instance> --expected-host-id <host> --json
python ocean.py gui --archive <system-gui-release.zip> --workspace <local-sandbox> --json
python ocean.py task list
```

### Modus C: Laufzeit-Supervisor, Agenten & Konsole

Überwachter Betrieb mit Windows-Job-Object- bzw. POSIX-Prozessgruppen-Bindung, Fokus-Controller, Agenten-/Session-Verwaltung, Terminal-Konsole (`chat` / `console`) und kontrolliertem Shutdown:

```bash
python ocean.py start --workspace <local-sandbox>
python ocean.py status --workspace <local-sandbox>
python ocean.py agents list --workspace <local-sandbox> --json
python ocean.py sessions list --workspace <local-sandbox> --json
python ocean.py tasks list --workspace <local-sandbox> --json
python ocean.py chat --workspace <local-sandbox> --once "Statusbericht"
python ocean.py user add --workspace <local-sandbox> --username <name> --email <mail>
python ocean.py down --workspace <local-sandbox>
```

---

## Dokumentations-Rangfolge (#2459)

1. **Jüngere Nutzerentscheidung** (Decision-Records / explizite Operator-Freigabe)
2. **Aktueller Umbauplan** (für aktive Transformationsbereiche)
3. **Moduldokumentation** (`ellmos.module.v2` Manifest `docs`-Einstieg für Modulfunktionen)
4. **Kerndokumentation** (`docs/CORE.md` und `SKILL.md` des installierten Kerns)
