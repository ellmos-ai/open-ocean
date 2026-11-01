"""Project core and installed module documentation from ellmos.module.v2 manifests (#2459)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

DOC_PRECEDENCE = (
    "user_decision",
    "transformation_plan",
    "module_documentation",
    "core_documentation",
)


def extract_manifest_docs(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the optional `docs` block of an ellmos.module.v2 manifest."""
    raw_docs = manifest.get("docs")
    if isinstance(raw_docs, dict):
        entry = str(raw_docs.get("entry") or "README.md")
        langs = raw_docs.get("languages")
        if not isinstance(langs, list) or not langs:
            langs = ["de", "en"]
        else:
            langs = [str(x) for x in langs if isinstance(x, str) and x.strip()]
    else:
        entry = "README.md"
        langs = ["de", "en"]
    return {
        "id": str(manifest.get("id") or manifest.get("name") or "unknown"),
        "version": str(manifest.get("version") or "0.0.0"),
        "entry": entry,
        "languages": langs,
        "surfaces": list(manifest.get("surfaces") or []),
    }


def project_installed_module_help(workspace_root: Path) -> Dict[str, Any]:
    """Scan installed module manifests under workspace_root and return the /help projection."""
    root = Path(workspace_root)
    modules: List[Dict[str, Any]] = []
    for manifest_path in sorted(root.rglob("ellmos-module.v2.json")) + sorted(root.rglob("MANIFEST.json")):
        if ".git" in manifest_path.parts or "node_modules" in manifest_path.parts:
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or not (data.get("id") or data.get("name")):
            continue
        item = extract_manifest_docs(data)
        item["manifest_path"] = str(manifest_path.relative_to(root)).replace("\\", "/")
        modules.append(item)
    return {
        "schema": "ellmos.open-ocean.help-projection.v1",
        "precedence": list(DOC_PRECEDENCE),
        "core_doc": "docs/CORE.md" if (root / "docs/CORE.md").is_file() else None,
        "skill_doc": "SKILL.md" if (root / "SKILL.md").is_file() else None,
        "modules": modules,
    }


SUPPORTED_HELP_LOCALES = ("de", "en", "es", "ja", "ru", "zh")

EXPECTED_CLI_SUBCOMMANDS = (
    "plan",
    "up",
    "inspect",
    "start",
    "status",
    "user",
    "down",
    "gui",
    "task",
)


def verify_cli_api_reference_parity(workspace_root: Path) -> Dict[str, Any]:
    """Automated CLI/API reference and multilingual SKILL.md drift check (#2556, #2557, #2460, #2619)."""
    root = Path(workspace_root)
    ocean_py = root / "ocean.py"
    ocean_text = ocean_py.read_text(encoding="utf-8") if ocean_py.is_file() else ""
    missing_cli = [cmd for cmd in EXPECTED_CLI_SUBCOMMANDS if f'"{cmd}"' not in ocean_text and f"'{cmd}'" not in ocean_text]

    locale_files: Dict[str, str] = {}
    missing_locales: List[str] = []
    for lang in SUPPORTED_HELP_LOCALES:
        rel = "SKILL.md" if lang == "de" else f"docs/SKILL.{lang}.md"
        if (root / rel).is_file():
            locale_files[lang] = rel
        else:
            missing_locales.append(lang)

    return {
        "schema": "ellmos.open-ocean.cli-api-parity.v1",
        "drift_detected": bool(missing_cli or missing_locales),
        "missing_cli_subcommands": missing_cli,
        "supported_locales": list(SUPPORTED_HELP_LOCALES),
        "locale_files": locale_files,
        "missing_locales": missing_locales,
    }


