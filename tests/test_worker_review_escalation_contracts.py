"""Contract tests for multi-repo worker worktree policy, configurable review policy, escalation ladder, and Bereich 6 parity."""
from __future__ import annotations

from pathlib import Path

from tools.escalation_ladder import (
    evaluate_escalation,
    project_agent_library_catalog,
    validate_learning_candidate,
    validate_persona_routing_manifest,
)
from tools.help_projection import (
    gui_showcase_and_competitor_matrix,
    pipeline_acceptance_matrix,
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
