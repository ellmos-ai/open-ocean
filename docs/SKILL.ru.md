---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
language: ru
category: infrastructure
description: "Локальное верифицируемое ядро композиции и среды выполнения экосистемы ellmos с тремя режимами доступа."
---

# open-ocean — Системный навык и режимы доступа (RU)

`open-ocean` обеспечивает декларативную сборку системы, управление ресурсами, мосты управления (Governance) и контролируемую среду выполнения.

## 3 режима доступа

1. **Режим A — Библиотека (Только чтение):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`
2. **Режим B — Активная композиция и GUI-мост:** `python ocean.py plan|up|inspect|task` + `tools.gui_bridge`
3. **Режим C — Супервизор среды выполнения:** `python ocean.py start|status|user|down` + `tools.runtime_supervisor`
