---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: ru
category: infrastructure
description: "Локальное верифицируемое ядро композиции и среды выполнения экосистемы ellmos с тремя режимами доступа (Библиотека и проверка полномочий, Активная композиция и GUI-мост, Супервизор среды выполнения и агентов)."
---

# open-ocean — Системный навык и режимы доступа (RU)

**Языки (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · **Русский** · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` обеспечивает декларативную сборку системы, управление ресурсами, трехуровневую проверку полномочий (`ocean authority`), зафиксированный GUI-мост (`ocean gui`) и контролируемую среду выполнения (на которую опираются такие проявления, как **BACH**). Полный справочник CLI (`16` основных команд, `16` подкоманд): [`api/cli-reference.md`](api/cli-reference.md).

## 3 режима доступа

1. **Режим A — Библиотека и диагностика (Только чтение):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **Режим B — Активная композиция, задачи и GUI-мост:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **Режим C — Супервизор среды выполнения, агенты и консоль:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## Приоритет документации (#2459)

1. **Более новое решение пользователя** (записи решений / явное подтверждение оператора)
2. **Активный план трансформации** (для изменяемых контуров)
3. **Документация модуля** (поле `docs` манифеста `ellmos.module.v2`)
4. **Базовая документация ядра** (`docs/CORE.md` и `SKILL.md` установленного ядра)
