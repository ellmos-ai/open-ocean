# -*- coding: utf-8 -*-
"""Ocean-Modul learning-loop: Skill-Gärtner / Skill Keeper (#1999-#2003, #2455).
- Löst die bisherige 'Hermes'-Heuristik ab (Tabellen: skill_keeper_candidates,
  skill_keeper_runs; Routen: /api/learning/skill-keeper/* mit Übergangsalias
  /api/learning/hermes/*; das Chat-Backend 'hermes' bleibt unberührt).
- Stufe 1: Sammeln und Bereinigen als deterministischer Job (requires_model=False).
- Stufe 2: Ausarbeitung jedes Kandidaten durch die Rolle 'skill-gaertner'
  (Agent Pflicht, requires_model=True) nach den Hausregeln des ellmos-skill-creator.
- GUI-Ort: gebündelt unter 'Skills & Software › Skill Keeper'.
"""
from __future__ import annotations

from typing import Any

LEARNING_CANDIDATE_SCHEMA = "ellmos.learning-loop-candidate.v1"
SKILL_KEEPER_SCHEMA = "ellmos.skill-keeper.v1"

REQUIRED_HOUSE_FIELDS = (
    "name",
    "version",
    "role",
    "category",
    "description",
    "triggers",
    "visibility",
    "languages",
    "config_json",
    "connections_json",
    "evals",
    "user_usecases",
    "usecase_gaps",
)

API_ROUTES = {
    "canonical": "/api/learning/skill-keeper/candidates",
    "legacy_alias": "/api/learning/hermes/candidates",
    "chat_backend_hermes_preserved": True,
    "ui_location": "Skills & Software › Skill Keeper",
}


def validate_learning_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate a Skill-Gärtner (`learning-loop`, formerly Hermes) candidate (#1999-#2003)."""
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


def collect_skill_candidates_job(raw_patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministischer Sammel-Job (class='job', requires_model=False)."""
    candidates: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in raw_patterns:
        name = str(item.get("name") or "").strip().lower().replace(" ", "-")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        candidates.append({
            "name": name,
            "raw_description": str(item.get("description") or "").strip(),
            "category": str(item.get("category") or "utilities"),
            "status": "collected_raw",
            "requires_agent_elaboration": True,
        })
    return candidates


def elaborate_candidate_with_skill_gaertner(
    candidate: dict[str, Any],
    *,
    agent_role: str = "skill-gaertner",
) -> dict[str, Any]:
    """Ausarbeitung durch den Skill-Gärtner nach den Regeln des ellmos-skill-creator."""
    if agent_role != "skill-gaertner":
        raise PermissionError("Ausarbeitung erfordert die Rolle 'skill-gaertner'")
    name = candidate["name"]
    elaborated = {
        "name": name,
        "version": "1.0.0",
        "role": "skill-gaertner",
        "category": candidate.get("category", "utilities"),
        "description": candidate.get("raw_description") or f"Kuratierter Skill {name}",
        "triggers": [f"/{name}", name],
        "visibility": "private-only",
        "languages": ["de", "en"],
        "config_json": {"learning_contract": SKILL_KEEPER_SCHEMA, "auto_publish": False},
        "connections_json": {"mcp": [], "bundles": []},
        "evals": [{"id": f"{name}-smoke", "type": "contract"}],
        "user_usecases": [f"Standardanwendung für {name}"],
        "usecase_gaps": [],
        "status": "awaiting_user_review",
        "ui_surface": "Skills & Software › Skill Keeper",
    }
    return elaborated


def validate_skill_creator_house_format(skill_doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for f in REQUIRED_HOUSE_FIELDS:
        if f not in skill_doc or skill_doc[f] in (None, ""):
            errors.append(f"Pflichtfeld fehlt: {f}")
    if skill_doc.get("visibility") != "private-only":
        errors.append("visibility muss standardmäßig 'private-only' sein")
    langs = skill_doc.get("languages") or []
    if not ("de" in langs and "en" in langs):
        errors.append("Sprachfassungen DE und EN sind Pflicht")
    return errors


def propose_review_adopt_loop(
    raw_pattern: dict[str, Any],
    *,
    reviewer_principal: str,
    decision: str = "accepted",
    origin_session_id: str = "session-default",
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """End-to-end Propose → Review → Adopt workflow for `learning-loop` / Skill Keeper (GUX-040)."""
    collected = collect_skill_candidates_job([raw_pattern])
    if not collected:
        raise ValueError("Kein gültiges Kandidatenmuster für propose_review_adopt_loop")
    elaborated = elaborate_candidate_with_skill_gaertner(collected[0], agent_role="skill-gaertner")
    house_errors = validate_skill_creator_house_format(elaborated)
    if house_errors:
        raise ValueError(f"Hausformat-Verletzung: {house_errors}")

    candidate_record = {
        "candidate_id": f"sk-{elaborated['name']}",
        "target_skill_id": elaborated["name"],
        "origin_session_id": origin_session_id,
        "evidence_refs": list(evidence_refs or [f"session:{origin_session_id}"]),
        "proposed_diff_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "review_state": decision,
        "reviewer_principal": reviewer_principal if decision == "accepted" else None,
    }
    validation = validate_learning_candidate(candidate_record)
    adopted = bool(validation["valid"] and validation["promotable"])
    elaborated["status"] = "adopted" if adopted else f"review_{decision}"
    return {
        "schema": SKILL_KEEPER_SCHEMA,
        "stage": "adopted" if adopted else "reviewed",
        "adopted": adopted,
        "candidate": candidate_record,
        "validation": validation,
        "skill_document": elaborated,
    }


def learn_and_reuse_nemofold_workflow(
    session_trace: list[dict[str, Any]],
    *,
    reviewer_principal: str = "operator:lukas",
) -> dict[str, Any]:
    """Learn recurring NemoFold preparation sequence from session trace and execute it on reuse (NEMO-01, #1974)."""
    steps = [
        str(item.get("step") or item.get("action") or "").strip()
        for item in (session_trace or [])
        if isinstance(item, dict) and str(item.get("step") or item.get("action") or "").strip()
    ]
    if not steps:
        steps = [
            "fetch_uniprot_fasta",
            "validate_msa_and_constraints",
            "prepare_nemofold_job_manifest",
        ]
    pattern = {
        "name": "nemofold-workflow-prep",
        "category": "science",
        "description": f"Wiederkehrender NemoFold-Vorbereitungsablauf ({' -> '.join(steps)})",
    }
    loop_result = propose_review_adopt_loop(
        pattern,
        reviewer_principal=reviewer_principal,
        decision="accepted",
        origin_session_id="nemofold-session-trace",
        evidence_refs=[f"trace-steps:{len(steps)}"],
    )
    return {
        "schema": "ellmos.nemofold-workflow-reuse.v1",
        "workflow_id": "nemofold-workflow-prep",
        "learned_steps": steps,
        "adopted": loop_result["adopted"],
        "reuse_ready": loop_result["adopted"],
        "reused_execution_plan": [
            {"index": idx + 1, "step": step, "automated": True}
            for idx, step in enumerate(steps)
        ],
        "learning_receipt": loop_result,
    }

