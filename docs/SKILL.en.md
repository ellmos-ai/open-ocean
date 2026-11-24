---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: en
category: infrastructure
description: "Local, verifiable composition and runtime kernel of the ellmos ecosystem with three access modes (Library & Authority Check, Active Composition & GUI Bridge, Supervised Runtime & Agent Service)."
---

# open-ocean — System Skill & Access Modes (EN)

**Languages (World Set 11):** [Deutsch](../SKILL.md) · **English** · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` provides the declarative system composition kernel, resource arbiter, 3-tier authority verification (`ocean authority`), pinned system GUI bridge (`ocean gui`), and supervised runtime for manifestations such as **BACH**. Full command reference (`16` top-level commands, `16` subcommands): [`api/cli-reference.md`](api/cli-reference.md).

## Three Access Modes

1. **Mode A — Library & Diagnostics (Read-Only):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **Mode B — Active Composition, Tasks & GUI Bridge:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **Mode C — Runtime Supervisor, Agents & Console:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## Documentation Precedence (#2459)

1. **Newer User Decision** (decision records / explicit operator approval)
2. **Active Transformation Plan** (for ongoing migration scopes)
3. **Module Documentation** (`ellmos.module.v2` manifest `docs` entry)
4. **Core Documentation** (`docs/CORE.md` and `SKILL.md` of the installed kernel)