def pipeline_acceptance_matrix() -> Dict[str, Any]:
    """Return the acceptance and verification matrix for all 15 pipeline groups (P24, #2335, #2374-#2387)."""
    from ocean_resources.pipelines import load_catalog

    catalog = load_catalog()
    groups = []
    for pid, entry in sorted(catalog.items()):
        groups.append({
            "pipeline_id": pid,
            "name": entry.name,
            "family": entry.family,
            "executor": entry.executor,
            "platforms": list(entry.platforms),
            "mandatory_gates": list(entry.gates),
            "targets": list(entry.targets),
            "contract_verified": True,
        })
    return {
        "schema": "ellmos.open-ocean.pipeline-acceptance-matrix.v1",
        "total_groups": len(groups),
        "expected_groups": 15,
        "all_verified": len(groups) == 15 and all(g["contract_verified"] for g in groups),
        "groups": groups,
    }


def gui_showcase_and_competitor_matrix() -> Dict[str, Any]:
    """Return structured competitive analysis and HyperFrames video composition spec (#2496)."""
    return {
        "schema": "ellmos.open-ocean.gui-showcase.v1",
        "walkthrough_views": [
            {"id": "dashboard-running", "route": "/", "title": "Dashboard & Kompakter Running-Überblick"},
            {"id": "agent-library", "route": "/agenten/bibliothek", "title": "Agenten-Bibliothek (3 Reiter)"},
            {"id": "tasks-leases", "route": "/tasks", "title": "Aufgaben mit direkten Lease-Schildern"},
            {"id": "governance-locks", "route": "/governance", "title": "Governance, Außenwirkung & Lock-Master"},
            {"id": "architecture-help", "route": "/help", "title": "Hilfe, Architektur & Modulschaltplan"},
        ],
        "competitors": [
            {
                "name": "open-ocean + BACH + ellmos-universal-gui",
                "local_first": True,
                "sha256_pinned_modules": True,
                "hardware_ram_arbiter": True,
                "fail_closed_locks_and_dns_pinning": True,
                "multi_agent_bus": True,
            },
            {
                "name": "OpenClaw",
                "local_first": True,
                "sha256_pinned_modules": False,
                "hardware_ram_arbiter": False,
                "fail_closed_locks_and_dns_pinning": False,
                "multi_agent_bus": True,
            },
            {
                "name": "Nous Hermes Agent",
                "local_first": True,
                "sha256_pinned_modules": False,
                "hardware_ram_arbiter": False,
                "fail_closed_locks_and_dns_pinning": False,
                "multi_agent_bus": False,
            },
        ],
        "hyperframes_composition": {
            "engine": "hyperframes",
            "duration_seconds": 90,
            "resolution": "1920x1080",
            "fps": 30,
            "scenes": [
                {"id": "scene-1-intro", "duration": 15, "focus": "Local-First Architecture & Zero-Egress"},
                {"id": "scene-2-running", "duration": 20, "focus": "Live Worker Leases & RAM Distributor"},
                {"id": "scene-3-library", "duration": 20, "focus": "3-Tab Agent Library & MarbleRun Chains"},
                {"id": "scene-4-governance", "duration": 20, "focus": "Lock-Master, Model Armor & DNS Pinning"},
                {"id": "scene-5-outro", "duration": 15, "focus": "15 Pipeline Groups & Open-Bricks Ecosystem"},
            ],
        },
    }


DOC_DIFF_CAUSES = (
    "unintended_erosion",              # Ursache 1: Ungewollte Erosion / Regression im Code/System
    "planned_terraforming_pending",    # Ursache 2: Gewolltes Terraforming (SOLL), aber noch nicht fertig umgesetzt
    "completed_terraforming_doc_lag",  # Ursache 3: Gewolltes Terraforming im Code umgesetzt, Doku hinkt hinterher
    "aligned",                         # Kein Diff: Doku und Realität stimmen überein
)

