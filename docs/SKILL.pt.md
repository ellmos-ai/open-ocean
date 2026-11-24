---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: pt
category: infrastructure
description: "Núcleo local e verificável de composição e execução do ecossistema ellmos com três modos de acesso (Biblioteca e Autoridade, Composição Ativa e Ponte GUI, Supervisor de Execução e Agentes)."
---

# open-ocean — Competência do Sistema e Modos de Acesso (PT)

**Idiomas (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · **Português** · [Русский](SKILL.ru.md) · [中文](SKILL.zh.md) · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` fornece o núcleo declarativo de composição de sistemas, arbitragem de recursos, verificação determinística de autoridade em três níveis (`ocean authority`), kit GUI fixado por hash (`ocean gui`) e tempo de execução supervisionado para manifestações como o **BACH**. Referência completa da CLI (`16` comandos principais, `16` subcomandos): [`api/cli-reference.md`](api/cli-reference.md).

## Os 3 Modos de Acesso

1. **Modo A — Biblioteca e Diagnóstico (Somente leitura):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **Modo B — Composição Ativa, Tarefas e Ponte GUI:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **Modo C — Supervisor de Execução, Agentes e Console:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## Precedência Documental (#2459)

1. **Decisão mais recente do usuário** (registros de decisão / aprovação explícita do operador)
2. **Plano de transformação ativo** (para escopos em migração ativa)
3. **Documentação do módulo** (campo `docs` no manifesto `ellmos.module.v2`)
4. **Documentação central** (`docs/CORE.md` e `SKILL.md` do núcleo instalado)
