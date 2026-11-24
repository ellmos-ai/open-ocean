---
name: open-ocean
version: 0.3.1
updated: 2026-11-24
language: zh
category: infrastructure
description: "ellmos 生态系统的本地可验证组合与运行时内核，支持三种访问模式（只读库与权限核验、活动组合与 GUI 桥接、受控运行时与代理监管）。"
---

# open-ocean — 系统技能与访问模式 (ZH)

**语言 (World Set 11):** [Deutsch](../SKILL.md) · [English](SKILL.en.md) · [Español](SKILL.es.md) · [Français](SKILL.fr.md) · [Português](SKILL.pt.md) · [Русский](SKILL.ru.md) · **中文** · [日本語](SKILL.ja.md) · [العربية](SKILL.ar.md) · [हिन्दी](SKILL.hi.md) · [বাংলা](SKILL.bn.md)

`open-ocean` 为声明式系统组合、资源调度、三级权限核验（`ocean authority`）、固定版本系统 GUI 桥接（`ocean gui`）以及受控运行时（如 **BACH** 等系统形态所依托的底座）提供统一基础。完整 CLI 参考（`16` 个主命令、`16` 个子命令）：[`api/cli-reference.md`](api/cli-reference.md)。

## 三种访问模式

1. **模式 A — 库与诊断模式（只读）:** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`, `tools.help_projection`, `python ocean.py stack-status|authority`
2. **模式 B — 活动组合、任务与 GUI 桥接:** `python ocean.py plan|up|inspect|gui|task` + `tools.gui_bridge` / `tools.gui_server`
3. **模式 C — 运行时监管、代理与终端控制台:** `python ocean.py start|status|agents|sessions|tasks|chat|console|user|down` + `tools.runtime_supervisor`

## 文档优先级 (#2459)

1. **最新的用户决策**（决策记录 / 操作员明确批准）
2. **当前迁移与重构计划**（针对正在演进的范围）
3. **模块文档**（`ellmos.module.v2` 清单中的 `docs` 入口）
4. **核心文档**（已安装内核的 `docs/CORE.md` 与 `SKILL.md`）
