---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: es
category: infrastructure
description: "Núcleo local y verificable de composición y ejecución del ecosistema ellmos con tres modos de acceso (Biblioteca y Autoridad, Composición Activa y Puente GUI, Supervisor de Ejecución y Agentes)."
---

# open-ocean — Habilidad del Sistema y Modos de Acceso (ES)

**Idiomas (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · **Español** · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` constituye la base declarativa para composiciones del sistema, control de recursos, verificación determinista de autoridad en tres niveles (`ocean authority`), kit GUI fijado (`ocean gui`) y tiempos de ejecución supervisados (sobre los que operan manifestaciones como **BACH**). Referencia completa de CLI (`16` comandos principales, `16` subcomandos): [`api/cli-reference.md`](api/cli-reference.md).

## Los 3 Modos de Acceso

1. **Modo A — Biblioteca y Diagnóstico (Solo lectura):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **Modo B — Composición Activa, Tareas y Puente GUI:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **Modo C — Supervisor de Ejecución, Agentes y Consola:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## Precedencia Documental (#2459)

1. **Decisión reciente del usuario** (registros de decisiones / aprobación explícita del operador)
2. **Plan activo de transformación** (para ámbitos en migración activa)
3. **Documentación del módulo** (campo `docs` en el manifiesto `ellmos.module.v2`)
4. **Documentación del núcleo** (`docs/CORE.md` y `SKILL.md` del núcleo instalado)
