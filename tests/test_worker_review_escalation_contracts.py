"""Contract tests for multi-repo worker worktree policy, configurable review policy, escalation ladder, and Bereich 6 parity."""
from __future__ import annotations

from pathlib import Path

from tools.escalation_ladder import (
    evaluate_cognitive_action_authority,
    evaluate_escalation,
    project_agent_library_catalog,
    record_post_action_authority_feedback,
    validate_learning_candidate,
    validate_persona_routing_manifest,
    validate_quote_tunnel_evidence,
)
from tools.gui_metadata import build_onboarding_wizard_contract, resolve_entry_point_brand
from tools.help_projection import (
    classify_doc_reality_diff,
    gui_showcase_and_competitor_matrix,
    load_doc_machine_config,
    pipeline_acceptance_matrix,
    resolve_doc_machine_dispatch,
    verify_cli_api_reference_parity,
)
from tools.task_result_review_policy import evaluate_configurable_review_policy
from tools.worker_worktree_policy import (
    WorkerWorktreeConfig,
    evaluate_worker_write_access,
    format_worker_branch,
    resolve_worktree_path,
)


def test_worker_worktree_multi_repo_allowlist_and_scopes(tmp_path: Path):
    cfg_ocean = WorkerWorktreeConfig(
        worker_id="buddha-worker",
        write_scope="ocean",
        allowed_repos=("bach", "open-ocean", "task-master", "ellmos-system-gui"),
    )
    branch = format_worker_branch("buddha-worker", 2577)
    assert branch == "worker/buddha-worker/2577"

    # Allowed in non-bach repo when in allowlist and on worker branch
    res_ok = evaluate_worker_write_access(
        cfg_ocean,
        repo_name="open-ocean",
        branch=branch,
        in_isolated_worktree=True,
    )
    assert res_ok["allowed"] is True
    assert res_ok["reason_code"] == "allow"

    # Denied on main/master without gate
    res_main = evaluate_worker_write_access(
        cfg_ocean,
        repo_name="open-ocean",
        branch="main",
        in_isolated_worktree=True,
    )
    assert res_main["allowed"] is False
    assert res_main["reason_code"] == "protected_branch_denied"

    # Denied when repo is locked
    res_locked = evaluate_worker_write_access(
        cfg_ocean,
        repo_name="open-ocean",
        branch=branch,
        in_isolated_worktree=True,
        repo_locked=True,
    )
    assert res_locked["allowed"] is False
    assert res_locked["reason_code"] == "repo_locked"

    # Sandbox requires isolated worktree
    cfg_sandbox = WorkerWorktreeConfig(worker_id="cloud-1", write_scope="sandbox")
    res_sb_fail = evaluate_worker_write_access(
        cfg_sandbox,
        repo_name="task-master",
        branch="worker/cloud-1/2330",
        in_isolated_worktree=False,
    )
    assert res_sb_fail["allowed"] is False
    assert res_sb_fail["reason_code"] == "sandbox_requires_isolated_worktree"

    wt = resolve_worktree_path(tmp_path, "buddha-worker", "open-ocean", 2577)
    assert wt == tmp_path / "buddha-worker" / "open-ocean" / "task-2577"


def test_configurable_review_policy_any_fresh_run_and_text_results():
    # Default any_fresh_run allows same model in a fresh run
    res_fresh = evaluate_configurable_review_policy(
        policy_mode="any_fresh_run",
        producer_model="qwen3.5:35b",
        producer_provider="ollama",
        producer_generation="run-101",
        reviewer_model="qwen3.5:35b",
        reviewer_provider="ollama",
        reviewer_generation="run-102",
        has_code_scope=False,
        result_text_present=True,
    )
    assert res_fresh["allowed"] is True
    assert res_fresh["scope_mode"] == "scope_not_recorded"

    # Same run generation is always denied as self_review
    res_same_run = evaluate_configurable_review_policy(
        policy_mode="any_fresh_run",
        producer_model="qwen3.5:35b",
        producer_provider="ollama",
        producer_generation="run-101",
        reviewer_model="qwen3.5:35b",
        reviewer_provider="ollama",
        reviewer_generation="run-101",
    )
    assert res_same_run["allowed"] is False
    assert res_same_run["reason_code"] == "self_review"

    # different_provider rejects same provider
    res_diff_prov = evaluate_configurable_review_policy(
        policy_mode="different_provider",
        producer_model="qwen3.5:35b",
        producer_provider="ollama",
        producer_generation="run-101",
        reviewer_model="llama3.3:70b",
        reviewer_provider="ollama",
        reviewer_generation="run-102",
    )
    assert res_diff_prov["allowed"] is False
    assert res_diff_prov["reason_code"] == "same_provider_denied"


