# Open-Ocean — Kanonische Modul-Zuordnung & SOLL/IST-Abgleich (Stand: 02.11.2026)

Dieses Dokument hält für `open-ocean` verbindlich fest, welche der 11 kanonischen Ocean-Module im Plattformkern gebunden sind (`tools/ocean_stack_bridge.py` / `python ocean.py stack-status --json`) und wie sich **SOLL-Architektur** und **gemessener IST-Zustand** verhalten.

## 1. SOLL vs. gemessenes IST der 11 Ocean-Modul-Bindungen

| Nr. | Modul-ID | Kanonischer Ort (SOLL) | Gemessenes IST in `open-ocean` | Gemessenes IST in `bach` | Status |
|---|---|---|---|---|---|
| 1 | `ocean-resources` | `ellmos-ai/ocean-resources` (`ocean_resources/ram_distributor.py`) + `open-ocean/ocean_resources/ram_distributor.py` | Gebunden via `tools/ocean_stack_bridge.py` (`load_ocean_ram_distributor_module`) | Gebunden via `system/hub/_services/ocean_stack_bridge.py` & `ocean_resources_adapter.py` | **ERFÜLLT (`bound: true`)** |
| 2 | `task-master` | `ellmos-ai/task-master` (`taskplan/lease.py`) + `open-ocean/tools/task_router.py` | Gebunden via `tools/ocean_stack_bridge.py` & `ocean.py task` | Gebunden via `system/hub/_services/ocean_stack_bridge.py` & `taskplan_bridge.py` | **ERFÜLLT (`bound: true`)** |
| 3 | `ellmos-worker` | `open-ocean/tools/worker_worktree_policy.py` | Eigenständiges Modul + Tests (`tests/test_worker_worktree_policy.py`) | Gebunden via `ocean_stack_bridge.py` | **ERFÜLLT (`bound: true`)** |
| 4 | `review-policy` | `open-ocean/tools/task_result_review_policy.py` | Eigenständiges Modul + Tests | Gebunden via `ocean_stack_bridge.py` | **ERFÜLLT (`bound: true`)** |
| 5 | `escalation-ladder` | `open-ocean/tools/escalation_ladder.py` | Eigenständiges Modul (3-Stufen-Autoritäts-Kaskade, Quote-Tunnel, Eskalationsleiter) | Gebunden via `ocean_stack_bridge.py` | **ERFÜLLT (`bound: true`)** |
| 6 | `persona-routing` | `open-ocean/tools/persona_routing.py` | Eigenständige Moduldatei (`ellmos.persona-routing.v2`, `ModuleDeliveryCatalog`, `project_module_library_and_routines`, `#2447`/`#2448`/`#2452`) | Gebunden via `ocean_stack_bridge.py`, `module_delivery_lifecycle.py` & `module_delivery_projection.py` | **ERFÜLLT (`bound: true`)** |
| 7 | `learning-loop` | `open-ocean/tools/learning_loop.py` | Eigenständige Moduldatei (`ellmos.skill-keeper.v1`, Skill-Gärtner 2-Stufen-Pipeline, `#2455`) | Gebunden via `ocean_stack_bridge.py` & `skill_keeper_service.py` | **ERFÜLLT (`bound: true`)** |
| 8 | `agent-library` | `open-ocean/tools/agent_library.py` | Eigenständige Moduldatei (3-Tab-Katalog, `AutomationLifecycleRegistry` `#2329`, Shared Completion `#2259`, Desktop-Harness `#2337`) | Gebunden via `ocean_stack_bridge.py`, `automation_agents_lifecycle.py`, `shared_completion_selection_integration.py`, `desktop_harness_contract.py` | **ERFÜLLT (`bound: true`)** |
| 9 | `capability-views` | `open-ocean/tools/capability_views.py` | Eigenständige Moduldatei (`software_inventory`, `#2075`) | Gebunden via `ocean_stack_bridge.py` (`ocean_software_inventory`) | **ERFÜLLT (`bound: true`)** |
| 10 | `governance-bridge` | `open-ocean/tools/governance_bridge.py` | Eigenständige Moduldatei (`task_history_audit`, `task_assignees_view`, `task_result_view`, `#2094`/`#2097`/`#2098`) | Gebunden via `ocean_stack_bridge.py` | **ERFÜLLT (`bound: true`)** |
| 11 | `doc-keeper` | `ellmos-ai/doc-keeper` (`src/doc_keeper/extractor.py`) + `open-ocean/tools/help_projection.py` | Gebunden via `tools/ocean_stack_bridge.py` (`load_doc_keeper_module`) | Gebunden via `system/hub/_services/ocean_stack_bridge.py` | **ERFÜLLT (`bound: true`)** |

## 2. Verifikation

```bash
python ocean.py stack-status --json
python tools/generate_api_cli_reference.py
pytest tests/test_ocean_stack_and_modules.py tests/test_store_readiness.py -q
```
