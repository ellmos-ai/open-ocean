# Security Policy / Sicherheitsrichtlinie

**[English](#english)** | **[Deutsch](#deutsch)**

---

<a name="english"></a>
## English

### Security & Privacy Invariants

`open-ocean` is the community full system architecture and installer layer of the ellmos ecosystem. Because it manages recipe resolution, component verification, local fetching/placement, and skill activation, it strictly enforces the following architectural security invariants:

1. **Local-First & Zero-Egress Invariant**:
   - All manifest evaluations, hash verification, component expansions, and activation steps execute locally on the host machine.
   - The core toolset emits zero telemetry, collects no diagnostic payloads, and connects to no external analytics or cloud services.
2. **Fail-Closed Verification & Transactional Rollback**:
   - Every bundle manifest and component reference is cryptographically verified against pinned SHA hashes before any write action is performed.
   - If a hash verification check fails, execution terminates immediately (exit code 2) without writing anything to disk.
   - All filesystem writes performed during live runs (`--apply`) are recorded in an activation log (`ocean-dev.activation-log.json`). Rollback (`--rollback`) reverses exactly these recorded actions in strict reverse order without heuristic guessing.
3. **Mandatory Dry-Run-First Safety Gate**:
   - Dry-run is the mandatory default mode for all commands (`ocean_dev.py`).
   - No filesystem mutations occur unless `--apply` is explicitly passed by the operator.
4. **Sandboxed Activation Isolation**:
   - `--skills-dir` never defaults to a live agent's active skills directory (e.g. `~/.claude/skills`).
   - The default target is an isolated sandbox (`<workspace>/skills`) that starts empty, ensuring active host agent configurations cannot be silently altered or polluted during testing.
5. **Non-Elevation & Least Privilege**:
   - All scripts and tools run completely unprivileged in standard user space. Root or administrator privileges are never requested or required.

### Supported Versions

| Version | Supported | Notes |
|---------|-----------|-------|
| `0.1.x` | :white_check_mark: | Active release stream |
| `< 0.1.0` | :x: | Pre-release / development builds |

### Reporting a Vulnerability

If you discover a security vulnerability or unexpected privilege escalation in `open-ocean`:

1. **Do not open a public issue.**
2. Report the vulnerability privately via [GitHub Security Advisories](https://github.com/ellmos-ai/open-ocean/security/advisories) or directly to the security team at [security@ellmos.ai](mailto:security@ellmos.ai) and [security@open-bricks.org](mailto:security@open-bricks.org) (fallback: [support@lukasgeiger.com](mailto:support@lukasgeiger.com), [lukas@open-bricks.org](mailto:lukas@open-bricks.org)).
3. Please include detailed reproduction steps, environment details, relevant activation logs, and expected versus observed behavior.
4. We acknowledge receipt within 48 hours and coordinate remediation releases promptly with a 5 business days triage guarantee.

---

<a name="deutsch"></a>
## Deutsch

### Sicherheits- & Datenschutz-Invarianten

`open-ocean` ist die Architektur- und Installer-Schicht des freien Community-Vollsystems im ellmos-Ökosystem. Da Rezept-Auflösungen, Komponenten-Verifizierungen, lokales Platzieren und Skill-Aktivierungen gesteuert werden, gelten verbindliche Sicherheitsinvarianten:

1. **Local-First & Zero-Egress-Invariante**:
   - Sämtliche Manifest-Auflösungen, Hash-Prüfungen, Komponenten-Pläne und Aktivierungsschritte laufen ausschließlich lokal auf dem Host-System.
   - Die Werkzeuge erzeugen keinerlei Netzwerktelemetrie, sammeln keine Nutzungsdaten und übertragen keine Informationen an externe Cloud-Dienste.
2. **Fail-Closed Verifikation & Transaktionaler Rollback**:
   - Jedes Bundle-Manifest und jede Komponenten-Referenz wird vor jeglicher Schreiboperation kryptografisch gegen fixierte SHA-Hashes geprüft.
   - Schlägt eine Verifikation fehl, bricht die Ausführung sofort ab (Exit-Code 2), ohne eine Datei zu schreiben.
   - Alle im Scharfbetrieb (`--apply`) durchgeführten Datei- und Verzeichnisoperationen werden in einem Aktivierungsprotokoll (`ocean-dev.activation-log.json`) festgehalten. Ein Rollback (`--rollback`) nimmt exakt diese Einträge in umgekehrter Reihenfolge ohne Heuristiken zurück.
3. **Verbindliches Dry-Run-Sicherheitsgatter**:
   - Dry-Run ist das verbindliche Standardverhalten aller Werkzeuge (`ocean_dev.py`).
   - Reale Schreiboperationen auf dem Dateisystem finden ausschließlich statt, wenn der Operator explizit `--apply` übergibt.
4. **Sandkasten-Isolation bei Aktivierung**:
   - `--skills-dir` zeigt standardmäßig niemals auf das Produktivverzeichnis eines aktiven KI-Agenten (wie `~/.claude/skills`).
   - Standardziel ist eine isolierte Sandbox (`<workspace>/skills`), sodass aktive Agenten-Konfigurationen bei Test- und Entwicklungsläufen nicht unbemerkt modifiziert werden können.
5. **Keine Rechteausweitung (User-Mode-Betrieb)**:
   - Alle Skripte und Werkzeuge laufen vollständig im normalen Benutzerkontext ohne Administrator- oder Root-Rechte.

### Unterstützte Versionen

| Version | Unterstützt | Hinweise |
|---------|-------------|----------|
| `0.1.x` | :white_check_mark: | Aktiver Release-Zweig |
| `< 0.1.0` | :x: | Vorabversionen / Entwicklungsstände |

### Melden einer Schwachstelle

Wenn Sie eine Sicherheitslücke oder unerwartete Rechteausweitung in `open-ocean` entdecken:

1. **Eröffnen Sie kein öffentliches Issue.**
2. Melden Sie die Schwachstelle vertraulich über [GitHub Security Advisories](https://github.com/ellmos-ai/open-ocean/security/advisories) oder direkt per E-Mail an [security@ellmos.ai](mailto:security@ellmos.ai) und [security@open-bricks.org](mailto:security@open-bricks.org) (Fallback: [support@lukasgeiger.com](mailto:support@lukasgeiger.com), [lukas@open-bricks.org](mailto:lukas@open-bricks.org)).
3. Bitte fügen Sie Reproduktionsschritte, Umgebungsdetails, relevante Aktivierungsprotokolle sowie das erwartete und beobachtete Verhalten bei.
4. Wir bestätigen den Eingang innerhalb von 48 Stunden und koordinieren eine Fehlerbehebung mit einer verbindlichen 5-Werktage-Triage-Zusage.
