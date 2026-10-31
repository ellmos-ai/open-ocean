---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
language: zh
category: infrastructure
description: "ellmos 生态系统的本地可验证组合与运行时内核，支持三种访问模式。"
---

# open-ocean — 系统技能与访问模式 (ZH)

`open-ocean` 为声明式系统组合、资源调度、治理桥接和受控运行时提供统一基础。

## 三种访问模式

1. **模式 A — 库模式（只读）:** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`
2. **模式 B — 活动组合与 GUI 桥接:** `python ocean.py plan|up|inspect|task` + `tools.gui_bridge`
3. **模式 C — 运行时监管服务:** `python ocean.py start|status|user|down` + `tools.runtime_supervisor`
