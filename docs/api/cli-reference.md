# Open-Ocean — CLI-Referenz (`ocean.py`, automatisch generiert, #2556)

- **Befehle gesamt:** `10`
- **Manifest-SHA256:** `c87842d6cafe3c536a96c9166bd0b8105a2503de580c0b9e96f5237d4966e108`

| Befehl | Aufruf | Beschreibung | Optionen |
|---|---|---|---|
| `down` | `ocean down` | Nur die zugehörige OCEAN-Laufzeit kontrolliert beenden | `--workspace`, `--json` |
| `gui` | `ocean gui` | gepinntes System-GUI-Kit prüfen oder lokal bereitstellen | `--archive`, `--dist-root`, `--receipt`, `--brand-config`, `--universal-fallback`, `--host`, `--port`, `--serve`, `--json` |
| `inspect` | `ocean inspect` | installierte Komponenten mit nativer System-Explorer-Evidenz rein lesend prüfen | `--workspace`, `--resolution`, `--receipt`, `--trust-store`, `--trust-store-sha256`, `--expected-instance-id`, `--expected-host-id`, `--root-only-resolution`, `--evaluated-at`, `--expected-provider-version`, `--component-bindings`, `--json` |
| `plan` | `ocean plan` | Komposition und Laufzeit rein lesend prüfen | `--bundles-root`, `--system-manifest`, `--modules-catalog`, `--skills-registry`, `--component-bindings`, `--source-pins`, `--workspace`, `--gui-archive`, `--gui-source-commit`, `--gui-archive-sha256`, `--json` |
| `stack-status` | `ocean stack-status` | Status aller 11 kanonischen Ocean-Module im Plattformkern anzeigen | `--json` |
| `start` | `ocean start` | installierten OCEAN-Stand oder eine deklarierte Modulrolle starten | `--workspace`, `--host`, `--port`, `--health-timeout`, `--json`, `--manifest`, `--provider`, `--model`, `--effort`, `--request`, `--cwd`, `--name`, `--dry-run` |
| `status` | `ocean status` | Installations- und Laufzeitstatus live prüfen | `--workspace`, `--json` |
| `task` | `ocean task` | Einheitliches Task-Lifecycle-Werkzeug über den Taskkern taskplan (list|take|renew|submit|return|block|reclaim) | — |
| `up` | `ocean up` | OCEAN in einer lokalen Sandbox installieren und starten | `--bundles-root`, `--system-manifest`, `--modules-catalog`, `--skills-registry`, `--component-bindings`, `--source-pins`, `--workspace`, `--gui-archive`, `--gui-source-commit`, `--gui-archive-sha256`, `--json`, `--host`, `--port`, `--apply`, `--policy-registry`, `--lock-cache`, `--health-timeout` |
| `user` | `ocean user` | Benutzer der aktiven OCEAN-Laufzeit verwalten | — |
