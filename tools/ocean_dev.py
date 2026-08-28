#!/usr/bin/env python3
"""Single-command entry point chaining Resolve -> Verify -> Fetch/Place ->
Activate for one ring (architecture/INSTALLER-TARGET.md's four-step model,
plus Roll back as a separate `--rollback` mode). This is the "ocean-dev up"
item from architecture/OCEAN-DEV-BUILD-PLAN_2026-08-18.md Section 5.

Composition, not re-implementation: Resolve/Verify reuse
tools/resolve_bundles.py's own tested functions directly (load_skeleton,
select_bundle_refs, verify_bundle, expand_components, merge_components,
resolve_module, resolve_skill, resolve_access_surface, apply_activation_check)
-- this file does not wrap resolve_bundles.main() or duplicate its logic, it
imports the pieces and owns its own reporting/exit codes on top of them, so a
failed Verify still stops the run before any write, exactly as it does there.

SAFETY -- read before changing defaults:
  - Dry-run is the default. Nothing is written to disk unless --apply is
    given, matching the pilot installer's own --dry-run-first convention
    (sovereign-private/_dev/pilot/install_sovereign.py) and the explicit
    instruction this was built under.
  - --skills-dir NEVER defaults to a host's real, live skill directory
    (e.g. ~/.claude/skills). The default is <workspace>/skills -- a sandbox
    that starts empty. Activating into a *real* host's live skills directory
    is only possible by passing --skills-dir explicitly; this tool will not
    do it on its own, so a build/test run of this file can never silently
    add or remove skills the running agent actually uses. See
    tools/host_adapters.py's module docstring for the full reasoning.
  - --workspace (module clones, skills sandbox, activation log) defaults to
    ~/ocean-dev -- outside OneDrive on every host that follows the same
    convention as the Mac Studio compute policy (nothing long-lived goes
    into an OneDrive-synced path).
  - Every write this script performs when --apply is given is logged to
    --activation-log (default <workspace>/ocean-dev.activation-log.json).
    `--rollback <that file>` undoes exactly those entries, in reverse order,
    and nothing else -- it does not guess at what else might need undoing.

Usage:
    python tools/ocean_dev.py --bundles-root <path> [--ring 1|2|all]
        [--workspace <dir>] [--skills-dir <dir>] [--host claude-code]
        [--apply] [--json] [--report <path>] [--activation-log <path>]

    python tools/ocean_dev.py --rollback <path-to-activation-log.json>
        [--workspace <dir>] [--skills-dir <dir>] [--host claude-code]

Exit codes: 0 = success (including "nothing to do"). 2 = Verify failed
(a bundle hash check did not pass). 3 = skeleton/manifest could not be read.
4 = at least one Fetch or Activate action failed after Verify passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_place import force_rmtree, plan_and_fetch  # noqa: E402
from host_adapters import known_adapters  # noqa: E402
from resolve_bundles import (  # noqa: E402
    DEFAULT_MODULES_CATALOG,
    DEFAULT_SKELETON,
    DEFAULT_SKILLS_REGISTRY,
    ResolveError,
    apply_activation_check,
    expand_components,
    load_skeleton,
    merge_components,
    resolve_access_surface,
    resolve_module,
    resolve_skill,
    select_bundle_refs,
    verify_bundle,
)

DEFAULT_WORKSPACE = Path.home() / "ocean-dev"


def _skills_source_root(skills_registry: Path) -> Path:
    """`components.json`'s own `path` field is relative to the registry's
    grandparent directory (verified empirically: entry path
    "skills/assist/buero/SKILL.md" resolves under
    .../.AI/.SKILLS/skills/assist/buero/SKILL.md, i.e. one level above
    the `registry/` directory that components.json itself lives in --
    checked against the real file on disk before writing this, the same
    empirical-first discipline resolve_bundles.py's component-ref nesting
    comment describes)."""
    return skills_registry.parent.parent


def resolve_and_verify(args: argparse.Namespace) -> tuple[list[Any], list[Any]]:
    """Runs Resolve + Verify via resolve_bundles.py's own functions. Returns
    (verifications, components). Raises ResolveError (caller maps to exit 3)
    or returns with an unresolved Verify (caller checks .ok and exits 2)."""
    skeleton = load_skeleton(args.skeleton)
    refs = select_bundle_refs(skeleton, args.ring)

    verifications = []
    component_lists = []
    for bundle_ref in refs:
        result, manifest = verify_bundle(bundle_ref, args.bundles_root)
        verifications.append(result)
        if result.ok and manifest is not None:
            component_lists.append(expand_components(manifest, bundle_ref["ref"]))

    if not all(v.ok for v in verifications):
        return verifications, []

    components = merge_components(component_lists)
    for comp in components:
        if comp.kind == "module":
            resolve_module(comp, args.modules_catalog)
        elif comp.kind == "skill":
            resolve_skill(comp, args.skills_registry)
        elif comp.kind == "access_surface":
            resolve_access_surface(comp)
        else:
            comp.status = "unresolved"
            comp.detail = {"reason": f"unknown component kind: {comp.kind!r}"}
    return verifications, components


def activate_skills(components: list[Any], adapter: Any, skills_source_root: Path, apply: bool) -> list[dict[str, Any]]:
    """Write-side Activate for every skill: Resolve status must be "resolved"
    AND the read-only activation check (apply_activation_check, run by the
    caller before this) must say not-present -- present already means
    "nothing to do", which activate_skill() would independently also decide
    (never overwrite), but skipping here avoids attempting a copy this run
    already knows is a no-op."""
    outcomes: list[dict[str, Any]] = []
    for comp in components:
        if comp.kind != "skill" or comp.status != "resolved":
            continue
        act = comp.detail.get("activation")
        if act and act.get("present"):
            outcomes.append({"ref": comp.ref, "action": "skipped-already-present", "detail": {}})
            continue
        name = comp.ref.split(":", 1)[1]
        rel_path = comp.detail.get("path")
        if not rel_path:
            outcomes.append({"ref": comp.ref, "action": "failed", "detail": {"reason": "no path in registry entry"}})
            continue
        source_dir = (skills_source_root / rel_path).parent
        result = adapter.activate_skill(name, source_dir, apply=apply)
        entry = result.as_dict()
        entry["ref"] = comp.ref
        outcomes.append(entry)
    return outcomes


def write_activation_log(path: Path, module_outcomes: list[Any], skill_outcomes: list[dict[str, Any]]) -> None:
    entries = []
    for o in module_outcomes:
        if o.action == "fetched":
            resolved_dest = Path(o.detail["dest"]).resolve(strict=False)
            entries.append({
                "type": "module",
                "ref": o.ref,
                "id": resolved_dest.name,
                "dest": str(resolved_dest),
            })
    for o in skill_outcomes:
        if o["action"] == "activated":
            entries.append({
                "type": "skill",
                "ref": o["ref"],
                "id": o["skill_name"],
                "dest": str(Path(o["detail"]["dest"]).resolve(strict=False)),
            })
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "ellmos.open-ocean-activation-log.v1", "entries": entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_leaf_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value


def do_rollback(log_path: Path, adapter: Any, workspace: Path) -> int:
    if not log_path.is_file():
        print(f"ERROR: activation log not found: {log_path}", file=sys.stderr)
        return 3
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid activation log {log_path}: {exc}", file=sys.stderr)
        return 4
    if not isinstance(log, dict) or log.get("schema") != "ellmos.open-ocean-activation-log.v1":
        print(f"ERROR: unsupported or missing activation-log schema in {log_path}", file=sys.stderr)
        return 4
    entries = log.get("entries")
    if not isinstance(entries, list):
        print(f"ERROR: activation-log entries must be a list in {log_path}", file=sys.stderr)
        return 4

    # Validate every entry and every target before the first deletion. A
    # malformed or replayed log therefore cannot produce a partial rollback.
    operations: list[tuple[str, str, str, Path]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            print(f"ERROR: activation-log entry {index} is not an object", file=sys.stderr)
            return 4
        entry_type = entry.get("type")
        ref = entry.get("ref")
        raw_dest = entry.get("dest")
        if not isinstance(raw_dest, str) or not raw_dest:
            print(f"ERROR: activation-log entry {index} has no valid destination", file=sys.stderr)
            return 4
        logged_dest = Path(raw_dest).resolve(strict=False)
        if entry_type == "skill":
            skill_id = entry.get("id")
            if not _safe_leaf_id(skill_id) or ref != f"skill:{skill_id}":
                print(f"ERROR: invalid skill rollback entry {index}: {entry!r}", file=sys.stderr)
                return 4
            configured_dest = (adapter.skills_dir / skill_id).resolve(strict=False)
            if logged_dest != configured_dest:
                print(
                    f"ERROR: skill {skill_id} logged destination {logged_dest} does not match configured target {configured_dest}",
                    file=sys.stderr,
                )
                return 4
            operations.append(("skill", ref, skill_id, logged_dest))
        elif entry_type == "module":
            if not isinstance(ref, str) or not ref.startswith("module:"):
                print(f"ERROR: invalid module rollback entry {index}: {entry!r}", file=sys.stderr)
                return 4
            ref_module_id = ref.removeprefix("module:")
            logged_module_id = entry.get("id", Path(raw_dest).name)
            if not _safe_leaf_id(ref_module_id) or not _safe_leaf_id(logged_module_id):
                print(
                    f"ERROR: unsafe module id in rollback entry {index}: ref={ref_module_id!r}, id={logged_module_id!r}",
                    file=sys.stderr,
                )
                return 4
            if logged_module_id.casefold() != ref_module_id.casefold():
                print(
                    f"ERROR: module rollback entry {index} id {logged_module_id!r} does not match ref {ref!r}",
                    file=sys.stderr,
                )
                return 4
            configured_dest = (workspace / "modules" / logged_module_id).resolve(strict=False)
            if logged_dest != configured_dest:
                print(
                    f"ERROR: module {ref} logged destination {logged_dest} does not match workspace target {configured_dest}",
                    file=sys.stderr,
                )
                return 4
            operations.append(("module", ref, logged_module_id, logged_dest))
        else:
            print(f"ERROR: unknown activation-log entry type at index {index}: {entry_type!r}", file=sys.stderr)
            return 4

    failures = 0
    for entry_type, ref, component_id, dest in reversed(operations):
        if entry_type == "skill":
            result = adapter.rollback_activate_skill(component_id, expected_dest=dest)
            print(f"  [{'OK' if result.action == 'rolled-back' else 'FAIL'}] skill {component_id}: {result.action} ({result.detail})")
            failures += int(result.action != "rolled-back")
        else:
            if dest.is_symlink():
                print(f"  [FAIL] module {ref}: refusing to remove symlink {dest}")
                failures += 1
                continue
            if not dest.is_dir():
                print(f"  [FAIL] module {ref}: {dest} not found (already rolled back?)")
                failures += 1
                continue
            try:
                force_rmtree(dest)
            except OSError as exc:
                print(f"  [FAIL] module {ref}: could not remove {dest}: {exc}")
                failures += 1
                continue
            if dest.exists() or dest.is_symlink():
                print(f"  [FAIL] module {ref}: target remains after rollback: {dest}")
                failures += 1
            else:
                print(f"  [OK] module {ref}: removed {dest}")
    return 4 if failures else 0


def render_text(report: dict[str, Any]) -> str:
    lines = [f"ocean-dev up -- ring {report['ring']} -- {'APPLY' if report['apply'] else 'DRY-RUN'}", ""]
    v = report["verify"]
    lines.append(f"Verify: {v['bundles_checked']} bundle(s), all_ok={v['all_ok']}")
    for r in v["results"]:
        lines.append(f"  [{'OK' if r['ok'] else 'FAIL'}] {r['bundle_ref']}")
    lines.append("")
    lines.append(f"Fetch+Place ({len(report['fetch'])} module component(s)):")
    for o in report["fetch"]:
        lines.append(f"  [{o['action']:>26}] {o['ref']}")
    lines.append("")
    lines.append(f"Activate ({len(report['activate'])} skill component(s)), host={report['host']}, target={report['skills_dir']}:")
    for o in report["activate"]:
        lines.append(f"  [{o['action']:>26}] {o['ref']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundles-root", type=Path, help="path to a local checkout of ellmos-ai/bundles (required unless --rollback)")
    parser.add_argument("--ring", default="1")
    parser.add_argument("--skeleton", type=Path, default=DEFAULT_SKELETON)
    parser.add_argument("--modules-catalog", type=Path, default=DEFAULT_MODULES_CATALOG)
    parser.add_argument("--skills-registry", type=Path, default=DEFAULT_SKILLS_REGISTRY)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--skills-dir", type=Path, default=None, help="write target for Activate; default <workspace>/skills, NEVER a live host directory unless given explicitly")
    parser.add_argument("--host", default="claude-code")
    parser.add_argument("--apply", action="store_true", help="perform real writes (default: dry-run/plan only)")
    parser.add_argument("--activation-log", type=Path, default=None, help="default <workspace>/ocean-dev.activation-log.json")
    parser.add_argument("--rollback", type=Path, default=None, metavar="LOG", help="undo the entries in this activation log instead of running Resolve->Activate")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    adapters = known_adapters()
    adapter_cls = adapters.get(args.host)
    if adapter_cls is None:
        print(f"ERROR: unknown --host {args.host!r} (known: {sorted(adapters)})", file=sys.stderr)
        return 3
    skills_dir = args.skills_dir or (args.workspace / "skills")
    adapter = adapter_cls(skills_dir=skills_dir)

    if args.rollback:
        return do_rollback(args.rollback, adapter, args.workspace)

    if args.bundles_root is None:
        print("ERROR: --bundles-root is required (unless --rollback)", file=sys.stderr)
        return 3

    try:
        verifications, components = resolve_and_verify(args)
    except ResolveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    if not all(v.ok for v in verifications):
        for v in verifications:
            if not v.ok:
                print(f"FAIL: {v.bundle_ref}: self_consistent={v.self_consistent} matches_pin={v.matches_pin}", file=sys.stderr)
        print("\nVerify FAILED -- stopping before Fetch/Place/Activate (INSTALLER-TARGET.md: "
              "a failed hash check stops the run).", file=sys.stderr)
        return 2

    activation_summary = apply_activation_check(components, adapter)
    fetch_outcomes = plan_and_fetch(components, args.modules_catalog, args.workspace, apply=args.apply)
    skills_source_root = _skills_source_root(args.skills_registry)
    activate_outcomes = activate_skills(components, adapter, skills_source_root, apply=args.apply)

    if args.apply:
        log_path = args.activation_log or (args.workspace / "ocean-dev.activation-log.json")
        write_activation_log(log_path, fetch_outcomes, activate_outcomes)

    report = {
        "schema": "ellmos.open-ocean-up-report.v1",
        "ring": args.ring,
        "apply": args.apply,
        "host": adapter.name,
        "skills_dir": str(skills_dir),
        "verify": {
            "bundles_checked": len(verifications),
            "all_ok": all(v.ok for v in verifications),
            "results": [v.as_dict() for v in verifications],
        },
        "activation_check": activation_summary,
        "fetch": [o.as_dict() for o in fetch_outcomes],
        "activate": activate_outcomes,
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text(report))

    any_failed = any(o.action == "failed" for o in fetch_outcomes) or any(o["action"] == "failed" for o in activate_outcomes)
    return 4 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
