"""Fetch + Place for `module:` components (architecture/INSTALLER-TARGET.md).

Pattern PORTED from sovereign-private's pilot installer
(_dev/pilot/install_sovereign.py:install_module / git_clone), not imported --
open-ocean has no dependency on that repository, and the port deliberately
drops one behaviour: install_sovereign.py's git_clone() falls BACK to the
default branch when the pinned `--branch <ref>` does not exist, so a broken
pin still produces a "successful" clone of the wrong commit
(INSTALLER-REUSE-BEFUND_2026-08-07.md Sec. 5.4). This module never does that:
a pin that is not a full 40-hex commit SHA is refused before any git command
runs (status "unpinnable"), and any git failure after that point removes
whatever partial directory it created rather than leaving it checked out on
whatever `git fetch` happened to land on.

Scope, updated 2026-08-19: at the time this module was first written, the
catalog carried no SHA pins at all -- `version` on every git-repository module
was a semver string ("0.1.0" etc.), not a commit hash, so "unpinnable" was the
correct, honest outcome for every Ring 1 module. `.MODULES/_scripts/
build_catalog.py` now computes a separate, builder-owned `commit_sha` field
(13/22 current git-repository modules pinned, including Ring 1's
WikiStub-Seed) -- `resolve_pin_for_module()` prefers that field, falling back
to `version` only when `version` itself happens to already be a full 40-hex
SHA (the pre-existing behaviour, kept so older/synthetic catalogs without a
`commit_sha` field still work exactly as before). A module with neither field
holding a valid SHA is still, correctly, "unpinnable" -- e.g. Ring 1's
build-your-users-mind and project-docs-template, which the catalog itself
does not pin (no fallback to a branch either way; see the "unpinnable" outcome
in plan_and_fetch(), which reports both raw fields for that reason). The
mechanic itself (valid SHA -> exact commit; invalid SHA -> loud failure,
nothing left behind) is proven by tests/test_fetch_place.py against a
disposable local throwaway git repository, mirroring the isolated test
technique INSTALLER-REUSE-BEFUND Sec. 5.4 itself used to find the bug being
avoided here.

Deliberately NOT this module's job:
  - writing into .MODULES/ (the shared catalog tree) -- E5 "Stores bleiben
    kanonisch": fetched modules land under a separate ocean-dev --workspace,
    never back into the canonical catalog.
  - resolving *which* components need fetching -- that is
    resolve_bundles.py's Resolve/Verify job; this module consumes its output
    (a ResolvedComponent with kind == "module") and does not re-verify hashes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class FetchError(RuntimeError):
    """A git operation failed after a valid SHA pin was already accepted."""


def is_git_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA_RE.match(value))


def force_rmtree(path: Path) -> None:
    """shutil.rmtree() alone cannot remove a git checkout's object files on
    Windows -- git marks blobs read-only, and plain rmtree raises
    PermissionError (WinError 5) on them. Found empirically running this
    module's own real-git tests on this host, not assumed.

    First fix attempt chmod'd every entry to write-only (stat.S_IWRITE,
    0o200) before removing -- fine on Windows (chmod barely affects
    directory traversal there), but WRONG on POSIX: a directory with mode
    0o200 has neither read nor execute, so shutil.rmtree can no longer list
    or descend into it, silently leaves it behind under `ignore_errors=True`,
    and the caller never finds out. Caught by the Mac Studio foreign-host
    smoke test (2026-08-18) -- both fetch-cleanup and rollback left a `.git`
    directory behind there, exactly this failure mode, exactly why that
    smoke test exists. Fixed by granting full owner rwx (0o700) instead of
    only the write bit, on both directories and files, before removing --
    this keeps traversal working on POSIX while still clearing Windows'
    read-only attribute (chmod 0o700 sets FILE_ATTRIBUTE_READONLY off too)."""
    if path.is_symlink():
        raise OSError(f"refusing to recursively remove symlink: {path}")
    if not path.exists():
        return
    try:
        path.chmod(0o700)
    except OSError:
        pass
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                (Path(root) / name).chmod(0o700)
            except OSError:
                pass
    shutil.rmtree(path)
    if path.exists() or path.is_symlink():
        raise OSError(f"recursive removal reported success but target remains: {path}")


@dataclass
class FetchOutcome:
    ref: str                # "module:<id>"
    action: str              # see _ACTIONS below
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "action": self.action, "detail": self.detail}


_ACTIONS = {
    "present": "already present locally (Resolve found it under the catalog's resolved_source) -- nothing to fetch",
    "no-catalog-entry": "Resolve could not find this module in the catalog at all -- Fetch has no source to act on",
    "unfetchable-source-type": "catalog entry exists but its source_of_truth.type is not git-repository -- "
                                "not something this module knows how to fetch (e.g. local-directory missing "
                                "on disk is a broken catalog entry, not a fetch target)",
    "unpinnable": "neither the catalog's commit_sha field nor its version field is a full 40-hex commit SHA "
                  "-- refusing to fetch rather than silently falling back to a branch (the bug this module "
                  "exists to not repeat)",
    "planned": "dry-run: this is what --apply would do (no git command has been run)",
    "fetched": "git fetch+checkout at the pinned SHA succeeded",
    "present-pinned-provider": "the exact OCEAN-bound provider commit, identity, repository, and capabilities are already present",
    "skipped-present-in-workspace": "the workspace destination for this module already exists -- never overwrite",
    "failed": "a git command failed; any partial destination directory was removed",
}


def resolve_pin_for_module(catalog_entry: dict[str, Any]) -> tuple[str | None, Any]:
    """Returns (sha_or_none, raw_version_field). A separate, focused catalog
    read rather than extending resolve_bundles.resolve_module()'s detail dict
    -- that function is tested and stable; this need (the raw, unfiltered
    pin fields) is specific to Fetch and does not belong in Resolve's output
    contract.

    Prefers the builder-computed `commit_sha` field
    (.MODULES/_scripts/build_catalog.py) over `version`: `version` stays a
    human-facing semver string, `commit_sha` is the actual pin, so there is
    no doubling of meaning between the two fields. `version` is still used as
    a pin *fallback* when it happens to already be a full 40-hex SHA itself
    -- the behaviour this function had before `commit_sha` existed, kept so
    a catalog entry (or test fixture) that only ever set `version` to a SHA
    keeps working unchanged. Neither field holding a valid SHA still means
    unpinnable -- this never widens what counts as pinnable, it only adds a
    second, preferred place to find a pin. The returned `raw_version_field`
    is deliberately still `version` specifically (not `commit_sha`) --
    callers that report "unpinnable" add the raw `commit_sha` themselves
    (see plan_and_fetch) so both fields are visible in that outcome's detail
    without changing this function's tested return shape."""
    raw_commit_sha = catalog_entry.get("commit_sha")
    raw_version = catalog_entry.get("version")
    if is_git_sha(raw_commit_sha):
        return raw_commit_sha, raw_version
    if is_git_sha(raw_version):
        return raw_version, raw_version
    return None, raw_version


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _normalized_repository(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").removesuffix(".git").casefold()


def verify_bound_provider(dest: Path, binding: dict[str, Any]) -> dict[str, Any]:
    """Prove that an existing placement satisfies one exact OCEAN binding."""
    if dest.is_symlink() or not dest.is_dir():
        raise FetchError(f"bound provider placement is not a regular directory: {dest}")
    head = _run_git(["rev-parse", "HEAD"], cwd=dest)
    observed_head = head.stdout.strip() if head.returncode == 0 else None
    if observed_head != binding.get("commit"):
        raise FetchError(
            f"bound provider HEAD {observed_head!r} does not match pinned commit "
            f"{binding.get('commit')!r}"
        )
    status = _run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=dest)
    if status.returncode != 0:
        raise FetchError("bound provider worktree state could not be verified")
    if status.stdout.strip():
        raise FetchError("bound provider has uncommitted or untracked changes")
    remote = _run_git(["remote", "get-url", "origin"], cwd=dest)
    observed_repository = remote.stdout.strip() if remote.returncode == 0 else None
    if (
        not observed_repository
        or _normalized_repository(observed_repository)
        != _normalized_repository(str(binding.get("repository") or ""))
    ):
        raise FetchError(
            f"bound provider repository {observed_repository!r} does not match "
            f"{binding.get('repository')!r}"
        )
    manifest_path = dest / str(binding.get("provider_manifest") or "")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FetchError(f"bound provider manifest is unreadable: {manifest_path}: {exc}") from exc
    if manifest.get("schema") != "ellmos.module.v2":
        raise FetchError(f"bound provider manifest has unsupported schema: {manifest.get('schema')!r}")
    if manifest.get("id") != binding.get("catalog_id"):
        raise FetchError(
            f"bound provider ID {manifest.get('id')!r} does not match "
            f"catalog ID {binding.get('catalog_id')!r}"
        )
    declared = set(manifest.get("provides") or [])
    required = list(binding.get("required_provides") or [])
    missing = sorted(set(required) - declared)
    if missing:
        raise FetchError(f"bound provider does not declare required capabilities: {missing}")
    return {
        "head": observed_head,
        "repository": observed_repository,
        "provider_id": manifest["id"],
        "verified_provides": required,
        "manifest": str(manifest_path),
    }


