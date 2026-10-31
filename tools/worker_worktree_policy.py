"""Multi-repository worker worktree policy, write scopes, and commit-policy gates (#2577, #2330, #3682-#3697, #2245).

Replaces the legacy BACH-only worker directory check with a configurable repository
allowlist (`allowed_repos`), explicit write scopes (`sandbox`, `ocean`, `free`),
and branch/commit hygiene (`worker/<agent>/<task-id>`) for background and cloud workers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

POLICY_SCHEMA = "ellmos.worker-worktree-policy.v1"
WRITE_SCOPES = ("sandbox", "ocean", "free")
DEFAULT_ALLOWED_REPOS = (
    "bach",
    "open-ocean",
    "ocean-resources",
    "task-master",
    "ellmos-system-gui",
    "ellmos-unified-gui",
    "ellmos-development-system",
    "ellmos-filecommander-mcp",
    "ellmos-tray",
    "foerderplaner",
    "web-scraper",
)
PROTECTED_BRANCHES = frozenset({"main", "master", "production", "release"})
WORKER_BRANCH_RE = re.compile(r"^worker/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True)
class WorkerWorktreeConfig:
    """Configuration for a worker's repository allowlist and write scope."""

    worker_id: str
    write_scope: str = "ocean"
    allowed_repos: tuple[str, ...] = DEFAULT_ALLOWED_REPOS
    allow_direct_protected_branch: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, str) or not self.worker_id.strip():
            raise ValueError("worker_id must be a non-empty string")
        if self.write_scope not in WRITE_SCOPES:
            raise ValueError(f"write_scope must be one of {WRITE_SCOPES}")
        if not isinstance(self.allowed_repos, tuple) or not self.allowed_repos:
            raise ValueError("allowed_repos must be a non-empty tuple")
        for repo in self.allowed_repos:
            if not isinstance(repo, str) or REPO_NAME_RE.fullmatch(repo) is None:
                raise ValueError(f"invalid repository name in allowlist: {repo!r}")


def format_worker_branch(worker_id: str, task_id: int | str) -> str:
    """Return canonical worker branch name `worker/<agent>/<task-id>`."""
    clean_worker = re.sub(r"[^A-Za-z0-9._-]", "-", str(worker_id).strip())
    clean_task = re.sub(r"[^A-Za-z0-9._-]", "-", str(task_id).strip())
    branch = f"worker/{clean_worker}/{clean_task}"
    if WORKER_BRANCH_RE.fullmatch(branch) is None:
        raise ValueError(f"cannot construct valid worker branch from {worker_id!r}, {task_id!r}")
    return branch


def evaluate_worker_write_access(
    config: WorkerWorktreeConfig,
    *,
    repo_name: str,
    branch: str,
    in_isolated_worktree: bool,
    repo_locked: bool = False,
    has_active_lease: bool = True,
) -> dict[str, Any]:
    """Evaluate whether a worker may write/commit in the target repository and branch."""
    if repo_locked:
        return {
            "schema": POLICY_SCHEMA,
            "allowed": False,
            "reason_code": "repo_locked",
            "write_scope": config.write_scope,
            "repo_name": repo_name,
        }
    if not has_active_lease:
        return {
            "schema": POLICY_SCHEMA,
            "allowed": False,
            "reason_code": "lease_missing",
            "write_scope": config.write_scope,
            "repo_name": repo_name,
        }
    allowed_set = {r.casefold() for r in config.allowed_repos}
    if repo_name.strip().casefold() not in allowed_set:
        return {
            "schema": POLICY_SCHEMA,
            "allowed": False,
            "reason_code": "repo_not_in_allowlist",
            "write_scope": config.write_scope,
            "repo_name": repo_name,
        }

    branch_clean = branch.strip()
    is_protected = branch_clean.casefold() in PROTECTED_BRANCHES

    if config.write_scope == "sandbox":
        if not in_isolated_worktree:
            return {
                "schema": POLICY_SCHEMA,
                "allowed": False,
                "reason_code": "sandbox_requires_isolated_worktree",
                "write_scope": config.write_scope,
                "repo_name": repo_name,
            }
        if is_protected:
            return {
                "schema": POLICY_SCHEMA,
                "allowed": False,
                "reason_code": "protected_branch_denied",
                "write_scope": config.write_scope,
                "repo_name": repo_name,
            }
    elif config.write_scope == "ocean":
        if is_protected and not config.allow_direct_protected_branch:
            return {
                "schema": POLICY_SCHEMA,
                "allowed": False,
                "reason_code": "protected_branch_denied",
                "write_scope": config.write_scope,
                "repo_name": repo_name,
            }
        if not is_protected and WORKER_BRANCH_RE.fullmatch(branch_clean) is None:
            return {
                "schema": POLICY_SCHEMA,
                "allowed": False,
                "reason_code": "invalid_worker_branch_name",
                "write_scope": config.write_scope,
                "repo_name": repo_name,
            }
    elif config.write_scope == "free":
        if is_protected and not config.allow_direct_protected_branch:
            return {
                "schema": POLICY_SCHEMA,
                "allowed": False,
                "reason_code": "protected_branch_requires_gate",
                "write_scope": config.write_scope,
                "repo_name": repo_name,
            }

    return {
        "schema": POLICY_SCHEMA,
        "allowed": True,
        "reason_code": "allow",
        "write_scope": config.write_scope,
        "repo_name": repo_name,
        "branch": branch_clean,
    }


def resolve_worktree_path(
    worktree_root: Path,
    worker_id: str,
    repo_name: str,
    task_id: int | str,
) -> Path:
    """Return deterministic isolated worktree path for any Ocean module repository."""
    if REPO_NAME_RE.fullmatch(repo_name) is None:
        raise ValueError(f"invalid repo_name: {repo_name!r}")
    clean_worker = re.sub(r"[^A-Za-z0-9._-]", "-", str(worker_id).strip())
    clean_task = re.sub(r"[^A-Za-z0-9._-]", "-", str(task_id).strip())
    return Path(worktree_root) / clean_worker / repo_name / f"task-{clean_task}"
