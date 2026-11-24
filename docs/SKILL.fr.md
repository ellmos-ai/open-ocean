---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: fr
category: infrastructure
description: "Noyau local et vérifiable de composition et d'exécution de l'écosystème ellmos avec trois modes d'accès (Bibliothèque et Autorité, Composition Active et Pont GUI, Superviseur d'Exécution et d'Agents)."
---

# open-ocean — Compétence Système et Modes d'Accès (FR)

**Langues (World Set 11) :** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · **Français** · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` constitue le socle déclaratif de composition système, d'arbitrage des ressources, de vérification déterministe d'autorité à trois niveaux (`ocean authority`), de pont GUI épinglé (`ocean gui`) et d'exécution supervisée pour des manifestations telles que **BACH**. Référence complète de la CLI (`16` commandes principales, `16` sous-commandes) : [`api/cli-reference.md`](api/cli-reference.md).

## Les 3 Modes d'Accès

1. **Mode A — Bibliothèque et Diagnostic (Lecture seule) :** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **Mode B — Composition Active, Tâches et Pont GUI :** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **Mode C — Superviseur d'Exécution, Agents et Console :** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## Hiérarchie Documentaire (#2459)

1. **Décision récente de l'utilisateur** (registres de décisions / validation explicite de l'opérateur)
2. **Plan de transformation actif** (pour les périmètres en cours de migration)
3. **Documentation du module** (champ `docs` du manifeste `ellmos.module.v2`)
4. **Documentation du noyau** (`docs/CORE.md` et `SKILL.md` du noyau installé)
