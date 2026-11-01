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
AUTHORITY_EVIDENCE_SCHEMA = "ellmos.authority-evidence.v1"
COGNITIVE_AUTHORITY_LOOP_SCHEMA = "ellmos.cognitive-authority-loop.v1"
PERSONA_ROUTING_SCHEMA = "ellmos.persona-routing.v2"
LEARNING_CANDIDATE_SCHEMA = "ellmos.learning-loop-candidate.v1"
AGENT_LIBRARY_SCHEMA = "ellmos.agent-library.v1"

AUTHORITY_TUNNEL_TIERS = (
    "semantic_tunneling",     # Tier 1: Dynamic everyday reversible work (authority_ref / goal context)
    "quote_evidence_tunnel",  # Tier 2: Deterministic verbatim quote check against source (NemoFold evidence.py)
    "hard_gate",              # Tier 3: Cryptographic / LOCK.user / hashed security question gate
)
INWARD_FIRST_AUTHORITY_CASCADE = (
    "context_tunnel_and_goal",
    "decisions_and_user_mind",
    "parent_orchestrator",
    "user_gate",
)

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


def _normalize_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_quote_tunnel_evidence(
    *,
    source_id: str,
    literal_quote: str,
    source_texts: dict[str, str],
    decision_id: str | None = None,
    superseded_ids: set[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Deterministic quote-tunnel verifier (`ellmos-authority-evidence`, extracted from NemoFold `evidence.py`).

    Checks in <1 ms whether `literal_quote` exists verbatim in `source_texts[source_id]` and has not been
    superseded by Terraforming (intentional user document edits) or corrupted by natural drift/erosion.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        return {
            "schema": AUTHORITY_EVIDENCE_SCHEMA,
            "verified": False,
            "reason_code": "empty_source_id",
            "source_id": source_id,
            "decision_id": decision_id,
        }
    if decision_id and decision_id in set(superseded_ids):
        return {
            "schema": AUTHORITY_EVIDENCE_SCHEMA,
            "verified": False,
            "reason_code": "superseded_by_terraforming",
            "source_id": source_id,
            "decision_id": decision_id,
        }
    raw_source = source_texts.get(source_id)
    if raw_source is None:
        return {
            "schema": AUTHORITY_EVIDENCE_SCHEMA,
            "verified": False,
            "reason_code": "unknown_source",
            "source_id": source_id,
            "decision_id": decision_id,
        }
    norm_quote = _normalize_quote(literal_quote)
    norm_source = _normalize_quote(raw_source)
    if not norm_quote or norm_quote not in norm_source:
        return {
            "schema": AUTHORITY_EVIDENCE_SCHEMA,
            "verified": False,
            "reason_code": "quote_not_found_or_eroded",
            "source_id": source_id,
            "decision_id": decision_id,
        }
    return {
        "schema": AUTHORITY_EVIDENCE_SCHEMA,
        "verified": True,
        "reason_code": "verified_verbatim_quote",
        "source_id": source_id,
        "decision_id": decision_id,
    }


def evaluate_cognitive_action_authority(
    *,
    action_class: str,
    reversible: bool = True,
    target_locked: bool = False,
    authority_ref: str | None = None,
    active_goal_or_plan_id: str | None = None,
    quote_evidence: dict[str, Any] | None = None,
    source_texts: dict[str, str] | None = None,
    has_hard_gate: bool = False,
) -> dict[str, Any]:
    """Evaluate the cognitive action loop (`Want to act -> Authority Checker -> Do it / Ask there to get`).

    Implements the 3-tier hybrid (`semantic_tunneling` -> `quote_evidence_tunnel` -> `hard_gate`)
    and explicitly prevents the `authority_desert` error class where clear, context-secured user intent
    would otherwise be blocked by static borders.
    """
    required_level = ACTION_MIN_AUTHORITY.get(action_class, "operator")

    # Tier 3: Hard Gate required for locked targets or irreversible user_gate actions
    if target_locked or required_level == "user_gate":
        if has_hard_gate:
            return {
                "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
                "allowed": True,
                "decision": "do_it",
                "tier": "hard_gate",
                "reason_code": "hard_gate_verified",
                "ask_where_to_get": (),
                "authority_desert_risk": False,
            }
        return {
            "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
            "allowed": False,
            "decision": "ask_there_to_get",
            "tier": "hard_gate",
            "reason_code": "locked_or_irreversible_requires_hard_gate",
            "ask_where_to_get": ("user_gate",),
            "authority_desert_risk": False,
        }

    # Tier 2: Deterministic Quote-Tunnel (`ellmos-authority-evidence`) for threshold / non-reversible actions
    if quote_evidence and source_texts is not None:
        check = validate_quote_tunnel_evidence(
            source_id=str(quote_evidence.get("source_id", "")),
            literal_quote=str(quote_evidence.get("quote", "")),
            source_texts=source_texts,
            decision_id=quote_evidence.get("decision_id"),
            superseded_ids=tuple(quote_evidence.get("superseded_ids", ())),
        )
        if check["verified"]:
            return {
                "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
                "allowed": True,
                "decision": "do_it",
                "tier": "quote_evidence_tunnel",
                "reason_code": "quote_tunnel_verified",
                "ask_where_to_get": (),
                "authority_desert_risk": False,
            }

    # Tier 1: Semantic Authority Tunneling for reversible everyday actions backed by goal/plan/authority_ref
    has_semantic_context = bool(
        (authority_ref and authority_ref.strip())
        or (active_goal_or_plan_id and active_goal_or_plan_id.strip())
    )
    if reversible and has_semantic_context and required_level in {"worker", "reviewer", "boss"}:
        return {
            "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
            "allowed": True,
            "decision": "do_it",
            "tier": "semantic_tunneling",
            "reason_code": "semantic_context_secured",
            "ask_where_to_get": (),
            "authority_desert_risk": False,
        }

    # Authority missing -> cascade inward first before interrupting user
    return {
        "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
        "allowed": False,
        "decision": "ask_there_to_get",
        "tier": "quote_evidence_tunnel" if not reversible else "semantic_tunneling",
        "reason_code": "authority_missing_cascade_inward_first",
        "ask_where_to_get": INWARD_FIRST_AUTHORITY_CASCADE,
        "authority_desert_risk": has_semantic_context,
    }


def record_post_action_authority_feedback(
    *,
    action_class: str,
    prompted_user: bool,
    user_intent_was_already_in_context: bool,
    action_exceeded_intent: bool = False,
) -> dict[str, Any]:
    """After-Action Reflection, Learning & Feedback for the Cognitive Authority Loop."""
    if action_exceeded_intent:
        classification = "error_overreach"
        lesson = "Tighten threshold check: require Tier-2 quote_evidence_tunnel for this action scope."
    elif prompted_user and user_intent_was_already_in_context:
        classification = "error_authority_desert"
        lesson = (
            "Authority desert detected: user intent was already context-secured in Goal/Plan/Transcript. "
            "Propagate authority_ref / quote_evidence via WorkflowHooker instead of prompting user."
        )
    else:
        classification = "aligned_flow"
        lesson = "Authority flow matched user intent without friction."

    return {
        "schema": COGNITIVE_AUTHORITY_LOOP_SCHEMA,
        "action_class": action_class,
        "classification": classification,
        "is_error": classification in {"error_overreach", "error_authority_desert"},
        "lesson": lesson,
    }