def fetch_module_at_sha(repository_url: str, sha: str, dest: Path, *, dry_run: bool) -> FetchOutcome:
    """Clone exactly `sha` from `repository_url` into `dest` via a shallow
    fetch-by-commit (no branch name involved at any point, so there is no
    branch to silently fall back to). `dest` must not already exist -- callers
    enforce "never overwrite" before calling this, matching the write-side
    Activate policy for skills."""
    if not is_git_sha(sha):
        raise FetchError(f"refusing to fetch {repository_url!r}: {sha!r} is not a 40-hex commit SHA")
    if dest.exists():
        raise FetchError(f"refusing to fetch into {dest}: destination already exists (never overwrite)")
    if dry_run:
        return FetchOutcome("", "planned", {"repository": repository_url, "sha": sha, "dest": str(dest)})

    dest.mkdir(parents=True)
    try:
        steps = [
            ["init", "-q"],
            ["remote", "add", "origin", repository_url],
            ["fetch", "--depth", "1", "origin", sha],
            ["checkout", "-q", "FETCH_HEAD"],
        ]
        for step in steps:
            proc = _run_git(step, cwd=dest)
            if proc.returncode != 0:
                raise FetchError(
                    f"git {' '.join(step)} failed (exit {proc.returncode}) for {repository_url}@{sha}: "
                    f"{proc.stderr.strip()}"
                )
        head = _run_git(["rev-parse", "HEAD"], cwd=dest)
        landed_sha = head.stdout.strip() if head.returncode == 0 else None
        if landed_sha != sha:
            raise FetchError(
                f"post-checkout HEAD {landed_sha!r} does not match the pinned SHA {sha!r} -- "
                "refusing to leave a mismatched checkout in place"
            )
    except FetchError as exc:
        try:
            force_rmtree(dest)
        except OSError as cleanup_exc:
            raise FetchError(f"{exc}; cleanup of partial destination {dest} failed: {cleanup_exc}") from cleanup_exc
        raise
    return FetchOutcome("", "fetched", {"repository": repository_url, "sha": sha, "dest": str(dest), "head": landed_sha})


