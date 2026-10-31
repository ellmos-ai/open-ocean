"""Identity, Authority & Escalation Ladder, Persona-Routing v2, Learning-Loop & Agent-Library contracts.

Covers:
  * #1958: Canonical authority & escalation ladder (worker -> reviewer -> boss -> operator -> user_gate)
  * #2447, #2448, #2452: persona-routing manifest v2 validation (`roles[]` and `maintenance[]`)
  * #1999-#2003: learning-loop candidate contract (Skill-Gaertner-Pipeline, formerly Hermes)
  * #2478: agent-library 3-tab catalog projection (templates, prompt_agents, chains)
"""
from __future__ import annotations

import re
from typing import Any

ESCALATION_SCHEMA = "ellmos.escalation-ladder.v1"
PERSONA_ROUTING_SCHEMA = "ellmos.persona-routing.v2"
LEARNING_CANDIDATE_SCHEMA = "ellmos.learning-loop-candidate.v1"
AGENT_LIBRARY_SCHEMA = "ellmos.agent-library.v1"

AUTHORITY_LEVELS = ("worker", "reviewer", "boss", "operator", "user_gate")
ACTION_MIN_AUTHORITY = {
    "task_execute": "worker",
    "branch_commit": "worker",
    "task_review": "reviewer",
    "result_accept": "reviewer",
    "role_dispatch": "boss",
    "maintenance_schedule": "boss",
    "protected_branch_merge": "operator",
    "module_activate": "operator",
    "external_publish": "user_gate",
    "store_submission": "user_gate",
    "lock_override": "user_gate",
}
INTERVAL_REF_RE = re.compile(r"^(config|routine|policy):[A-Za-z0-9._/-]+$")


def authority_rank(level: str) -> int:
    if level not in AUTHORITY_LEVELS:
        raise ValueError(f"unknown authority level: {level!r}")
    return AUTHORITY_LEVELS.index(level)


def evaluate_escalation(
    actor_level: str,
    action_class: str,
    *,
    target_locked: bool = False,
    has_user_gate: bool = False,
) -> dict[str, Any]:
    """Evaluate whether an actor has authority for `action_class` or must escalate."""
    if actor_level not in AUTHORITY_LEVELS or action_class not in ACTION_MIN_AUTHORITY:
        return {
            "schema": ESCALATION_SCHEMA,
            "allowed": False,
            "reason_code": "invalid_authority_or_action",
            "required_level": None,
            "escalate_to": "operator",
        }
    if target_locked and not has_user_gate:
        return {
            "schema": ESCALATION_SCHEMA,
            "allowed": False,
            "reason_code": "locked_target_requires_user_gate",
            "required_level": "user_gate",
            "escalate_to": "user_gate",
        }
    required = ACTION_MIN_AUTHORITY[action_class]
    if required == "user_gate" and not has_user_gate and actor_level != "user_gate":
        return {
            "schema": ESCALATION_SCHEMA,
            "allowed": False,
            "reason_code": "user_gate_required",
            "required_level": "user_gate",
            "escalate_to": "user_gate",
        }
    actor_idx = authority_rank(actor_level)
    req_idx = authority_rank(required)
    if required == "user_gate" and has_user_gate and actor_idx >= authority_rank("operator"):
        return {
            "schema": ESCALATION_SCHEMA,
            "allowed": True,
            "reason_code": "allow",
            "required_level": required,
            "escalate_to": None,
        }
    if actor_idx < req_idx:
        next_level = AUTHORITY_LEVELS[min(actor_idx + 1, req_idx)]
        return {
            "schema": ESCALATION_SCHEMA,
            "allowed": False,
            "reason_code": "insufficient_authority_escalate",
            "required_level": required,
            "escalate_to": next_level,
        }
    return {
        "schema": ESCALATION_SCHEMA,
        "allowed": True,
        "reason_code": "allow",
        "required_level": required,
        "escalate_to": None,
    }


