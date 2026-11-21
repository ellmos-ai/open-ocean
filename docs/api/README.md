# Open-Ocean — HTTP-API & Modul-Referenz (automatisch generiert, #2556)

- **Schema:** `ellmos.api-cli-reference.v1`
- **HTTP-Routen:** `3`
- **Gebundene Ocean-Module:** `11`
- **Manifest-SHA256:** `06b1c66ed59ca3fb7e2dbc5e3d27ff4b2ea4747f10583c4015520df9f6e2a1e3`

## 1. HTTP-API-Routen (`tools/gui_bridge.py` & `tools/gui_server.py`)

| Methode | Pfad | Quelle |
|---|---|---|
| `GET` | `/api/gui/capabilities` | `tools/gui_server.py` |
| `GET` | `/api/gui/kit-manifest` | `tools/gui_server.py` |
| `GET` | `/health` | `tools/gui_server.py` |

## 2. Kanonische 11 Ocean-Modul-Bindungen (`tools/ocean_stack_bridge.py`)

| Modul-ID | Python-Modul | Gebunden |
|---|---|---|
| `agent-library` | `tools.agent_library` | `ja` |
| `capability-views` | `tools.capability_views` | `ja` |
| `doc-keeper` | `doc_keeper.extractor` | `ja` |
| `ellmos-worker` | `tools.worker_worktree_policy` | `ja` |
| `escalation-ladder` | `tools.escalation_ladder` | `ja` |
| `governance-bridge` | `tools.governance_bridge` | `ja` |
| `learning-loop` | `tools.learning_loop` | `ja` |
| `ocean-resources` | `ocean_resources.ram_distributor` | `ja` |
| `persona-routing` | `tools.persona_routing` | `ja` |
| `review-policy` | `tools.task_result_review_policy` | `ja` |
| `task-master` | `taskplan.lease` | `ja` |
