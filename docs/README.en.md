# open-ocean — Documentation Index

*[Deutsch](README.de.md)* | *[Main README](../README.md)* | *[Main README (German)](../README_de.md)*

Welcome to the documentation directory of `open-ocean`. This directory collects all architecture contracts, operational guides, user manuals, and parity verification reports for the local-first, verifiable installer and runtime core.

## Documentation Structure

| Document | Language | Description |
|---|---|---|
| [`CORE.md`](CORE.md) | German | Core documentation covering system concepts, installation, rollback guarantees, and lifecycle operations. |
| [`GUI-CONSUMER.md`](GUI-CONSUMER.md) | German | Consumer contract for the system GUI (`ellmos-system-gui`). |
| [`K9-REMAINING-CI.md`](K9-REMAINING-CI.md) | German | Continuous CI verification and evidence for remaining K9 operations. |
| [`K9-REMAINING-OPERATIONS-CONTRACT.md`](K9-REMAINING-OPERATIONS-CONTRACT.md) | German | Comparison matrix and parity contract for the six K9 operations. |
| [`SKILL.en.md`](SKILL.en.md) | English | Agent skill specification in English (additional translations: `SKILL.es.md`, `SKILL.ja.md`, `SKILL.ru.md`, `SKILL.zh.md`). |
| [`DOCUMENT-REGISTER.json`](DOCUMENT-REGISTER.json) | JSON | Central register of all tracked documents with SHA-256 hashes and reader relations. |

## Architecture Plans (`../architecture/`)

- [`architecture/doc-freshness-and-claims.v1.json`](../architecture/doc-freshness-and-claims.v1.json): Machine-readable verification of documentation freshness, translation pairs, and verified documentation claims.
- [`architecture/OCEAN-CLI-CONSOLE-PLAN.md`](../architecture/OCEAN-CLI-CONSOLE-PLAN.md) / [`architecture/OCEAN-CLI-CONSOLE-PLAN.en.md`](../architecture/OCEAN-CLI-CONSOLE-PLAN.en.md): Dual-operability architecture for API + CLI (`ocean chat` / `ocean console`).
- [`architecture/component-bindings.v1.json`](../architecture/component-bindings.v1.json): 13 core bundles with language field and documentation manifest contracts.
- [`architecture/product-branding.v1.json`](../architecture/product-branding.v1.json): Pinned product branding contract (*Ocean* with subtitle *BACH*).

## Language Policy

`open-ocean` adheres to a strict bilingual minimum standard (`de` as default source language, `en` as required international language) and the 6-language world set (`de`, `en`, `es`, `ja`, `ru`, `zh`) for agent skill specifications.