def plan_and_fetch(
    components: list[Any], catalog_path: Path, workspace: Path, *, apply: bool,
) -> list[FetchOutcome]:
    """For every kind == "module" ResolvedComponent: decide + (if apply) do.
    Reads the catalog itself only to resolve the pin (see
    resolve_pin_for_module) -- membership/presence was already decided by
    resolve_bundles.resolve_module() and is trusted here via component.status
    and component.detail, not re-derived."""
    catalog: dict[str, Any] = {}
    if catalog_path.is_file():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    modules_by_id = {m["id"]: m for m in catalog.get("modules", [])}

    outcomes: list[FetchOutcome] = []
    dest_root = workspace / "modules"
    for comp in components:
        if comp.kind != "module":
            continue
        binding = comp.detail.get("binding")
        if isinstance(binding, dict):
            catalog_id = comp.detail.get("catalog_id")
            entry = modules_by_id.get(catalog_id, {})
            if not entry:
                outcomes.append(FetchOutcome(
                    comp.ref,
                    "no-catalog-entry",
                    {"reason": "exact bound catalog record is absent", **dict(comp.detail)},
                ))
                continue
            if comp.detail.get("source_type") != "git-repository":
                outcomes.append(FetchOutcome(
                    comp.ref, "unfetchable-source-type", dict(comp.detail)
                ))
                continue
            sha = binding.get("commit")
            repository_url = comp.detail.get("repository")
            placement_id = binding.get("placement_id")
            if not is_git_sha(sha):
                outcomes.append(FetchOutcome(
                    comp.ref,
                    "unpinnable",
                    {"pin_source": "component-binding", "raw_commit_sha": sha},
                ))
                continue
            if (
                not isinstance(placement_id, str)
                or not placement_id
                or placement_id in {".", ".."}
                or "/" in placement_id
                or "\\" in placement_id
                or comp.ref != f"module:{placement_id}"
            ):
                outcomes.append(FetchOutcome(
                    comp.ref,
                    "failed",
                    {"reason": "unsafe or mismatched component-binding placement_id"},
                ))
                continue
            if (
                not repository_url
                or _normalized_repository(str(repository_url))
                != _normalized_repository(str(binding.get("repository") or ""))
            ):
                outcomes.append(FetchOutcome(
                    comp.ref,
                    "failed",
                    {"reason": "catalog repository does not match component binding"},
                ))
                continue
            dest = dest_root / placement_id
            if dest.exists() or dest.is_symlink():
                try:
                    proof = verify_bound_provider(dest, binding)
                except FetchError as exc:
                    outcomes.append(FetchOutcome(
                        comp.ref,
                        "failed",
                        {"error": str(exc), "dest": str(dest), "never_overwritten": True},
                    ))
                    continue
                binding["provider_verified"] = True
                binding["verification"] = proof
                comp.status = "resolved"
                comp.detail["local_path"] = str(dest.resolve(strict=False))
                comp.detail["present_locally"] = True
                comp.detail["provides"] = sorted(
                    set(comp.detail.get("provides") or [])
                    | set(binding.get("required_provides") or [])
                )
                outcomes.append(FetchOutcome(
                    comp.ref,
                    "present-pinned-provider",
                    {"dest": str(dest), "pin_source": "component-binding", **proof},
                ))
                continue
            try:
                outcome = fetch_module_at_sha(
                    str(repository_url), sha, dest, dry_run=not apply
                )
            except FetchError as exc:
                outcomes.append(FetchOutcome(comp.ref, "failed", {"error": str(exc)}))
                continue
            outcome.ref = comp.ref
            outcome.detail.update({
                "catalog_id": catalog_id,
                "placement_id": placement_id,
                "pin_source": "component-binding",
                "required_provides": list(binding.get("required_provides") or []),
            })
            if apply:
                try:
                    proof = verify_bound_provider(dest, binding)
                except FetchError as exc:
                    try:
                        force_rmtree(dest)
                    except OSError as cleanup_exc:
                        exc = FetchError(f"{exc}; cleanup failed: {cleanup_exc}")
                    outcomes.append(FetchOutcome(comp.ref, "failed", {"error": str(exc)}))
                    continue
                binding["provider_verified"] = True
                binding["verification"] = proof
                comp.status = "resolved"
                comp.detail["local_path"] = str(dest.resolve(strict=False))
                comp.detail["present_locally"] = True
                comp.detail["provides"] = sorted(
                    set(comp.detail.get("provides") or [])
                    | set(binding.get("required_provides") or [])
                )
                outcome.detail.update(proof)
            outcomes.append(outcome)
            continue
        if comp.status == "resolved":
            outcomes.append(FetchOutcome(comp.ref, "present", {"present_locally": True}))
            continue
        catalog_id = comp.detail.get("catalog_id")
        if not catalog_id:
            outcomes.append(FetchOutcome(comp.ref, "no-catalog-entry", dict(comp.detail)))
            continue
        if comp.detail.get("source_type") != "git-repository":
            outcomes.append(FetchOutcome(comp.ref, "unfetchable-source-type", dict(comp.detail)))
            continue
        entry = modules_by_id.get(catalog_id, {})
        sha, raw_version = resolve_pin_for_module(entry)
        repository_url = comp.detail.get("repository")
        if sha is None:
            outcomes.append(FetchOutcome(
                comp.ref, "unpinnable",
                {
                    "catalog_id": catalog_id, "raw_version": raw_version,
                    "raw_commit_sha": entry.get("commit_sha"), "repository": repository_url,
                },
            ))
            continue
        dest = dest_root / catalog_id
        if dest.exists():
            outcomes.append(FetchOutcome(comp.ref, "skipped-present-in-workspace", {"dest": str(dest)}))
            continue
        if not repository_url:
            outcomes.append(FetchOutcome(comp.ref, "failed", {"reason": "no repository URL in catalog entry"}))
            continue
        try:
            outcome = fetch_module_at_sha(repository_url, sha, dest, dry_run=not apply)
        except FetchError as exc:
            outcomes.append(FetchOutcome(comp.ref, "failed", {"error": str(exc)}))
            continue
        outcome.ref = comp.ref
        outcomes.append(outcome)
    return outcomes
