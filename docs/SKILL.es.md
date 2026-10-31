---
name: open-ocean
version: 0.3.0
updated: 2026-10-31
language: es
category: infrastructure
description: "Núcleo local y verificable de composición y ejecución del ecosistema ellmos con tres modos de acceso."
---

# open-ocean — Habilidad del Sistema y Modos de Acceso (ES)

`open-ocean` constituye la base declarativa para composiciones del sistema, control de recursos, puentes de gobernanza y tiempos de ejecución supervisados.

## Los 3 Modos de Acceso

1. **Modo A — Biblioteca (Solo lectura):** `ocean_resources.client`, `tools.ocean_inspect`, `tools.governance_bridge`
2. **Modo B — Composición Activa y Puente GUI:** `python ocean.py plan|up|inspect|task` + `tools.gui_bridge`
3. **Modo C — Supervisor de Ejecución:** `python ocean.py start|status|user|down` + `tools.runtime_supervisor`
