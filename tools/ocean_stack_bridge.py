# -*- coding: utf-8 -*-
"""Central Ocean-Stack Module Binding Registry for Open-Ocean (`tools.ocean_stack_bridge`).

Mirror counterpart to BACH's `system/hub/_services/ocean_stack_bridge.py`:
verifies and exposes all 11 canonical Ocean modules (`ocean-resources`, `task-master`,
`ellmos-worker`, `review-policy`, `escalation-ladder`, `persona-routing`,
`learning-loop`, `agent-library`, `capability-views`, `governance-bridge`, `doc-keeper`)
so both `open-ocean` and `bach` share the exact same 11-module binding contract.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

_MODULE_CACHE: dict[str, Any] = {}


def _candidate_repo_roots() -> list[Path]:
    ocean_root = Path(__file__).resolve().parents[1]
    candidates = [
        ocean_root.parent,
        Path(os.environ.get("OCEAN_REPOS_ROOT", "")) if os.environ.get("OCEAN_REPOS_ROOT") else None,
        Path("C:/_Local_DEV/repos"),
        Path("/Users/lukas/services"),
        ocean_root,
    ]
    seen: list[Path] = []
    for c in candidates:
        if c and c not in seen and c.is_dir():
            seen.append(c)
    return seen


def _load_module_from_repo(cache_key: str, import_name: str, repo_name: str, rel_file: str) -> Any:
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]

    ocean_root = Path(__file__).resolve().parents[1]
    if repo_name == "open-ocean":
        local_target = ocean_root / rel_file
        if local_target.is_file():
            mod = importlib.import_module(import_name)
            _MODULE_CACHE[cache_key] = mod
            return mod

    for root in _candidate_repo_roots():
        repo_dir = root / repo_name if root.name != repo_name else root
        target = repo_dir / rel_file
        if target.is_file():
            for p_str in (str(target.parent), str(repo_dir / "src"), str(repo_dir)):
                if p_str not in sys.path:
                    sys.path.insert(0, p_str)
            spec = importlib.util.spec_from_file_location(cache_key, target)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[cache_key] = mod
                try:
                    spec.loader.exec_module(mod)
                    _MODULE_CACHE[cache_key] = mod
                    return mod
                except ImportError:
                    mod = importlib.import_module(import_name)
                    _MODULE_CACHE[cache_key] = mod
                    return mod

    mod = importlib.import_module(import_name)
    _MODULE_CACHE[cache_key] = mod
    return mod


def load_ocean_ram_distributor_module() -> Any:
    try:
        return _load_module_from_repo(
            "ocean_resources_ram_distributor",
            "ocean_resources.ram_distributor",
            "ocean-resources",
            "ocean_resources/ram_distributor.py",
        )
    except ImportError:
        return _load_module_from_repo(
            "ocean_resources_ram_distributor",
            "ocean_resources.ram_distributor",
            "open-ocean",
            "ocean_resources/ram_distributor.py",
        )


def load_taskplan_lease_module() -> Any:
    try:
        return _load_module_from_repo(
            "taskplan_lease_kernel",
            "taskplan.lease",
            "task-master",
            "taskplan/lease.py",
        )
    except ImportError:
        return _load_module_from_repo(
            "ocean_task_router",
            "tools.task_router",
            "open-ocean",
            "tools/task_router.py",
        )


def load_worker_worktree_policy_module() -> Any:
    return _load_module_from_repo(
        "ocean_worker_worktree_policy",
        "tools.worker_worktree_policy",
        "open-ocean",
        "tools/worker_worktree_policy.py",
    )


def load_task_result_review_policy_module() -> Any:
    return _load_module_from_repo(
        "ocean_task_result_review_policy",
        "tools.task_result_review_policy",
        "open-ocean",
        "tools/task_result_review_policy.py",
    )


def load_escalation_ladder_module() -> Any:
    return _load_module_from_repo(
        "ocean_escalation_ladder",
        "tools.escalation_ladder",
        "open-ocean",
        "tools/escalation_ladder.py",
    )


def load_persona_routing_module() -> Any:
    return _load_module_from_repo(
        "ocean_persona_routing",
        "tools.persona_routing",
        "open-ocean",
        "tools/persona_routing.py",
    )


def load_learning_loop_module() -> Any:
    return _load_module_from_repo(
        "ocean_learning_loop",
        "tools.learning_loop",
        "open-ocean",
        "tools/learning_loop.py",
    )


def load_agent_library_module() -> Any:
    return _load_module_from_repo(
        "ocean_agent_library",
        "tools.agent_library",
        "open-ocean",
        "tools/agent_library.py",
    )


def load_capability_views_module() -> Any:
    return _load_module_from_repo(
        "ocean_capability_views",
        "tools.capability_views",
        "open-ocean",
        "tools/capability_views.py",
    )


def load_governance_bridge_module() -> Any:
    return _load_module_from_repo(
        "ocean_governance_bridge",
        "tools.governance_bridge",
        "open-ocean",
        "tools/governance_bridge.py",
    )


def load_doc_keeper_module() -> Any:
    try:
        return _load_module_from_repo(
            "ellmos_doc_keeper_extractor",
            "doc_keeper.extractor",
            "doc-keeper",
            "src/doc_keeper/extractor.py",
        )
    except ImportError:
        return _load_module_from_repo(
            "ocean_help_projection",
            "tools.help_projection",
            "open-ocean",
            "tools/help_projection.py",
        )


def load_voice_io_module() -> Any:
    return _load_module_from_repo(
        "ellmos_voice_io_service",
        "ellmos_voice_io.service",
        "ellmos-voice-io",
        "src/ellmos_voice_io/service.py",
    )


def load_talk_module() -> Any:
    return _load_module_from_repo(
        "ellmos_talk_engine",
        "ellmos_talk.engine",
        "ellmos-talk",
        "src/ellmos_talk/engine.py",
    )


def load_sensation_module() -> Any:
    return _load_module_from_repo(
        "ellmos_sensation_sensor_hub",
        "ellmos_sensation.sensor_hub",
        "ellmos-sensation",
        "src/ellmos_sensation/sensor_hub.py",
    )


def load_homecontrol_module() -> Any:
    return _load_module_from_repo(
        "ellmos_homecontrol_hub",
        "ellmos_homecontrol.hub",
        "ellmos-homecontrol",
        "src/ellmos_homecontrol/hub.py",
    )


def load_robotics_module() -> Any:
    return _load_module_from_repo(
        "ellmos_robotics_mcp_standard",
        "ellmos_robotics.mcp_standard",
        "ellmos-robotics",
        "src/ellmos_robotics/mcp_standard.py",
    )


def ocean_capability_extensions_status() -> dict[str, Any]:
    """Return binding status of the 5 multimodal/embodied capability modules (#533-#537)."""
    ext_modules = {
        "ellmos-voice-io": ("ellmos_voice_io.service", load_voice_io_module),
        "ellmos-talk": ("ellmos_talk.engine", load_talk_module),
        "ellmos-sensation": ("ellmos_sensation.sensor_hub", load_sensation_module),
        "ellmos-homecontrol": ("ellmos_homecontrol.hub", load_homecontrol_module),
        "ellmos-robotics": ("ellmos_robotics.mcp_standard", load_robotics_module),
    }
    bound: dict[str, Any] = {}
    for name, (mod_id, loader) in ext_modules.items():
        try:
            m = loader()
            bound[name] = {
                "bound": True,
                "module": mod_id,
                "file": getattr(m, "__file__", None),
            }
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            bound[name] = {
                "bound": False,
                "module": mod_id,
                "error": str(exc),
            }
    return bound


def ocean_stack_status() -> dict[str, Any]:
    """Return status of all 11 canonical Ocean modules bound in Open-Ocean."""
    modules = {
        "ocean-resources": ("ocean_resources.ram_distributor", load_ocean_ram_distributor_module),
        "task-master": ("taskplan.lease", load_taskplan_lease_module),
        "ellmos-worker": ("tools.worker_worktree_policy", load_worker_worktree_policy_module),
        "review-policy": ("tools.task_result_review_policy", load_task_result_review_policy_module),
        "escalation-ladder": ("tools.escalation_ladder", load_escalation_ladder_module),
        "persona-routing": ("tools.persona_routing", load_persona_routing_module),
        "learning-loop": ("tools.learning_loop", load_learning_loop_module),
        "agent-library": ("tools.agent_library", load_agent_library_module),
        "capability-views": ("tools.capability_views", load_capability_views_module),
        "governance-bridge": ("tools.governance_bridge", load_governance_bridge_module),
        "doc-keeper": ("doc_keeper.extractor", load_doc_keeper_module),
    }
    bound: dict[str, Any] = {}
    for name, (mod_id, loader) in modules.items():
        try:
            m = loader()
            bound[name] = {
                "bound": True,
                "module": mod_id,
                "file": getattr(m, "__file__", None),
            }
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            bound[name] = {
                "bound": False,
                "module": mod_id,
                "error": str(exc),
            }
    extensions = ocean_capability_extensions_status()
    return {
        "schema": "ocean.stack-bindings.v1",
        "stack_role": "canonical-ocean-platform-core",
        "bound_count": sum(1 for item in bound.values() if item["bound"]),
        "total_modules": len(bound),
        "modules": bound,
        "capability_extensions": extensions,
        "capability_extensions_bound_count": sum(1 for item in extensions.values() if item["bound"]),
    }
