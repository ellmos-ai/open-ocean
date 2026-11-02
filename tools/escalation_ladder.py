"""Identity, Authority & Escalation Ladder, Persona-Routing v2, Learning-Loop & Agent-Library contracts.

Covers:
  * #1958: Canonical authority & escalation ladder (worker -> reviewer -> boss -> operator -> user_gate)
  * #2447, #2448, #2452: persona-routing manifest v2 validation (`roles[]` and `maintenance[]`)
  * #1999-#2003: learning-loop candidate contract (Skill-Gaertner-Pipeline, formerly Hermes)
  * #2478: agent-library 3-tab catalog projection (templates, prompt_agents, chains)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ESCALATION_SCHEMA = "ellmos.escalation-ladder.v1"
AUTHORITY_EVIDENCE_SCHEMA = "ellmos.authority-evidence.v1"
COGNITIVE_AUTHORITY_LOOP_SCHEMA = "ellmos.cognitive-authority-loop.v1"
PERSONA_ROUTING_SCHEMA = "ellmos.persona-routing.v2"
LEARNING_CANDIDATE_SCHEMA = "ellmos.learning-loop-candidate.v1"
AGENT_LIBRARY_SCHEMA = "ellmos.agent-library.v1"
ROLE_SOCKET_CATALOG_SCHEMA = "ellmos.role-socket-catalog.v1"

# Flexible provider sockets decouple Ocean/BACH roles from a fixed LLM vendor (`clutch` + `agents-heart`).
PROVIDER_SOCKET_PROFILES: dict[str, dict[str, Any]] = {
    "reasoning_coordinator": {
        "socket_id": "reasoning_coordinator",
        "description": "High-reasoning coordinator socket for Umbrella/Boss routing and multi-step orchestration.",
        "providers": {
            "claude": "claude-opus-4-6",
            "codex": "gpt-5.4",
            "agy": "gemini-3.1-pro",
            "kimi": "kimi-k2.5",
            "ollama": "qwen3.5:35b-a3b",
            "openrouter": "anthropic/claude-opus-4-6",
        },
    },
    "domain_specialist": {
        "socket_id": "domain_specialist",
        "description": "Balanced specialist socket for domain experts, audits, and structured report generation.",
        "providers": {
            "claude": "claude-sonnet-4-6",
            "codex": "gpt-5.4-mini",
            "agy": "gemini-3-flash",
            "kimi": "kimi-k2.5",
            "ollama": "qwen3.5:35b-a3b",
            "openrouter": "anthropic/claude-sonnet-4-6",
        },
    },
    "fast_worker": {
        "socket_id": "fast_worker",
        "description": "Low-latency execution socket for atomic worker tasks, ticket triage, and hygiene scans.",
        "providers": {
            "claude": "claude-haiku-4-5",
            "codex": "gpt-5.4-mini",
            "agy": "gemini-3-flash-lite",
            "kimi": "kimi-k2.5",
            "ollama": "qwen2.5-coder:14b",
            "openrouter": "google/gemini-2.5-flash",
        },
    },
}

# Canonical BACH Boss (Coordinator) & Expert roles mapped to Ocean dual-routing + flexible provider sockets.
OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG: tuple[dict[str, Any], ...] = (
    # --- 6 Coordinators (formerly BACH Boss Agents) ---
    {
        "id": "ati",
        "label": "ATI (Software-Entwicklung & Tooling)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "projekt-pipeline-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='dev')",
        "socket_id": "reasoning_coordinator",
        "experts": ("entwickler-agent", "system-architekt", "devops-experte"),
    },
    {
        "id": "bueroassistent",
        "label": "Büroassistent (Steuern, Verwaltung & Dokumente)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "office-administration-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='office')",
        "socket_id": "reasoning_coordinator",
        "experts": ("steuer-agent", "foerderplaner", "bewerbungsexperte", "rechtsberater"),
    },
    {
        "id": "finanz-assistent",
        "label": "Finanz-Assistent (Banking, Budget & Versicherungen)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "finance-insurance-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='finance')",
        "socket_id": "reasoning_coordinator",
        "experts": ("finanz-experte", "versicherungs-experte", "immobilien-experte"),
    },
    {
        "id": "gesundheitsassistent",
        "label": "Gesundheitsassistent (Medizin, Labor & Prävention)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "therapie-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='health_therapy')",
        "socket_id": "reasoning_coordinator",
        "experts": ("gesundheitsverwalter", "psychologischer-berater"),
    },
    {
        "id": "persoenlicher-assistent",
        "label": "Persönlicher Assistent (Alltag, Termine & Kontakte)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "personal-life-umbrella",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='personal')",
        "socket_id": "reasoning_coordinator",
        "experts": ("reise-experte", "haushalts-experte", "kommunikations-experte"),
    },
    {
        "id": "produktivitaet",
        "label": "Produktivität (Selbstmanagement & Ziele)",
        "tier": "coordinator",
        "legacy_bach_kind": "boss",
        "semantic_route": "selbstmanagement",
        "deterministic_route": "controlcenter_resolve_semantic_route(domain='productivity')",
        "socket_id": "reasoning_coordinator",
        "experts": ("projekt-experte", "qualitaets-experte", "dokumentations-experte", "forschungs-experte"),
    },
    # --- Representative Domain Experts (with flexible provider sockets) ---
    {
        "id": "steuer-agent",
        "label": "Steuer-Experte (Belege & ELSTER)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "office-administration-umbrella -> steuer-agent",
        "deterministic_route": "controlcenter_switch_profile(profile='office-tax')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "foerderplaner",
        "label": "Förderplaner (ICF & Teilhabeplanung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> foerderplaner",
        "deterministic_route": "controlcenter_switch_profile(profile='therapy-icf')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "bewerbungsexperte",
        "label": "Bewerbungsexperte (CV, Matching & Anschreiben)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "office-administration-umbrella -> bewerbungsexperte",
        "deterministic_route": "controlcenter_find_skill(query='bewerbungsexperte')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "gesundheitsverwalter",
        "label": "Gesundheitsverwalter (Befunde & Medikation)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> gesundheitsverwalter",
        "deterministic_route": "controlcenter_switch_profile(profile='health-records')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "psychologischer-berater",
        "label": "Psychologischer Berater (Stabilisierung & Gesprächsführung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "therapie-umbrella -> counseling-basics",
        "deterministic_route": "controlcenter_find_skill(query='therapie-umbrella')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "forschungs-experte",
        "label": "Forschungs-Experte (Literatur, ArXiv & Claim-Mode)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "research-umbrella -> claim-mode",
        "deterministic_route": "controlcenter_find_skill(query='claim-mode')",
        "socket_id": "domain_specialist",
    },
    {
        "id": "dokumentations-experte",
        "label": "Dokumentations-Experte (Doc-Keeper & 3-Ursachen-Prüfung)",
        "tier": "expert",
        "legacy_bach_kind": "expert",
        "semantic_route": "docs-analysis -> doc-keeper",
        "deterministic_route": "controlcenter_find_skill(query='docs-analysis')",
        "socket_id": "domain_specialist",
    },
)

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
        if not isinstance(role_id, str) or not role_id.strip():
            problems.append(f"roles[{idx}].id missing")
        elif role_id in seen_roles:
            problems.append(f"duplicate role id: {role_id}")
        else:
            seen_roles.add(role_id)

        # Support both the ellmos.module.v2.schema.json role contract (label, prompt, request, modes)
        # and the internal capability contract (kind, capabilities).
        if "prompt" in role or "label" in role or "request" in role or "modes" in role:
            if not isinstance(role.get("label"), str) or not role["label"].strip():
                problems.append(f"roles[{idx}].label must be a non-empty string")
            if not isinstance(role.get("prompt"), str) or not role["prompt"].strip():
                problems.append(f"roles[{idx}].prompt must be a non-empty relative path")
            if not isinstance(role.get("request"), str) or not role["request"].strip():
                problems.append(f"roles[{idx}].request must be a non-empty string")
            if not isinstance(role.get("modes"), list):
                problems.append(f"roles[{idx}].modes must be a list")
        else:
            kind = role.get("kind")
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


def get_ocean_role_routing_catalog() -> dict[str, Any]:
    """Return the canonical BACH-to-Ocean Coordinator & Expert role catalog with flexible provider sockets."""
    coordinators = [r for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG if r["tier"] == "coordinator"]
    experts = [r for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG if r["tier"] == "expert"]
    return {
        "schema": ROLE_SOCKET_CATALOG_SCHEMA,
        "routing_modes": ("semantic_umbrella_and_persona", "deterministic_controlcenter_mcp"),
        "provider_sockets": PROVIDER_SOCKET_PROFILES,
        "coordinators": coordinators,
        "experts": experts,
        "total_roles": len(OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG),
    }


def discover_module_role_templates(repos_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Scan installed module `ellmos-module.v2.json` manifests and return Agent-Library templates."""
    root = Path(repos_root) if repos_root is not None else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        return []
    discovered: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        manifest_path = child / "ellmos-module.v2.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        module_id = str(manifest.get("id") or child.name)
        roles = manifest.get("roles")
        if not isinstance(roles, list):
            continue
        for role in roles:
            if not isinstance(role, dict) or not role.get("id"):
                continue
            discovered.append(
                {
                    "id": f"{module_id}:{role['id']}",
                    "role_id": str(role["id"]),
                    "module_id": module_id,
                    "label": str(role.get("label") or role["id"]),
                    "source": "module_manifest_role",
                    "prompt": role.get("prompt"),
                    "request": role.get("request"),
                    "providers": list(role.get("providers") or ("claude", "codex", "agy", "kimi")),
                    "socket_id": "domain_specialist",
                }
            )
    return discovered