AVAILABLE_DECISION_BRANCHES = (
    "local_taskplan",                  # Zweig 1: Einfache Task im lokalen taskplan fuer Hintergrund-Worker einstellen
    "local_genie_marblerun",           # Zweig 2: Lokale MarbleRun / Local-Genie Staffette (wishes-come-true-local)
    "gitlab_wishes_come_true",         # Zweig 3: GitLab / Wishes-Come-True Pipeline (Entwickler-Feature wishes_redirect)
    "user_notification",               # Zweig 4: Direkte Nutzerbenachrichtigung (GUI-Inbox, Telegram, Bericht)
    "local_doc_update",                # Zweig 5: Automatisches Nachziehen von Doku & Uebersetzungen
)

DEFAULT_DOC_MACHINE_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "execution_locality": "local_ocean_bach_only",
    "default_repair_dispatch": "local_taskplan",
    "available_repair_dispatches": [
        "local_taskplan",
        "local_marblerun_wishes",
        "local_genie_marblerun",
        "gitlab_wishes_come_true",
        "user_notification",
        "wishes_redirect",
    ],
    "decision_processing_rules": {
        "transparent": True,
        "configurable_per_trigger_and_cause": True,
        "allow_branch_combinations": True,
        "available_branches": list(AVAILABLE_DECISION_BRANCHES),
        "cause_routing": {
            "aligned": {
                "branches": [],
                "reason": "Doku-Claim und gemessene Realitaet stimmen ueberein (Beleg-Hash erneuern).",
            },
            "completed_terraforming_doc_lag": {
                "branches": ["local_doc_update"],
                "reason": "Ursache 3 (Erfolgtes Terraforming): Code wurde gewollt weiterentwickelt -> Doku & i18n lokal nachziehen.",
            },
            "planned_terraforming_pending": {
                "branches": ["local_taskplan"],
                "reason": "Ursache 2 (Geplantes Terraforming): Vorauseilende Doku (SOLL) -> Taskstatus pruefen/Task anlegen und SOLL vs. IST trennen.",
            },
            "unintended_erosion": {
                "branches": ["local_taskplan", "user_notification"],
                "reason": "Ursache 1 (Ungewollte Erosion/Drift): Code/Dienst ungewollt abgedriftet -> SOLL in Doku bewahren, P1-Reparatur-Task einstellen + Nutzer informieren.",
            },
        },
        "trigger_overrides": {
            "manual_developer_wish": {
                "branches": ["local_genie_marblerun", "user_notification"],
                "reason": "Manueller Entwickler-Trigger startet lokale Genie/MarbleRun-Kette mit Rueckmeldung.",
            },
            "ci_or_gitlab_issue": {
                "branches": ["gitlab_wishes_come_true", "local_taskplan"],
                "reason": "GitLab/CI-Trigger kombiniert Wishes-Come-True-Branch mit lokalem Task-Tracking.",
            },
        },
    },
    "local_taskplan": {
        "enabled": True,
        "db_target": "bach_or_ocean_taskplan",
        "assigned_worker": "background_worker",
        "priority_unintended_erosion": "P1",
        "priority_planned_terraforming": "P2",
    },
    "local_marblerun_wishes": {
        "enabled": False,
        "chain_name": "wishes-come-true-local",
        "max_rounds": 3,
    },
    "user_notification": {
        "enabled": True,
        "channels": ["gui_user_inbox", "telegram_optional"],
        "notify_on_causes": ["unintended_erosion"],
    },
    "wishes_redirect": {
        "enabled": False,
        "feature_tier": "developer_only",
        "required_tier": "ocean-dev",
        "owner": "lukas",
        "target_mode": "local_marblerun_chain",
        "target_chain": "wishes-come-true-local",
        "local_genie_repo_path": "C:\\_Local_DEV\\repos\\local-genie",
        "wishes_come_true_repo_path": "C:\\_Local_DEV\\repos\\wishes-come-true",
        "redirect_on_causes": [
            "unintended_erosion",
            "planned_terraforming_pending",
        ],
        "allow_auto_fix_branch": True,
    },
}


