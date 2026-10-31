---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
language: en
category: infrastructure
description: "Local, verifiable composition and runtime kernel of the ellmos ecosystem with three access modes (Library/Read-Only, Active Composition & GUI Bridge, Supervised Host Service)."
---

# open-ocean — System Skill & Access Modes (EN)

`open-ocean` provides the declarative system composition kernel, resource arbiter, governance bridges, and supervised runtime for manifestations such as **BACH**.

## Three Access Modes

1. **Mode A — Library (Read-Only):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`
2. **Mode B — Active Composition & GUI Bridge:** `python ocean.py plan|up|inspect|task` + `tools.gui_bridge`
3. **Mode C — Runtime Supervisor & Host Service:** `python ocean.py start|status|user|down` + `tools.runtime_supervisor`