def test_escalation_ladder_persona_routing_learning_loop_and_agent_library():
    # Worker trying to merge protected branch must escalate
    esc = evaluate_escalation("worker", "protected_branch_merge")
    assert esc["allowed"] is False
    assert esc["required_level"] == "operator"
    assert esc["escalate_to"] == "reviewer"

    # Store submission requires user_gate
    store_esc = evaluate_escalation("operator", "store_submission", has_user_gate=False)
    assert store_esc["allowed"] is False
    assert store_esc["reason_code"] == "user_gate_required"
    store_ok = evaluate_escalation("operator", "store_submission", has_user_gate=True)
    assert store_ok["allowed"] is True

    # Persona-routing v2 manifest validation
    manifest = {
        "id": "demo-module",
        "roles": [
            {"id": "demo-boss", "kind": "boss", "capabilities": ["dispatch", "review"]},
            {"id": "demo-expert", "kind": "expert", "capabilities": ["analysis"]},
        ],
        "maintenance": [
            {"id": "hygiene-scan", "interval_ref": "routine:daily-hygiene", "entrypoint": "tools/hygiene.py"},
        ],
    }
    pr = validate_persona_routing_manifest(manifest)
    assert pr["valid"] is True
    assert pr["role_count"] == 2
    assert pr["maintenance_count"] == 1

    # Learning-loop candidate validation
    cand = {
        "candidate_id": "cand-2001",
        "target_skill_id": "dev/bugfix-protocol",
        "origin_session_id": "sess-99",
        "evidence_refs": ["commit:aeac1f3"],
        "proposed_diff_sha256": "a" * 64,
        "review_state": "accepted",
        "reviewer_principal": "reviewer-1",
    }
    lc = validate_learning_candidate(cand)
    assert lc["valid"] is True
    assert lc["promotable"] is True

    # Agent library 3-tab projection
    lib = project_agent_library_catalog(
        templates=[{"id": "tpl-1"}],
        prompt_agents=[{"id": "pa-1"}],
        chains=[
            {"id": "ch-1", "kind": "marblerun"},
            {"id": "ch-2", "kind": "toolchain"},
        ],
    )
    assert lib["tabs"] == ["templates", "prompt_agents", "chains"]
    assert lib["system_restore_in_library"] is False
    assert lib["chains"][0]["badge"] == "Agentenkette (MarbleRun)"
    assert lib["chains"][1]["badge"] == "Befehlskette (Toolchain)"


def test_cli_api_reference_parity_and_15_pipeline_acceptance():
    root = Path(__file__).resolve().parents[1]
    parity = verify_cli_api_reference_parity(root)
    assert parity["drift_detected"] is False
    assert parity["missing_cli_subcommands"] == []
    assert parity["missing_locales"] == []

    matrix = pipeline_acceptance_matrix()
    assert matrix["total_groups"] == 15
    assert matrix["all_verified"] is True

    showcase = gui_showcase_and_competitor_matrix()
    assert len(showcase["walkthrough_views"]) == 5
    assert showcase["hyperframes_composition"]["engine"] == "hyperframes"