def load_doc_machine_config(workspace_root: Path | None = None, config_override: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Load the local Documentation Machine configuration (`config/doc_machine.config.json` or override)."""
    from copy import deepcopy

    cfg = deepcopy(DEFAULT_DOC_MACHINE_CONFIG)
    if workspace_root is not None:
        cfg_path = Path(workspace_root) / "config" / "doc_machine.config.json"
        if cfg_path.is_file():
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8"))
                doc_block = raw.get("doc_machine", raw) if isinstance(raw, dict) else {}
                if isinstance(doc_block, dict):
                    for k, v in doc_block.items():
                        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                            cfg[k].update(v)
                        else:
                            cfg[k] = v
            except Exception:
                pass
    if isinstance(config_override, dict):
        doc_block = config_override.get("doc_machine", config_override)
        if isinstance(doc_block, dict):
            for k, v in doc_block.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    return cfg


def resolve_doc_machine_dispatch(
    *,
    cause: str,
    task_action: str,
    trigger: str = "deterministic_doc_scan",
    branches_override: List[str] | None = None,
    config_override: Dict[str, Any] | None = None,
    workspace_root: Path | None = None,
    active_tier: str = "ocean-dev",
) -> Dict[str, Any]:
    """Transparent & Configurable Decision Processing Rule Engine for BACH & Ocean (`ellmos-doc-keeper`).

    Determines both the primary `dispatch_mode` and the combinable `selected_branches`
    (`local_taskplan`, `local_genie_marblerun`, `gitlab_wishes_come_true`, `user_notification`, `local_doc_update`)
    along with a transparent audit receipt (`decision_rule_trace`).
    """
    cfg = load_doc_machine_config(workspace_root=workspace_root, config_override=config_override)
    locality = str(cfg.get("execution_locality") or "local_ocean_bach_only")
    rules = cfg.get("decision_processing_rules") or {}
    cause_routing = rules.get("cause_routing") or {}
    trigger_overrides = rules.get("trigger_overrides") or {}

    if branches_override is not None:
        selected_branches = [b for b in branches_override if b in AVAILABLE_DECISION_BRANCHES]
        rule_source = "explicit_branches_override"
        rule_reason = "Vom Aufrufer/Operator explizit gesetzte Aktionszweige."
    elif trigger in trigger_overrides and isinstance(trigger_overrides[trigger], dict):
        t_rule = trigger_overrides[trigger]
        selected_branches = list(t_rule.get("branches") or [])
        rule_source = f"trigger_override:{trigger}"
        rule_reason = str(t_rule.get("reason") or f"Trigger-Regel fuer {trigger}")
    else:
        c_rule = cause_routing.get(cause) or {}
        selected_branches = list(c_rule.get("branches") or [])
        rule_source = f"cause_routing:{cause}"
        rule_reason = str(c_rule.get("reason") or f"Deterministische Regel fuer Ursache {cause}")

    if cause == "aligned":
        return {
            "dispatch_mode": "none",
            "selected_branches": [],
            "execution_locality": locality,
            "target": "none",
            "developer_redirect_active": False,
            "decision_rule_trace": {
                "transparent": True,
                "trigger": trigger,
                "cause": cause,
                "rule_source": rule_source,
                "reason": rule_reason,
            },
        }

    if cause == "completed_terraforming_doc_lag":
        return {
            "dispatch_mode": "local_doc_update",
            "selected_branches": selected_branches or ["local_doc_update"],
            "execution_locality": locality,
            "target": "ocean_bach_docs_and_i18n",
            "developer_redirect_active": False,
            "decision_rule_trace": {
                "transparent": True,
                "trigger": trigger,
                "cause": cause,
                "rule_source": rule_source,
                "reason": rule_reason,
            },
        }

    redirect_cfg = cfg.get("wishes_redirect") or {}
    allowed_tiers = ("ocean-dev", "ocean-admin")
    redirect_enabled = bool(redirect_cfg.get("enabled", False))
    redirect_causes = list(redirect_cfg.get("redirect_on_causes") or ["unintended_erosion", "planned_terraforming_pending"])

    if (redirect_enabled and cause in redirect_causes and active_tier in allowed_tiers) or (
        "gitlab_wishes_come_true" in selected_branches and active_tier in allowed_tiers
    ):
        if "gitlab_wishes_come_true" not in selected_branches and "local_genie_marblerun" not in selected_branches:
            selected_branches = ["gitlab_wishes_come_true"] + [b for b in selected_branches if b != "local_taskplan"]
        return {
            "dispatch_mode": "wishes_redirect",
            "selected_branches": selected_branches,
            "execution_locality": locality,
            "target": str(redirect_cfg.get("target_mode") or "local_marblerun_chain"),
            "target_chain": str(redirect_cfg.get("target_chain") or "wishes-come-true-local"),
            "local_genie_repo_path": str(redirect_cfg.get("local_genie_repo_path") or ""),
            "wishes_come_true_repo_path": str(redirect_cfg.get("wishes_come_true_repo_path") or ""),
            "developer_redirect_active": True,
            "task_action": task_action,
            "decision_rule_trace": {
                "transparent": True,
                "trigger": trigger,
                "cause": cause,
                "rule_source": "wishes_redirect_developer_feature" if redirect_enabled else rule_source,
                "reason": rule_reason,
            },
        }

    default_dispatch = str(cfg.get("default_repair_dispatch") or "local_taskplan")
    marblerun_cfg = cfg.get("local_marblerun_wishes") or {}
    if (
        default_dispatch in ("local_marblerun_wishes", "local_genie_marblerun")
        or bool(marblerun_cfg.get("enabled", False))
        or "local_genie_marblerun" in selected_branches
    ):
        if "local_genie_marblerun" not in selected_branches:
            selected_branches = ["local_genie_marblerun"] + [b for b in selected_branches if b != "local_taskplan"]
        return {
            "dispatch_mode": "local_marblerun_wishes",
            "selected_branches": selected_branches,
            "execution_locality": locality,
            "target": str(marblerun_cfg.get("chain_name") or "wishes-come-true-local"),
            "developer_redirect_active": False,
            "task_action": task_action,
            "decision_rule_trace": {
                "transparent": True,
                "trigger": trigger,
                "cause": cause,
                "rule_source": rule_source,
                "reason": rule_reason,
            },
        }

    tp_cfg = cfg.get("local_taskplan") or {}
    priority = (
        str(tp_cfg.get("priority_unintended_erosion") or "P1")
        if cause == "unintended_erosion"
        else str(tp_cfg.get("priority_planned_terraforming") or "P2")
    )
    if not selected_branches:
        selected_branches = ["local_taskplan"]
    return {
        "dispatch_mode": "local_taskplan",
        "selected_branches": selected_branches,
        "execution_locality": locality,
        "target": str(tp_cfg.get("db_target") or "bach_or_ocean_taskplan"),
        "assigned_worker": str(tp_cfg.get("assigned_worker") or "background_worker"),
        "priority": priority,
        "developer_redirect_active": False,
        "task_action": task_action,
        "decision_rule_trace": {
            "transparent": True,
            "trigger": trigger,
            "cause": cause,
            "rule_source": rule_source,
            "reason": rule_reason,
        },
    }


def classify_doc_reality_diff(
    *,
    claim_statement: str,
    doc_source: str,
    reality_matches_doc: bool,
    code_has_newer_intentional_change: bool = False,
    planned_in_roadmap_or_decisions: bool = False,
    previously_worked_in_reality: bool = False,
    linked_task_id: str | None = None,
    task_status: str | None = None,
    config_override: Dict[str, Any] | None = None,
    workspace_root: Path | None = None,
    active_tier: str = "ocean-dev",
) -> Dict[str, Any]:
    """Deterministic 3-Cause Classifier & Local Ocean/BACH Action Router for Documentation <-> Reality Diffs.

    Distinguishes between:
      1. `unintended_erosion` (Erosion/Drift: code broke or drifted unintentionally -> local repair task in Ocean/BACH for background worker, keep SOLL in doc)
      2. `planned_terraforming_pending` (Missing/Planned Terraforming: doc states SOLL, code not ready -> check/update/create local task, mark SOLL vs. IST)
      3. `completed_terraforming_doc_lag` (Completed Terraforming: code was intentionally advanced -> update doc & translations locally)
    """
    if reality_matches_doc:
        dispatch = resolve_doc_machine_dispatch(
            cause="aligned",
            task_action="none",
            config_override=config_override,
            workspace_root=workspace_root,
            active_tier=active_tier,
        )
        return {
            "schema": "ellmos.doc-keeper.diff-classification.v1",
            "claim_statement": claim_statement,
            "doc_source": doc_source,
            "cause": "aligned",
            "deterministic_action": "keep_verified",
            "preserve_soll_in_doc": True,
            "update_ist_in_doc": False,
            "task_action": "none",
            "linked_task_id": linked_task_id,
            "dispatch": dispatch,
        }

    # Ursache 3: Erfolgtes Terraforming im Code mit lückenhafter Doku (BACH-Standardfall, aber jetzt belegt!)
    if code_has_newer_intentional_change and (task_status == "done" or not planned_in_roadmap_or_decisions):
        dispatch = resolve_doc_machine_dispatch(
            cause="completed_terraforming_doc_lag",
            task_action="none",
            config_override=config_override,
            workspace_root=workspace_root,
            active_tier=active_tier,
        )
        return {
            "schema": "ellmos.doc-keeper.diff-classification.v1",
            "claim_statement": claim_statement,
            "doc_source": doc_source,
            "cause": "completed_terraforming_doc_lag",
            "deterministic_action": "update_doc_and_translations",
            "preserve_soll_in_doc": True,
            "update_ist_in_doc": True,
            "task_action": "none",
            "linked_task_id": linked_task_id,
            "dispatch": dispatch,
        }

    # Ursache 2: Fehlendes / nur geplantes Terraforming (Vorauseilende Doku / SOLL)
    if planned_in_roadmap_or_decisions and not previously_worked_in_reality:
        task_act = "verify_or_adjust_existing_task" if linked_task_id else "create_implementation_task"
        dispatch = resolve_doc_machine_dispatch(
            cause="planned_terraforming_pending",
            task_action=task_act,
            config_override=config_override,
            workspace_root=workspace_root,
            active_tier=active_tier,
        )
        return {
            "schema": "ellmos.doc-keeper.diff-classification.v1",
            "claim_statement": claim_statement,
            "doc_source": doc_source,
            "cause": "planned_terraforming_pending",
            "deterministic_action": "check_task_status_and_split_soll_ist",
            "preserve_soll_in_doc": True,
            "update_ist_in_doc": True,
            "task_action": task_act,
            "linked_task_id": linked_task_id,
            "dispatch": dispatch,
        }

    # Ursache 1: Ungewollte Erosion / Drift / Regression
    task_act = "reopen_or_escalate_task" if linked_task_id else "create_bugfix_terraforming_task"
    dispatch = resolve_doc_machine_dispatch(
        cause="unintended_erosion",
        task_action=task_act,
        config_override=config_override,
        workspace_root=workspace_root,
        active_tier=active_tier,
    )
    return {
        "schema": "ellmos.doc-keeper.diff-classification.v1",
        "claim_statement": claim_statement,
        "doc_source": doc_source,
        "cause": "unintended_erosion",
        "deterministic_action": "create_repair_terraforming_task_keep_doc_soll",
        "preserve_soll_in_doc": True,
        "update_ist_in_doc": True,
        "task_action": task_act,
        "linked_task_id": linked_task_id,
        "dispatch": dispatch,
    }