def build_full_agent_library_catalog(
    repos_root: str | Path | None = None,
    *,
    extra_prompt_agents: list[dict[str, Any]] | None = None,
    extra_chains: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the populated 3-tab Agent-Library catalog combining BACH Coordinator/Expert roles and module `roles[]`."""
    role_templates: list[dict[str, Any]] = [
        {
            "id": f"ocean-role:{r['id']}",
            "role_id": r["id"],
            "module_id": "open-ocean",
            "label": r["label"],
            "tier": r["tier"],
            "source": "ocean_role_socket_catalog",
            "semantic_route": r["semantic_route"],
            "deterministic_route": r["deterministic_route"],
            "socket_id": r["socket_id"],
            "providers": list(PROVIDER_SOCKET_PROFILES[r["socket_id"]]["providers"].keys()),
        }
        for r in OCEAN_ROLE_ROUTING_AND_SOCKET_CATALOG
    ]
    module_templates = discover_module_role_templates(repos_root)
    default_chains = [
        {"id": "marblerun:doc-keeper-machine", "kind": "marblerun", "label": "Doc-Keeper Machine (3-Cause Audit)"},
        {"id": "marblerun:wishes-come-true-local", "kind": "marblerun", "label": "Wishes-Come-True Local Genie"},
        {"id": "toolchain:daily-hygiene", "kind": "toolchain", "label": "Daily Hygiene & Lock Check"},
    ]
    return project_agent_library_catalog(
        templates=role_templates + module_templates,
        prompt_agents=list(extra_prompt_agents or []),
        chains=list(extra_chains if extra_chains is not None else default_chains),
    )


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


CAPABILITY_PERMISSION_SCHEMA = "ellmos.capability-permissions.v1"

DEFAULT_CAPABILITY_PERMISSIONS: dict[str, bool] = {
    "system_tools": True,
    "browser_control": True,
    "camera": False,
    "microphone": False,
    "screen_capture": False,
    "voice_tts": True,
    "speech_to_text": True,
    "smarthome_robotics": False,
    "ollama": True,
}


def evaluate_capability_permission(
    capability_key: str,
    permissions: dict[str, bool] | None = None,
    *,
    has_user_gate: bool = False,
) -> dict[str, Any]:
    """Fail-closed evaluation of hardware/device capability permissions (#3763-#3768 / Ocean #533-#538)."""
    effective = dict(DEFAULT_CAPABILITY_PERMISSIONS)
    if permissions:
        for k, v in permissions.items():
            if k in effective:
                effective[k] = bool(v)
    if capability_key not in effective:
        return {
            "schema": CAPABILITY_PERMISSION_SCHEMA,
            "capability": capability_key,
            "allowed": False,
            "reason_code": "unknown_capability_denied_fail_closed",
            "effective_permissions": effective,
        }
    granted = bool(effective[capability_key]) or bool(has_user_gate)
    return {
        "schema": CAPABILITY_PERMISSION_SCHEMA,
        "capability": capability_key,
        "allowed": granted,
        "reason_code": "capability_granted" if granted else "capability_disabled_in_permissions_matrix",
        "effective_permissions": effective,
    }