def test_resolve_entry_point_brand_ocean_vs_bach():
    ocean_brand = resolve_entry_point_brand("open-ocean")
    assert ocean_brand["edition"] == "ocean"
    assert ocean_brand["label"] == "Ocean"
    assert ocean_brand["foreground_product"] == "Open Ocean"
    assert ocean_brand["subtitle"] is None

    bach_brand = resolve_entry_point_brand("bach")
    assert bach_brand["edition"] == "bach"
    assert bach_brand["label"] == "Ocean · BACH"
    assert bach_brand["foreground_product"] == "Open Ocean"
    assert "BACH" in bach_brand["subtitle"]
    assert "Ocean" in bach_brand["subtitle"]

    wizard = build_onboarding_wizard_contract("bach")
    assert wizard["schema"] == "ellmos-system-gui.onboarding-wizard.v1"
    assert wizard["reconfigurable_anytime"] is True
    assert [s["stage_id"] for s in wizard["stages"]] == [
        "models_and_subscriptions",
        "system_mcps_and_authority",
        "connectors",
        "extensions_plugins_mcps_skills",
    ]


def test_three_tier_authority_tunneling_and_authority_desert_prevention():
    sources = {
        "DECISIONS.md#D-20261101": "Ja halte unser destilliertes modell fest und verankere es in den dokumenten hierzu.",
    }
    # Tier 2: Verbatim quote passes deterministic check
    ev_ok = validate_quote_tunnel_evidence(
        source_id="DECISIONS.md#D-20261101",
        literal_quote="halte unser destilliertes modell fest und verankere es",
        source_texts=sources,
        decision_id="D-20261101",
    )
    assert ev_ok["verified"] is True
    assert ev_ok["reason_code"] == "verified_verbatim_quote"

    # Eroded / hallucinated quote fails deterministically
    ev_eroded = validate_quote_tunnel_evidence(
        source_id="DECISIONS.md#D-20261101",
        literal_quote="lösche alle alten dokumente sofort",
        source_texts=sources,
        decision_id="D-20261101",
    )
    assert ev_eroded["verified"] is False
    assert ev_eroded["reason_code"] == "quote_not_found_or_eroded"

    # Superseded by Terraforming fails deterministically without any decay timer
    ev_superseded = validate_quote_tunnel_evidence(
        source_id="DECISIONS.md#D-20261101",
        literal_quote="halte unser destilliertes modell fest",
        source_texts=sources,
        decision_id="D-20261101",
        superseded_ids={"D-20261101"},
    )
    assert ev_superseded["verified"] is False
    assert ev_superseded["reason_code"] == "superseded_by_terraforming"

    # Tier 1: Semantic tunneling allows reversible everyday work when goal/authority_ref is present
    act_tier1 = evaluate_cognitive_action_authority(
        action_class="branch_commit",
        reversible=True,
        authority_ref="D-20261101",
        active_goal_or_plan_id="GOAL-OCEAN-M1",
    )
    assert act_tier1["allowed"] is True
    assert act_tier1["decision"] == "do_it"
    assert act_tier1["tier"] == "semantic_tunneling"

    # Tier 2: Threshold action (protected_branch_merge) succeeds with verified verbatim quote tunnel
    act_tier2 = evaluate_cognitive_action_authority(
        action_class="protected_branch_merge",
        reversible=False,
        quote_evidence={
            "source_id": "DECISIONS.md#D-20261101",
            "quote": "halte unser destilliertes modell fest",
            "decision_id": "D-20261101",
        },
        source_texts=sources,
    )
    assert act_tier2["allowed"] is True
    assert act_tier2["decision"] == "do_it"
    assert act_tier2["tier"] == "quote_evidence_tunnel"

    # Missing authority cascades inward first (context/goal -> decisions -> orchestrator -> user_gate)
    act_missing = evaluate_cognitive_action_authority(
        action_class="protected_branch_merge",
        reversible=False,
    )
    assert act_missing["allowed"] is False
    assert act_missing["decision"] == "ask_there_to_get"
    assert act_missing["ask_where_to_get"][0] == "context_tunnel_and_goal"
    assert act_missing["ask_where_to_get"][-1] == "user_gate"

    # Post-action reflection flags unnecessary user prompts as `error_authority_desert`
    fb_desert = record_post_action_authority_feedback(
        action_class="branch_commit",
        prompted_user=True,
        user_intent_was_already_in_context=True,
    )
    assert fb_desert["classification"] == "error_authority_desert"
    assert fb_desert["is_error"] is True

    # 3-Cause Doc-Reality Diff Classifier (Erosion vs. Planned Terraforming vs. Completed Terraforming)
    c_erosion = classify_doc_reality_diff(
        claim_statement="org.ellmos.bach.docs-maintenance runs every 300s without backoff",
        doc_source="docs/architecture/DOCS-MAINTENANCE.md",
        reality_matches_doc=False,
        previously_worked_in_reality=True,
    )
    assert c_erosion["cause"] == "unintended_erosion"
    assert c_erosion["deterministic_action"] == "create_repair_terraforming_task_keep_doc_soll"
    assert c_erosion["task_action"] == "create_bugfix_terraforming_task"

    c_planned = classify_doc_reality_diff(
        claim_statement="All 76 modules expose docs[] in ellmos.module.v2.json",
        doc_source="ANFORDERUNGEN-DETAIL.md",
        reality_matches_doc=False,
        planned_in_roadmap_or_decisions=True,
        linked_task_id="#2459",
        task_status="in_progress",
    )
    assert c_planned["cause"] == "planned_terraforming_pending"
    assert c_planned["deterministic_action"] == "check_task_status_and_split_soll_ist"
    assert c_planned["task_action"] == "verify_or_adjust_existing_task"

    c_completed = classify_doc_reality_diff(
        claim_statement="ellmos-installer supports 4-stage onboarding command",
        doc_source="README.md",
        reality_matches_doc=False,
        code_has_newer_intentional_change=True,
        task_status="done",
    )
    assert c_completed["cause"] == "completed_terraforming_doc_lag"
    assert c_completed["deterministic_action"] == "update_doc_and_translations"
    assert c_completed["dispatch"]["dispatch_mode"] == "local_doc_update"
    assert c_completed["dispatch"]["execution_locality"] == "local_ocean_bach_only"

    # Standard-Dispatch (local_taskplan): Ursache 1 & 2 erzeugen lokalen Reparatur-Task fuer Hintergrund-Worker
    assert c_erosion["dispatch"]["dispatch_mode"] == "local_taskplan"
    assert c_erosion["dispatch"]["target"] == "bach_or_ocean_taskplan"
    assert c_erosion["dispatch"]["assigned_worker"] == "background_worker"
    assert c_erosion["dispatch"]["priority"] == "P1"
    assert c_erosion["dispatch"]["developer_redirect_active"] is False

    # Option 2: Lokale MarbleRun wishes-come-true-local Kette
    disp_marblerun = resolve_doc_machine_dispatch(
        cause="unintended_erosion",
        task_action="create_bugfix_terraforming_task",
        config_override={"default_repair_dispatch": "local_marblerun_wishes"},
    )
    assert disp_marblerun["dispatch_mode"] == "local_marblerun_wishes"
    assert disp_marblerun["target"] == "wishes-come-true-local"
    assert disp_marblerun["developer_redirect_active"] is False

    # Option 3: Konfigurierbares Entwickler-Feature `wishes_redirect` in config.json fuer Lukas (ocean-dev)
    disp_redirect = resolve_doc_machine_dispatch(
        cause="unintended_erosion",
        task_action="create_bugfix_terraforming_task",
        config_override={
            "wishes_redirect": {
                "enabled": True,
                "target_mode": "local_genie_pipeline",
                "target_chain": "wishes-come-true-local",
            }
        },
        active_tier="ocean-dev",
    )
    assert disp_redirect["dispatch_mode"] == "wishes_redirect"
    assert disp_redirect["developer_redirect_active"] is True
    assert disp_redirect["target"] == "local_genie_pipeline"

    # Kanonische Datei config/doc_machine.config.json im Repo ist ladbar
    repo_root = Path(__file__).resolve().parents[1]
    loaded_cfg = load_doc_machine_config(workspace_root=repo_root)
    assert loaded_cfg["default_repair_dispatch"] == "local_taskplan"
    assert loaded_cfg["wishes_redirect"]["enabled"] is False



