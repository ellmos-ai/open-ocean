# open-ocean — Dokumentationsübersicht

*[English](README.en.md)* | *[Haupt-README](../README.md)* | *[Haupt-README (Deutsch)](../README_de.md)*

Willkommen im Dokumentationsverzeichnis von `open-ocean`. Dieses Verzeichnis bündelt alle Verträge, Architekturkonzepte, Bedienungsanleitungen und Nachweise des lokalen, verifizierbaren Installer- und Laufzeitkerns.

## Struktur der Dokumentation

| Dokument | Sprache | Beschreibung |
|---|---|---|
| [`CORE.md`](CORE.md) | Deutsch | Kerndokumentation zu Konzept, Installation, Rollback-Garantien und Lebenszyklus. |
| [`GUI-CONSUMER.md`](GUI-CONSUMER.md) | Deutsch | Vertrag über den Verbrauch der System-GUI (`ellmos-system-gui`). |
| [`K9-REMAINING-CI.md`](K9-REMAINING-CI.md) | Deutsch | Permanenter CI-Nachweis der verbleibenden K9-Operationen. |
| [`K9-REMAINING-OPERATIONS-CONTRACT.md`](K9-REMAINING-OPERATIONS-CONTRACT.md) | Deutsch | Gegenüberstellung und Paritätsvertrag der sechs K9-Operationen. |
| [`SKILL.en.md`](SKILL.en.md) | Englisch | Agenten-Fertigkeitsprofil (`SKILL.md`) in englischer Übersetzung (weitere: `SKILL.es.md`, `SKILL.ja.md`, `SKILL.ru.md`, `SKILL.zh.md`). |
| [`DOCUMENT-REGISTER.json`](DOCUMENT-REGISTER.json) | JSON | Zentrales Register aller Dokumente mit Prüfsummen und Leser-Verbindungen. |

## Architekturpläne (`../architecture/`)

- [`architecture/doc-freshness-and-claims.v1.json`](../architecture/doc-freshness-and-claims.v1.json): Maschinenlesbarer Nachweis über Dokumentenfrische, Übersetzungsbeziehungen und verifizierte Doku-Claims.
- [`architecture/OCEAN-CLI-CONSOLE-PLAN.md`](../architecture/OCEAN-CLI-CONSOLE-PLAN.md) / [`architecture/OCEAN-CLI-CONSOLE-PLAN.en.md`](../architecture/OCEAN-CLI-CONSOLE-PLAN.en.md): Dual-Bedienbarkeitskonzept für API + CLI (`ocean chat` / `ocean console`).
- [`architecture/component-bindings.v1.json`](../architecture/component-bindings.v1.json): 13 Kern-Bundles inklusive Sprachfeld- und Dokumentenvertrag.
- [`architecture/product-branding.v1.json`](../architecture/product-branding.v1.json): Verbindliche Produktlinien-Nomenklatur (*Ocean* mit Untertitel *BACH*).

## Sprachpolitik

`open-ocean` folgt der zweisprachigen Mindest-Norm (`de` als Quellsprache, `en` als internationale Pflichtsprache) sowie dem 6-Sprachen-Weltsatz (`de`, `en`, `es`, `ja`, `ru`, `zh`) für universelle Agentenskills.
