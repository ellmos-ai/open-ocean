---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
category: infrastructure
description: "Lokaler, verifizierbarer Kompositions- und Laufzeitkern des ellmos-Ökosystems mit drei Zugriffsmodi (Bibliothek/Read-Only, Aktive Komposition & GUI-Brücke, Überwachter Host-Service)."
---

# open-ocean — System-Skill & Zugriffsmodi

`open-ocean` bildet nach Entscheidung **D-20261012-002** das gemeinsame Fundament für deklarative Systemkompositionen, Ressourcensteuerung, Governance-Brücken und überwachte Laufzeiten (worauf Manifestationen wie **BACH** aufsetzen).

## Die 3 Zugriffsmodi

| Modus | Name | Einstiegspunkt | Charakter | Empfohlen für |
|---|---|---|---|---|
| **A** | **Bibliothek (Gast / Read-Only)** | `ocean_resources.client` / `tools.ocean_inspect` / `tools.governance_bridge` | Rein lesend, kein Daemon-Start, keine Zustandsänderung | Statusabfragen, Katalog-/Governance-Prüfung, Ressourcen-Reads |
| **B** | **Aktive Komposition & Brücke** | `python ocean.py plan|up|inspect` + `tools.gui_bridge` | Deklarative Auflösung, SHA-gepinnte Bereitstellung, HTTP/GUI-Brücke | Kompositionsbau, Modul-Integration, GUI-/Operator-Abfragen |
| **C** | **Laufzeit-Supervisor & Host-Service** | `python ocean.py start|status|user|down` + `tools.runtime_supervisor` | Überwachter Daemon-Lebenszyklus mit Prozesshygiene & Restart-Reconciliation | Produktiver Dauerbetrieb, Multi-Provider-Sessions, Host-Steuerung |

---

### Modus A: Bibliothek (Read-Only)

Lesender Zugriff auf Kompositionsstatus, Governance-Projektionen (`bach.policy-registry.v1`, `lock_scan_cache`) und Ressourcen-Telemetrie ohne Start eines Supervisors:

```python
from pathlib import Path
from tools.governance_bridge import lock_cache_snapshot, policy_registry_snapshot
from tools.help_projection import project_installed_module_help

locks = lock_cache_snapshot(Path("LOCK-CACHE.md"))
help_index = project_installed_module_help(Path("."))
```

### Modus B: Aktive Komposition & GUI-Brücke

Auflösen, Verifizieren und Aktivieren deklarativer Rezepte sowie Bereitstellung der vertragstreuen HTTP-Brücke (`/api/governance/*`, `/api/usecases`, `/api/capabilities`):

```bash
python ocean.py plan <composition-args>
python ocean.py up <composition-args> --apply
python ocean.py inspect --workspace <local-sandbox> --json
```

### Modus C: Laufzeit-Supervisor & Host-Service

Überwachter Betrieb mit Windows-Job-Object- bzw. Prozessgruppen-Bindung, Fokus-Controller und kontrolliertem Shutdown:

```bash
python ocean.py start --workspace <local-sandbox>
python ocean.py status --workspace <local-sandbox>
python ocean.py down --workspace <local-sandbox>
```

---

## Dokumentations-Rangfolge (#2459)

1. **Jüngere Nutzerentscheidung** (Decision-Records / explizite Operator-Freigabe)
2. **Aktueller Umbauplan** (für aktive Transformationsbereiche)
3. **Moduldokumentation** (`ellmos.module.v2` Manifest `docs`-Einstieg für Modulfunktionen)
4. **Kerndokumentation** (`docs/CORE.md` und `SKILL.md` des installierten Kerns)