def validate_persona_routing_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate `roles[]` and `maintenance[]` blocks in an ellmos.module.v2 manifest (#2447, #2448, #2452)."""
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "problems": ["manifest must be a dict"]}

    roles = manifest.get("roles", [])
    if not isinstance(roles, list):
        problems.append("roles must be a list")
        roles = []
    seen_roles: set[str] = set()
    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            problems.append(f"roles[{idx}] must be a dict")
            continue
        role_id = role.get("id")
        kind = role.get("kind")
        if not isinstance(role_id, str) or not role_id.strip():
            problems.append(f"roles[{idx}].id missing")
        elif role_id in seen_roles:
            problems.append(f"duplicate role id: {role_id}")
        else:
            seen_roles.add(role_id)
        if kind not in {"boss", "expert", "worker", "reviewer"}:
            problems.append(f"roles[{idx}].kind must be boss|expert|worker|reviewer")
        caps = role.get("capabilities")
        if not isinstance(caps, list) or not caps or any(not isinstance(c, str) for c in caps):
            problems.append(f"roles[{idx}].capabilities must be a non-empty string list")

    maintenance = manifest.get("maintenance", [])
    if not isinstance(maintenance, list):
        problems.append("maintenance must be a list")
        maintenance = []
    for idx, item in enumerate(maintenance):
        if not isinstance(item, dict):
            problems.append(f"maintenance[{idx}] must be a dict")
            continue
        routine_id = item.get("id")
        interval_ref = item.get("interval_ref")
        if not isinstance(routine_id, str) or not routine_id.strip():
            problems.append(f"maintenance[{idx}].id missing")
        if not isinstance(interval_ref, str) or INTERVAL_REF_RE.fullmatch(interval_ref) is None:
            problems.append(f"maintenance[{idx}].interval_ref must match config|routine|policy:<name>")
        if not isinstance(item.get("entrypoint"), str) or not item["entrypoint"].strip():
            problems.append(f"maintenance[{idx}].entrypoint missing")

    return {
        "schema": PERSONA_ROUTING_SCHEMA,
        "valid": len(problems) == 0,
        "role_count": len(roles),
        "maintenance_count": len(maintenance),
        "problems": problems,
    }


def validate_learning_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate a Skill-Gaertner (`learning-loop`, formerly Hermes) candidate (#1999-#2003)."""
    problems: list[str] = []
    required = {
        "candidate_id",
        "target_skill_id",
        "origin_session_id",
        "evidence_refs",
        "proposed_diff_sha256",
        "review_state",
    }
    if not isinstance(candidate, dict):
        return {"schema": LEARNING_CANDIDATE_SCHEMA, "valid": False, "problems": ["candidate must be a dict"]}
    missing = sorted(required - set(candidate))
    if missing:
        problems.append(f"missing fields: {missing}")
    evidence = candidate.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence:
        problems.append("evidence_refs must be a non-empty list")
    state = candidate.get("review_state")
    if state not in {"proposed", "reviewed", "accepted", "rejected"}:
        problems.append("review_state must be proposed|reviewed|accepted|rejected")
    if state == "accepted" and not candidate.get("reviewer_principal"):
        problems.append("accepted candidate requires reviewer_principal")
    return {
        "schema": LEARNING_CANDIDATE_SCHEMA,
        "valid": len(problems) == 0,
        "promotable": len(problems) == 0 and state == "accepted",
        "problems": problems,
    }


def project_agent_library_catalog(
    *,
    templates: list[dict[str, Any]],
    prompt_agents: list[dict[str, Any]],
    chains: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project the 3-tab Agent-Library view (`templates`, `prompt_agents`, `chains`) (#2478)."""
    normalized_chains = []
    for chain in chains:
        kind = chain.get("kind") or ("marblerun" if chain.get("type") == "agent_chain" else "toolchain")
        if kind not in {"marblerun", "toolchain"}:
            kind = "toolchain"
        badge = "Agentenkette (MarbleRun)" if kind == "marblerun" else "Befehlskette (Toolchain)"
        normalized_chains.append({**chain, "kind": kind, "badge": badge})
    return {
        "schema": AGENT_LIBRARY_SCHEMA,
        "tabs": ["templates", "prompt_agents", "chains"],
        "system_restore_in_library": False,
        "system_restore_location": "/settings#system-agents-restore",
        "templates": list(templates),
        "prompt_agents": list(prompt_agents),
        "chains": normalized_chains,
    }
